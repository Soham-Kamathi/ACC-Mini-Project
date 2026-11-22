from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from backend.app.core.db import get_db, SessionLocal
from backend.app.core.security import get_current_user_id
from backend.app.models.function import Function
from backend.app.models.invocation import InvocationLog
from backend.app.services.k8s_client import k8s_service
from backend.app.services.naming import function_key
from backend.app.services.autoscaler import autoscaler
from backend.app.services.telemetry import (
    FAAS_ACTIVE_REPLICAS,
    FAAS_INFLIGHT_CURRENT,
    FAAS_POD_RESTARTS,
    FAAS_POD_OOM_KILLS,
    get_current_inflight
)

router = APIRouter(tags=["Metrics & Observability"])

@router.get("/metrics")
def prometheus_metrics():
    """Prometheus scraper endpoint with real-time synchronized cluster and function gauges."""
    try:
        with SessionLocal() as db:
            functions = db.query(Function).all()
            for fn in functions:
                auto_reps = autoscaler.get_current_replicas(fn.id)
                current_reps = auto_reps if auto_reps is not None else (fn.active_replicas or 0)
                FAAS_ACTIVE_REPLICAS.labels(function_name=fn.name).set(current_reps)
                FAAS_INFLIGHT_CURRENT.labels(function_name=fn.name).set(get_current_inflight(fn.name))
                if k8s_service.k8s_available:
                    pm = k8s_service.get_pod_metrics(function_key=function_key(fn.owner_id, fn.name))
                    FAAS_POD_RESTARTS.labels(function_name=fn.name).set(pm.get("restarts_total", 0))
                    FAAS_POD_OOM_KILLS.labels(function_name=fn.name).set(pm.get("oom_kills_total", 0))
    except Exception as e:
        print(f"[Prometheus Scrape Sync Error] {e}")

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@router.get("/stats")
def get_dashboard_stats(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Provides high-level KPI stats for the frontend dashboard cards."""
    user_functions = db.query(Function).filter(Function.owner_id == user_id).all()
    total_functions = len(user_functions)

    # Compute live total active container pods / replicas
    total_active_pods = 0
    scaled_zero_functions = 0
    for fn in user_functions:
        auto_reps = autoscaler.get_current_replicas(fn.id)
        if auto_reps is not None:
            total_active_pods += auto_reps
            if auto_reps == 0:
                scaled_zero_functions += 1
        elif fn.status == "SCALED_TO_ZERO":
            scaled_zero_functions += 1
        elif k8s_service.k8s_available:
            r_status = k8s_service.get_replica_status(function_key(fn.owner_id, fn.name))
            if r_status is not None:
                reps = r_status.get("ready") or r_status.get("desired") or fn.active_replicas or 0
                total_active_pods += reps
                if reps == 0:
                    scaled_zero_functions += 1
            else:
                total_active_pods += (fn.active_replicas or 0)
                if (fn.active_replicas or 0) == 0:
                    scaled_zero_functions += 1
        else:
            total_active_pods += (fn.active_replicas or 0)
            if (fn.active_replicas or 0) == 0:
                scaled_zero_functions += 1

    # Aggregate invocation statistics
    inv_stats = db.query(
        func.count(InvocationLog.id).label("total_invocations"),
        func.sum(cast(InvocationLog.is_cold_start, Integer)).label("cold_starts"),
        func.avg(InvocationLog.execution_duration_ms).label("avg_exec_ms"),
        func.avg(InvocationLog.cold_start_duration_ms).label("avg_cold_start_ms")
    ).join(Function).filter(Function.owner_id == user_id).first()

    total_invocations = inv_stats.total_invocations or 0
    cold_starts = inv_stats.cold_starts or 0
    warm_invocations = total_invocations - cold_starts

    return {
        "total_functions": total_functions,
        "active_replicas": total_active_pods,
        "scaled_to_zero_count": scaled_zero_functions,
        "total_invocations": total_invocations,
        "cold_start_count": cold_starts,
        "warm_invocation_count": warm_invocations,
        "cold_start_ratio_pct": round((cold_starts / total_invocations * 100), 1) if total_invocations > 0 else 0,
        "avg_execution_duration_ms": round(inv_stats.avg_exec_ms or 0, 2),
        "avg_cold_start_duration_ms": round(inv_stats.avg_cold_start_ms or 0, 2)
    }
