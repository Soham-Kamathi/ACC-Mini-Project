import time
import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Set, Tuple
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, Gauge
from backend.app.core.config import settings
from backend.app.models.function import Function, FunctionVersion
from backend.app.models.invocation import InvocationLog
from backend.app.services.k8s_client import k8s_service
from backend.app.services.naming import resource_name

# Prometheus Metrics Definitions
INVOCATION_COUNT = Counter(
    "faas_invocations_total",
    "Total number of serverless function invocations",
    ["function_name", "status"]
)
COLD_START_COUNT = Counter(
    "faas_cold_starts_total",
    "Total number of cold starts",
    ["function_name"]
)
INVOCATION_DURATION = Histogram(
    "faas_invocation_duration_seconds",
    "Total invocation duration in seconds",
    ["function_name", "type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
ACTIVE_REPLICAS = Gauge(
    "faas_active_replicas",
    "Active replicas per function",
    ["function_name"]
)

# Where an invocation actually ran
EXEC_K8S = "k8s"
EXEC_SANDBOX = "sandbox"
EXEC_NONE = "none"

class VersionNotFound(ValueError):
    pass

class VersionNotReady(RuntimeError):
    pass

# In-memory caches and batch log queue to eliminate DB lock contention
_version_cache: Dict[str, Tuple[Any, float]] = {}
_log_queue: Optional[asyncio.Queue] = None
_log_worker_task: Optional[asyncio.Task] = None

# function id -> version tags whose Deployment is known to be scaled up (warm).
# The reaper clears a function's entry when it scales it to zero.
_warm_versions: Dict[int, Set[str]] = {}
_cold_start_locks: Dict[str, asyncio.Lock] = {}

def mark_warm(function_id: int, version_tag: str):
    _warm_versions.setdefault(function_id, set()).add(version_tag)

def mark_cold(function_id: int):
    _warm_versions.pop(function_id, None)

def invalidate_router_cache(fn_id: Optional[int] = None):
    global _version_cache
    if fn_id:
        keys_to_del = [k for k in list(_version_cache.keys()) if k.startswith(f"{fn_id}:")]
        for k in keys_to_del:
            _version_cache.pop(k, None)
    else:
        _version_cache.clear()

def _execute_sandbox(code: str, payload: Any) -> Tuple[int, Any, Optional[str]]:
    """
    Runs user code with exec() inside the API process. NOT isolated: only reachable when
    settings.ALLOW_LOCAL_SANDBOX is enabled (local development / tests).
    """
    import inspect
    try:
        local_scope = {}
        exec(code, local_scope)
        handler = local_scope.get("handler") or local_scope.get("main")
        if not callable(handler):
            return 500, None, "Handler function 'handler(event)' not found in code"

        sig = inspect.signature(handler)
        params = list(sig.parameters.values())
        if len(params) == 0:
            result = handler()
        elif len(params) == 1:
            result = handler(payload)
        elif isinstance(payload, dict) and all(p.name in payload for p in params if p.default == inspect.Parameter.empty):
            result = handler(**payload)
        else:
            result = handler(payload)
        return 200, result, None
    except Exception as ex:
        return 500, None, f"Runtime execution error: {str(ex)}"

async def _batch_log_worker():
    from backend.app.core.db import SessionLocal
    while True:
        try:
            items = []
            item = await _log_queue.get()
            items.append(item)
            while not _log_queue.empty() and len(items) < 100:
                try:
                    items.append(_log_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            def _write_batch(batch):
                with SessionLocal() as bg_db:
                    now_dt = datetime.utcnow()
                    for fn_id, log_kwargs in batch:
                        # Calls that never executed (nothing deployed, sandbox off) must not mark the function running
                        if log_kwargs.get("executed_on") != EXEC_NONE:
                            fn_obj = bg_db.query(Function).filter(Function.id == fn_id).first()
                            if fn_obj:
                                fn_obj.last_invoked_at = now_dt
                                fn_obj.active_replicas = 1
                                fn_obj.status = "RUNNING"
                        bg_db.add(InvocationLog(**log_kwargs))
                    bg_db.commit()

            await asyncio.to_thread(_write_batch, items)
            for _ in items:
                _log_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[RouterService Batch Log Error] {e}")
            await asyncio.sleep(0.05)

def _ensure_log_worker():
    global _log_queue, _log_worker_task
    if _log_queue is None:
        _log_queue = asyncio.Queue()
    if _log_worker_task is None or _log_worker_task.done():
        _log_worker_task = asyncio.create_task(_batch_log_worker())

class RouterService:
    def _resolve_version(self, db: Session, function: Function, version_tag: Optional[str]) -> FunctionVersion:
        """Latest = newest version that finished building/deploying. Versions that are still building are not routable."""
        cache_key = f"{function.id}:{version_tag or 'latest'}"
        now_time = time.time()
        if cache_key in _version_cache:
            c_ver, c_ts = _version_cache[cache_key]
            if (now_time - c_ts) < 15.0:
                return c_ver

        query = db.query(FunctionVersion).filter(FunctionVersion.function_id == function.id)
        if version_tag:
            version = query.filter(FunctionVersion.version_tag == version_tag).first()
            if not version:
                raise VersionNotFound(f"Version '{version_tag}' not found for function '{function.name}'")
            if not version.is_active:
                raise VersionNotReady(f"Version '{version_tag}' of '{function.name}' is not ready (still building, or the build failed)")
        else:
            version = query.filter(FunctionVersion.is_active.is_(True)).order_by(FunctionVersion.id.desc()).first()
            if not version:
                raise VersionNotReady(f"Function '{function.name}' has no ready version yet (still building, or the build failed)")
        _version_cache[cache_key] = (version, now_time)
        return version

    async def _cold_start(self, function: Function, version: FunctionVersion, resource: str, has_k8s_deployment: bool) -> float:
        COLD_START_COUNT.labels(function_name=function.name).inc()
        cold_start_begin = time.perf_counter()

        if has_k8s_deployment:
            print(f"[RouterService] Cold start detected for '{resource}'. Scaling up to 1 replica in K8s...")
            await asyncio.to_thread(k8s_service.scale_deployment, resource, 1)
            ready_ip = await asyncio.to_thread(k8s_service.wait_for_ready_pod, resource, 30)
            if not ready_ip and k8s_service.k8s_available:
                raise RuntimeError(f"Timed out waiting for Pod readiness for function '{function.name}' ({version.version_tag})")
        else:
            print(f"[RouterService] Cold start for local sandbox function '{function.name}'...")

        cold_start_duration_ms = (time.perf_counter() - cold_start_begin) * 1000.0
        print(f"[RouterService] Cold start completed in {cold_start_duration_ms:.2f}ms")

        mark_warm(function.id, version.version_tag)
        function.active_replicas = 1
        function.status = "RUNNING"
        def _mark_running(fn_id: int):
            from backend.app.core.db import SessionLocal
            with SessionLocal() as s:
                f = s.query(Function).filter(Function.id == fn_id).first()
                if f:
                    f.active_replicas = 1
                    f.status = "RUNNING"
                    s.commit()
        await asyncio.to_thread(_mark_running, function.id)
        ACTIVE_REPLICAS.labels(function_name=function.name).set(1)
        return cold_start_duration_ms

    async def invoke_function(
        self,
        db: Session,
        function: Function,
        version_tag: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a function version, handling cold-start provisioning if its Deployment is scaled to zero.
        Raises VersionNotFound / VersionNotReady if the requested version cannot be served.
        """
        request_id = str(uuid.uuid4())
        payload = payload or {}

        # 1. Resolve Function Version (with 15s in-memory cache)
        version = self._resolve_version(db, function, version_tag)
        resource = resource_name(function.owner_id, function.name, version.version_tag)

        has_k8s_deployment = await asyncio.to_thread(k8s_service.has_deployment, resource)
        sandbox_allowed = settings.ALLOW_LOCAL_SANDBOX

        is_cold_start = False
        cold_start_duration_ms = 0.0
        executed_on = EXEC_NONE
        status_code = 200
        result = None
        error_msg = None
        execution_duration_ms = 0.0

        if not has_k8s_deployment and not sandbox_allowed:
            status_code = 503
            error_msg = (f"No running deployment for '{function.name}' ({version.version_tag}) and the in-process "
                         "sandbox is disabled (set ALLOW_LOCAL_SANDBOX=true for local development only)")
        else:
            # 2. Cold Start Activation if this version's Deployment is not known to be warm.
            # The lock makes concurrent requests share one cold start instead of each scaling up.
            if version.version_tag not in _warm_versions.get(function.id, ()):
                lock = _cold_start_locks.setdefault(resource, asyncio.Lock())
                async with lock:
                    if version.version_tag not in _warm_versions.get(function.id, ()):
                        is_cold_start = True
                        cold_start_duration_ms = await self._cold_start(function, version, resource, has_k8s_deployment)

            # 3. Dispatch Invocation
            def _run_sandbox() -> Tuple[int, Any, Optional[str], float]:
                t0 = time.perf_counter()
                code, res, err = _execute_sandbox(version.code, payload)
                return code, res, err, (time.perf_counter() - t0) * 1000.0

            if has_k8s_deployment:
                executed_on = EXEC_K8S
                try:
                    inv_res = await asyncio.to_thread(
                        k8s_service.invoke_function, resource, payload, float(function.timeout_seconds) + 5.0
                    )
                    status_code = inv_res["status_code"]
                    result = inv_res["result"]
                    execution_duration_ms = inv_res.get("execution_time_ms", 0.0)
                    error_msg = inv_res.get("error")
                    # Only infrastructure errors (Pod not routable yet) may fall back; 500/504 from the
                    # function itself are real results and must not be re-executed elsewhere.
                    if status_code in (502, 503) and sandbox_allowed and version.code:
                        print(f"[RouterService Warning] K8s returned status {status_code}: {error_msg}. Falling back to sandbox.")
                        executed_on = EXEC_SANDBOX
                        status_code, result, error_msg, execution_duration_ms = _run_sandbox()
                except Exception as e:
                    if sandbox_allowed and version.code:
                        print(f"[RouterService Warning] Kubernetes invocation failed: {e}. Falling back to sandbox.")
                        executed_on = EXEC_SANDBOX
                        status_code, result, error_msg, execution_duration_ms = _run_sandbox()
                    else:
                        status_code = 502
                        error_msg = f"Invocation proxy error: {str(e)}"
            else:
                # Only reachable with ALLOW_LOCAL_SANDBOX (local development / tests)
                executed_on = EXEC_SANDBOX
                if version.code:
                    status_code, result, error_msg, execution_duration_ms = _run_sandbox()
                else:
                    status_code = 500
                    error_msg = f"No code version found for function '{function.name}'"

        total_duration_ms = cold_start_duration_ms + execution_duration_ms

        # 4. Record Metrics & Logs
        INVOCATION_COUNT.labels(
            function_name=function.name,
            status="success" if status_code == 200 else "error"
        ).inc()

        duration_type = "cold" if is_cold_start else "warm"
        INVOCATION_DURATION.labels(
            function_name=function.name,
            type=duration_type
        ).observe(total_duration_ms / 1000.0)

        log_data = {
            "function_id": function.id,
            "version_id": version.id,
            "request_id": request_id,
            "is_cold_start": is_cold_start,
            "cold_start_duration_ms": round(cold_start_duration_ms, 2),
            "execution_duration_ms": round(execution_duration_ms, 2),
            "total_duration_ms": round(total_duration_ms, 2),
            "executed_on": executed_on,
            "status_code": status_code,
            "payload_input": json.dumps(payload),
            "payload_output": json.dumps(result) if result is not None else "",
            "error_message": error_msg or ""
        }
        _ensure_log_worker()
        _log_queue.put_nowait((function.id, log_data))

        return {
            "request_id": request_id,
            "function_name": function.name,
            "version": version.version_tag,
            "status_code": status_code,
            "executed_on": executed_on,
            "is_cold_start": is_cold_start,
            "cold_start_duration_ms": round(cold_start_duration_ms, 2),
            "execution_duration_ms": round(execution_duration_ms, 2),
            "total_duration_ms": round(total_duration_ms, 2),
            "result": result,
            "error": error_msg
        }

router_service = RouterService()
