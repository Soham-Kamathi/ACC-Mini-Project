import pytest
from backend.app.core.config import settings
from backend.app.services.builder import builder_service
from backend.app.services.k8s_client import k8s_service

@pytest.fixture(autouse=True)
def hermetic_runtime(request, monkeypatch):
    """
    Tests must not depend on a live Docker/Kubernetes: building and deploying are stubbed, no Deployment
    exists, and the in-process sandbox is enabled unless a test opts out with @pytest.mark.no_sandbox.
    Tests that need a Deployment re-patch k8s_service themselves.
    """
    monkeypatch.setattr(builder_service, "build_function_image",
                        lambda username, function_name, version_tag, **kw: f"test/{username}/{function_name}:{version_tag}")
    monkeypatch.setattr(k8s_service, "deploy_function", lambda *a, **kw: True)
    monkeypatch.setattr(k8s_service, "has_deployment", lambda resource: False)
    monkeypatch.setattr(k8s_service, "wait_for_ready_pod", lambda resource, timeout_seconds=30: "127.0.0.1")
    monkeypatch.setattr(k8s_service, "scale_function", lambda function_key, replicas: None)
    monkeypatch.setattr(k8s_service, "delete_function", lambda function_key: True)
    monkeypatch.setattr(settings, "ALLOW_LOCAL_SANDBOX", "no_sandbox" not in request.keywords)
