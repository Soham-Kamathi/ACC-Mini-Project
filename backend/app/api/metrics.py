from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from backend.app.core.db import get_db
from backend.app.core.security import get_current_user_id
from backend.app.models.function import Function
from backend.app.models.invocation import InvocationLog

router = APIRouter(tags=["Metrics & Observability"])

@router.get("/metrics")
def prometheus_metrics():
    """Prometheus scraper endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@router.get("/stats")
def get_dashboard_stats(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Provides high-level KPI stats for the frontend dashboard cards."""
    total_functions = db.query(Function).filter(Function.owner_id == user_id).count()
    active_functions = db.query(Function).filter(
        Function.owner_id == user_id, 
        Function.active_replicas > 0
    ).count()
    scaled_zero_functions = db.query(Function).filter(
        Function.owner_id == user_id, 
        Function.status == "SCALED_TO_ZERO"
    ).count()

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
        "active_replicas": active_functions,
        "scaled_to_zero_count": scaled_zero_functions,
        "total_invocations": total_invocations,
        "cold_start_count": cold_starts,
        "warm_invocation_count": warm_invocations,
        "cold_start_ratio_pct": round((cold_starts / total_invocations * 100), 1) if total_invocations > 0 else 0,
        "avg_execution_duration_ms": round(inv_stats.avg_exec_ms or 0, 2),
        "avg_cold_start_duration_ms": round(inv_stats.avg_cold_start_ms or 0, 2)
    }
