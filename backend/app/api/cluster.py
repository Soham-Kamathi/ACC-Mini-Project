from fastapi import APIRouter
from backend.app.services.builder import builder_service
from backend.app.services.k8s_client import k8s_service
from backend.app.services.controller import faas_controller
from backend.app.core.config import settings

router = APIRouter(prefix="/cluster", tags=["Cluster & System"])

@router.get("/status")
def get_cluster_status():
    nodes_count = 0
    k8s_info = "Disconnected"
    if k8s_service.k8s_available:
        try:
            nodes = k8s_service.core_v1.list_node()
            nodes_count = len(nodes.items)
            k8s_info = f"Connected ({nodes_count} node(s))"
        except Exception:
            k8s_info = "Connected (permissions limited)"

    return {
        "kubernetes": {
            "status": "online" if k8s_service.k8s_available else "offline",
            "info": k8s_info,
            "namespace": settings.K8S_NAMESPACE,
            "nodes_count": nodes_count
        },
        "docker": {
            "status": "online" if builder_service.docker_available else "offline",
            "registry": settings.DOCKER_REGISTRY
        },
        "controller": {
            "scale_to_zero_reaper": "running" if faas_controller.is_running else "stopped",
            "idle_timeout_seconds": settings.IDLE_TIMEOUT_SECONDS,
            "reaper_interval_seconds": settings.REAPER_INTERVAL_SECONDS
        }
    }
