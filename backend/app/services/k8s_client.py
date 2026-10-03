import time
from typing import Optional, Dict, Any, List
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from backend.app.core.config import settings

class K8sService:
    def __init__(self):
        self.k8s_available = False
        self.apps_v1: Optional[client.AppsV1Api] = None
        self.core_v1: Optional[client.CoreV1Api] = None
        self._deployment_cache: Dict[str, Any] = {}
        self._init_client()

    def _init_client(self):
        try:
            if settings.K8S_IN_CLUSTER:
                config.load_incluster_config()
            else:
                config.load_kube_config()
            k8s_config = client.Configuration.get_default_copy()
            k8s_config.connection_pool_maxsize = 120
            api_client = client.ApiClient(configuration=k8s_config)
            self.apps_v1 = client.AppsV1Api(api_client=api_client)
            self.core_v1 = client.CoreV1Api(api_client=api_client)
            self.k8s_available = True
            print("[K8sService] Connected to Kubernetes cluster successfully.")
            self._ensure_namespace(settings.K8S_NAMESPACE)
        except Exception as e:
            print(f"[K8sService Warning] Could not connect to Kubernetes: {e}. Running in standalone/fallback mode.")
            self.k8s_available = False

    def _ensure_namespace(self, namespace: str):
        if not self.k8s_available:
            return
        try:
            namespaces = self.core_v1.list_namespace()
            if not any(ns.metadata.name == namespace for ns in namespaces.items):
                ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
                self.core_v1.create_namespace(ns_body)
                print(f"[K8sService] Created namespace: {namespace}")
        except Exception as e:
            print(f"[K8sService Error] Failed ensuring namespace {namespace}: {e}")

    def deploy_function(self, function_name: str, image_tag: str, memory_limit: str = "256Mi", cpu_limit: str = "500m", initial_replicas: int = 1) -> bool:
        """
        Creates or updates a Kubernetes Deployment and Service for the serverless function.
        """
        if not self.k8s_available:
            print(f"[K8sService Mock] Deployed function {function_name} with image {image_tag}")
            return True

        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE

        # Security Context
        security_context = client.V1SecurityContext(
            run_as_non_root=True,
            run_as_user=10001,
            allow_privilege_escalation=False,
            capabilities=client.V1Capabilities(drop=["ALL"])
        )

        # Resource Requirements
        resources = client.V1ResourceRequirements(
            limits={"memory": memory_limit, "cpu": cpu_limit},
            requests={"memory": "64Mi", "cpu": "100m"}
        )

        # Readiness Probe for cold-start checking
        readiness_probe = client.V1Probe(
            http_get=client.V1HTTPGetAction(path="/healthz", port=8080),
            initial_delay_seconds=1,
            period_seconds=1,
            failure_threshold=30
        )

        # Container Definition
        container = client.V1Container(
            name="function-runner",
            image=image_tag,
            image_pull_policy="IfNotPresent",
            ports=[client.V1ContainerPort(container_port=8080)],
            resources=resources,
            security_context=security_context,
            readiness_probe=readiness_probe
        )

        # Pod Template Spec
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": app_label, "faas-function": function_name}),
            spec=client.V1PodSpec(
                containers=[container],
                restart_policy="Always"
            )
        )

        # Deployment Spec
        spec = client.V1DeploymentSpec(
            replicas=initial_replicas,
            selector=client.V1LabelSelector(match_labels={"app": app_label}),
            template=template
        )

        deployment_body = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=app_label, namespace=namespace, labels={"app": app_label}),
            spec=spec
        )

        # Create or Update Deployment
        try:
            self.apps_v1.read_namespaced_deployment(name=app_label, namespace=namespace)
            self.apps_v1.replace_namespaced_deployment(name=app_label, namespace=namespace, body=deployment_body)
            print(f"[K8sService] Updated Deployment: {app_label}")
        except ApiException as e:
            if e.status == 404:
                self.apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment_body)
                print(f"[K8sService] Created Deployment: {app_label}")
            else:
                raise e

        # Create or Update Service
        service_body = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(name=app_label, namespace=namespace, labels={"app": app_label}),
            spec=client.V1ServiceSpec(
                selector={"app": app_label},
                ports=[client.V1ServicePort(port=8080, target_port=8080)],
                type="ClusterIP"
            )
        )

        try:
            self.core_v1.read_namespaced_service(name=app_label, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                self.core_v1.create_namespaced_service(namespace=namespace, body=service_body)
                print(f"[K8sService] Created ClusterIP Service: {app_label}")

        return True

    def scale_deployment(self, function_name: str, replicas: int) -> bool:
        """
        Scales the number of replicas for a function deployment (e.g. to 0 for scale-to-zero, or to 1 for warm-up).
        """
        if not self.k8s_available:
            print(f"[K8sService Mock] Scaled function {function_name} to {replicas} replicas")
            return True

        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE

        try:
            scale_body = client.V1Scale(
                metadata=client.V1ObjectMeta(name=app_label, namespace=namespace),
                spec=client.V1ScaleSpec(replicas=replicas)
            )
            self.apps_v1.replace_namespaced_deployment_scale(name=app_label, namespace=namespace, body=scale_body)
            print(f"[K8sService] Scaled {app_label} to {replicas} replicas")
            return True
        except Exception as e:
            print(f"[K8sService Error] Failed scaling {app_label}: {e}")
            return False

    def wait_for_ready_pod(self, function_name: str, timeout_seconds: int = 30) -> Optional[str]:
        """
        Waits until at least one pod is in Ready condition, and returns the Pod IP or Service hostname.
        """
        if not self.k8s_available:
            return "127.0.0.1"

        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE
        start_time = time.time()

        while (time.time() - start_time) < timeout_seconds:
            try:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"app={app_label}"
                )
                for pod in pods.items:
                    if pod.status and pod.status.phase == "Running" and pod.status.pod_ip:
                        # Check container ready status
                        if pod.status.container_statuses:
                            ready = all(c.ready for c in pod.status.container_statuses)
                            if ready:
                                return pod.status.pod_ip
            except Exception as e:
                print(f"[K8sService] Polling pods error: {e}")
            time.sleep(0.1)

        return None

    def has_deployment(self, function_name: str) -> bool:
        """
        Checks whether the Deployment for a function exists in Kubernetes.
        Caches positive/negative results briefly to avoid saturating K8s API during bursts.
        """
        if not self.k8s_available:
            return False
            
        now = time.time()
        if function_name in self._deployment_cache:
            exists, cached_at = self._deployment_cache[function_name]
            if (now - cached_at) < 30.0:
                return exists

        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE
        try:
            self.apps_v1.read_namespaced_deployment(name=app_label, namespace=namespace)
            self._deployment_cache[function_name] = (True, now)
            return True
        except Exception:
            self._deployment_cache[function_name] = (False, now)
            return False

    def invoke_function(self, function_name: str, payload: dict, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """
        Invokes a function via the Kubernetes API server service proxy (for out-of-cluster)
        or direct cluster DNS (for in-cluster).
        """
        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE

        if settings.K8S_IN_CLUSTER:
            import httpx
            url = f"http://{app_label}.{namespace}.svc.cluster.local:8080/execute"
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.post(url, json=payload)
                resp_json = resp.json() if resp.status_code == 200 else {}
                return {
                    "status_code": resp.status_code,
                    "result": resp_json.get("result"),
                    "execution_time_ms": resp_json.get("execution_time_ms", 0.0),
                    "error": resp_json.get("error", resp.text) if resp.status_code != 200 else None
                }
        else:
            path = f"/api/v1/namespaces/{namespace}/services/http:{app_label}:8080/proxy/execute"
            resp = self.core_v1.api_client.call_api(
                path,
                'POST',
                header_params={'Content-Type': 'application/json'},
                body=payload,
                response_type='object',
                _request_timeout=timeout_seconds
            )
            data = resp[0]
            status_code = resp[1]
            if isinstance(data, dict):
                inner_status = data.get("statusCode", status_code)
                return {
                    "status_code": inner_status,
                    "result": data.get("result"),
                    "execution_time_ms": data.get("execution_time_ms", 0.0),
                    "error": data.get("error") if inner_status != 200 else None
                }
            return {
                "status_code": status_code,
                "result": data,
                "execution_time_ms": 0.0,
                "error": None
            }

    def get_function_endpoint(self, function_name: str) -> str:
        """
        Returns the invocation URL for the function inside the cluster or via proxy.
        """
        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE
        if self.k8s_available:
            return f"http://{app_label}.{namespace}.svc.cluster.local:8080/execute"
        return f"http://127.0.0.1:8080/execute"

    def delete_function(self, function_name: str) -> bool:
        """
        Deletes the Deployment and Service for the function.
        """
        if not self.k8s_available:
            return True

        app_label = f"fn-{function_name}"
        namespace = settings.K8S_NAMESPACE

        try:
            self.apps_v1.delete_namespaced_deployment(name=app_label, namespace=namespace)
            self.core_v1.delete_namespaced_service(name=app_label, namespace=namespace)
            print(f"[K8sService] Cleaned up Kubernetes resources for {function_name}")
            return True
        except Exception as e:
            print(f"[K8sService Warning] Cleanup error: {e}")
            return False

k8s_service = K8sService()
