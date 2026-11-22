from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from backend.app.core.db import get_db
from backend.app.core.security import get_current_user_id
from backend.app.models.function import Function, FunctionVersion, ScalingEvent
from backend.app.models.invocation import InvocationLog
from backend.app.services.autoscaler import autoscaler
from backend.app.services.k8s_client import k8s_service
from backend.app.services.naming import function_key
from backend.app.services.telemetry import (
    get_current_inflight,
    get_recent_scaling_events,
    FAAS_POD_RESTARTS,
    FAAS_POD_OOM_KILLS
)

router = APIRouter(prefix="/observability", tags=["Observability & Deep Telemetry"])

def _format_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    s = dt.isoformat()
    if not s.endswith("Z") and "+" not in s[-6:]:
        return s + "Z"
    return s

def _parse_time_range(time_range: str) -> Optional[datetime]:
    now = datetime.utcnow()
    tr = (time_range or "1h").lower()
    if tr == "15m":
        return now - timedelta(minutes=15)
    elif tr == "1h":
        return now - timedelta(hours=1)
    elif tr == "6h":
        return now - timedelta(hours=6)
    elif tr == "24h":
        return now - timedelta(hours=24)
    elif tr == "all":
        return None
    return now - timedelta(hours=1)

def _get_window_seconds(time_range: str) -> float:
    tr = (time_range or "1h").lower()
    if tr == "15m":
        return 15 * 60.0
    elif tr == "1h":
        return 3600.0
    elif tr == "6h":
        return 6 * 3600.0
    elif tr == "24h":
        return 24 * 3600.0
    return 3600.0

def _compute_percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    vals = sorted(values)
    n = len(vals)
    return {
        "avg": round(sum(vals) / n, 2),
        "min": round(vals[0], 2),
        "max": round(vals[-1], 2),
        "p50": round(vals[int(0.50 * (n - 1))], 2),
        "p95": round(vals[int(0.95 * (n - 1))], 2),
        "p99": round(vals[int(0.99 * (n - 1))], 2)
    }

def _build_time_series(logs: List[InvocationLog], time_range: str) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    tr = (time_range or "1h").lower()

    if tr == "15m":
        num_buckets = 15
        bucket_sec = 60
        start_time = now - timedelta(minutes=15)
    elif tr == "1h":
        num_buckets = 30
        bucket_sec = 120
        start_time = now - timedelta(hours=1)
    elif tr == "6h":
        num_buckets = 24
        bucket_sec = 900
        start_time = now - timedelta(hours=6)
    elif tr == "24h":
        num_buckets = 24
        bucket_sec = 3600
        start_time = now - timedelta(hours=24)
    else:
        # All time
        if not logs:
            start_time = now - timedelta(hours=1)
            num_buckets = 15
            bucket_sec = 240
        else:
            earliest = min(l.timestamp for l in logs)
            span = max(60.0, (now - earliest).total_seconds())
            num_buckets = 20
            bucket_sec = max(60, int(span / num_buckets))
            start_time = now - timedelta(seconds=num_buckets * bucket_sec)

    buckets: List[Dict[str, Any]] = []
    bucket_logs: List[List[InvocationLog]] = [[] for _ in range(num_buckets)]

    for log in logs:
        delta = (log.timestamp - start_time).total_seconds()
        if 0 <= delta < (num_buckets * bucket_sec):
            idx = int(delta // bucket_sec)
            if idx < num_buckets:
                bucket_logs[idx].append(log)

    for i in range(num_buckets):
        b_time = start_time + timedelta(seconds=i * bucket_sec)
        b_logs = bucket_logs[i]
        b_total = len(b_logs)
        b_success = sum(1 for l in b_logs if l.status_code == 200)
        b_error = b_total - b_success
        b_cold = sum(1 for l in b_logs if l.is_cold_start)
        
        exec_times = [l.execution_duration_ms for l in b_logs]
        pcts = _compute_percentiles(exec_times)

        buckets.append({
            "timestamp": _format_utc_iso(b_time),
            "time_label": b_time.strftime("%H:%M" if bucket_sec < 86400 else "%m-%d %H:%M"),
            "invocations": b_total,
            "successes": b_success,
            "errors": b_error,
            "cold_starts": b_cold,
            "warm_starts": b_total - b_cold,
            "rps": round(b_total / bucket_sec, 3),
            "avg_latency_ms": pcts["avg"],
            "p50_latency_ms": pcts["p50"],
            "p95_latency_ms": pcts["p95"],
            "p99_latency_ms": pcts["p99"]
        })

    return buckets

@router.get("/overview")
def get_platform_observability(
    time_range: str = Query("1h", pattern="^(15m|1h|6h|24h|all)$"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Platform-Wide Observability Telemetry:
    Tracks total invocations, RPS, in-flight concurrency, success/error rates,
    granular latency percentiles (avg, p50, p95, p99), cold vs warm stats,
    replicas, pod cluster resources, scaling events, and time-series data.
    """
    since = _parse_time_range(time_range)
    window_sec = _get_window_seconds(time_range)

    # 1. Fetch User Functions
    functions = db.query(Function).filter(Function.owner_id == user_id).all()
    fn_map = {f.id: f for f in functions}
    fn_ids = list(fn_map.keys())

    total_functions = len(functions)
    active_replicas = 0
    scaled_zero_count = 0
    for f in functions:
        auto_rep = autoscaler.get_current_replicas(f.id)
        if auto_rep is not None:
            active_replicas += auto_rep
            if auto_rep == 0:
                scaled_zero_count += 1
        elif f.status == "SCALED_TO_ZERO":
            scaled_zero_count += 1
        elif k8s_service.k8s_available:
            r_status = k8s_service.get_replica_status(function_key(f.owner_id, f.name))
            if r_status is not None:
                reps = r_status.get("ready") or r_status.get("desired") or f.active_replicas or 0
                active_replicas += reps
                if reps == 0:
                    scaled_zero_count += 1
            else:
                active_replicas += (f.active_replicas or 0)
                if (f.active_replicas or 0) == 0:
                    scaled_zero_count += 1
        else:
            active_replicas += (f.active_replicas or 0)
            if (f.active_replicas or 0) == 0:
                scaled_zero_count += 1

    # 2. Query Invocation Logs in Window
    query = db.query(InvocationLog).filter(InvocationLog.function_id.in_(fn_ids)) if fn_ids else None
    if query and since:
        query = query.filter(InvocationLog.timestamp >= since)
    
    logs = query.order_by(InvocationLog.timestamp.asc()).all() if query else []

    total_invocations = len(logs)
    successful_invocations = sum(1 for l in logs if l.status_code == 200)
    failed_invocations = total_invocations - successful_invocations
    
    success_rate_pct = round((successful_invocations / total_invocations * 100.0), 2) if total_invocations > 0 else 100.0
    error_rate_pct = round((failed_invocations / total_invocations * 100.0), 2) if total_invocations > 0 else 0.0

    # Timeouts and Rejected Requests
    timeout_count = sum(1 for l in logs if l.status_code == 504 or "timeout" in (l.error_message or "").lower())
    rejected_count = sum(1 for l in logs if l.status_code in (413, 429, 503))

    # Latencies (execution and total)
    exec_durations = [l.execution_duration_ms for l in logs]
    total_durations = [l.total_duration_ms for l in logs]
    exec_pcts = _compute_percentiles(exec_durations)
    total_pcts = _compute_percentiles(total_durations)

    # Cold vs Warm Starts
    cold_logs = [l for l in logs if l.is_cold_start]
    warm_logs = [l for l in logs if not l.is_cold_start]
    cold_start_count = len(cold_logs)
    warm_start_count = len(warm_logs)
    cold_start_ratio_pct = round((cold_start_count / total_invocations * 100.0), 1) if total_invocations > 0 else 0.0
    
    avg_cold_start_ms = round(sum(l.cold_start_duration_ms for l in cold_logs) / cold_start_count, 2) if cold_logs else 0.0
    avg_warm_latency_ms = round(sum(l.execution_duration_ms for l in warm_logs) / warm_start_count, 2) if warm_logs else 0.0

    # Current RPS and In-Flight Requests
    platform_inflight = get_current_inflight()
    rps = round(total_invocations / window_sec, 3) if window_sec > 0 else 0.0

    # 3. Cluster Pod & Resource Metrics
    k8s_metrics = k8s_service.get_pod_metrics()
    # Sync Prometheus gauges
    for f in functions:
        FAAS_POD_RESTARTS.labels(function_name=f.name).set(k8s_metrics.get("restarts_total", 0))
        FAAS_POD_OOM_KILLS.labels(function_name=f.name).set(k8s_metrics.get("oom_kills_total", 0))

    # 4. Time Series Buckets
    time_series = _build_time_series(logs, time_range)

    # 5. Top Functions Leaderboard
    fn_breakdown = []
    for f in functions:
        f_logs = [l for l in logs if l.function_id == f.id]
        f_total = len(f_logs)
        f_succ = sum(1 for l in f_logs if l.status_code == 200)
        f_err = f_total - f_succ
        f_pcts = _compute_percentiles([l.execution_duration_ms for l in f_logs])
        f_cold = sum(1 for l in f_logs if l.is_cold_start)
        f_auto = autoscaler.get_current_replicas(f.id)
        f_reps = f_auto if f_auto is not None else (f.active_replicas or 0)

        fn_breakdown.append({
            "id": f.id,
            "name": f.name,
            "public_id": f.public_id,
            "runtime": f.runtime,
            "status": f.status,
            "active_replicas": f_reps,
            "total_invocations": f_total,
            "successful_invocations": f_succ,
            "failed_invocations": f_err,
            "cold_starts": f_cold,
            "success_rate_pct": round((f_succ / f_total * 100.0), 1) if f_total > 0 else 100.0,
            "avg_latency_ms": f_pcts["avg"],
            "p50_latency_ms": f_pcts["p50"],
            "p95_latency_ms": f_pcts["p95"],
            "p99_latency_ms": f_pcts["p99"],
            "current_inflight": get_current_inflight(f.name)
        })

    fn_breakdown.sort(key=lambda x: x["total_invocations"], reverse=True)

    # 6. Recent Platform Scaling Events
    recent_scaling = get_recent_scaling_events(limit=30)
    if not recent_scaling and fn_ids:
        # Fallback to DB scaling events
        db_events = db.query(ScalingEvent).filter(
            ScalingEvent.function_id.in_(fn_ids)
        ).order_by(ScalingEvent.timestamp.desc()).limit(30).all()
        recent_scaling = [
            {
                "function_id": e.function_id,
                "function_name": e.function_name,
                "from_replicas": e.from_replicas,
                "to_replicas": e.to_replicas,
                "direction": e.direction,
                "reason": e.reason,
                "timestamp": _format_utc_iso(e.timestamp)
            }
            for e in db_events
        ]

    return {
        "time_range": time_range,
        "summary": {
            "total_invocations": total_invocations,
            "successful_invocations": successful_invocations,
            "failed_invocations": failed_invocations,
            "success_rate_pct": success_rate_pct,
            "error_rate_pct": error_rate_pct,
            "timeout_count": timeout_count,
            "rejected_requests_count": rejected_count,
            "rps": rps,
            "in_flight_concurrent": platform_inflight,
            "avg_execution_latency_ms": exec_pcts["avg"],
            "p50_latency_ms": exec_pcts["p50"],
            "p95_latency_ms": exec_pcts["p95"],
            "p99_latency_ms": exec_pcts["p99"],
            "min_latency_ms": exec_pcts["min"],
            "max_latency_ms": exec_pcts["max"],
            "cold_start_count": cold_start_count,
            "warm_start_count": warm_start_count,
            "cold_start_ratio_pct": cold_start_ratio_pct,
            "avg_cold_start_duration_ms": avg_cold_start_ms,
            "avg_warm_latency_ms": avg_warm_latency_ms,
            "total_functions": total_functions,
            "active_replicas": active_replicas,
            "scaled_to_zero_count": scaled_zero_count,
            "k8s_connected": k8s_service.k8s_available,
            "pod_count": k8s_metrics.get("pod_count", 0),
            "ready_pod_count": k8s_metrics.get("ready_count", 0),
            "pod_restarts_total": k8s_metrics.get("restarts_total", 0),
            "oom_kills_total": k8s_metrics.get("oom_kills_total", 0),
            "cpu_utilization_pct": k8s_metrics.get("cpu_utilization_pct", 0.0),
            "memory_utilization_pct": k8s_metrics.get("memory_utilization_pct", 0.0),
            "cpu_usage_display": f"{k8s_metrics.get('cpu_usage_millicores', 0.0)}m / {k8s_metrics.get('cpu_limit_millicores', 0.0)}m",
            "memory_usage_display": f"{k8s_metrics.get('memory_usage_mb', 0.0)}Mi / {k8s_metrics.get('memory_limit_mb', 0.0)}Mi"
        },
        "time_series": time_series,
        "function_breakdown": fn_breakdown,
        "recent_scaling_events": recent_scaling
    }

@router.get("/functions")
def list_functions_observability_summary(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Returns quick observability catalog for function selection."""
    functions = db.query(Function).filter(Function.owner_id == user_id).all()
    results = []
    for f in functions:
        inv_count = db.query(func.count(InvocationLog.id)).filter(InvocationLog.function_id == f.id).scalar() or 0
        results.append({
            "id": f.id,
            "name": f.name,
            "public_id": f.public_id,
            "runtime": f.runtime,
            "status": f.status,
            "active_replicas": f.active_replicas,
            "min_replicas": f.min_replicas,
            "max_replicas": f.max_replicas,
            "total_invocations": inv_count,
            "last_invoked_at": _format_utc_iso(f.last_invoked_at)
        })
    return results

@router.get("/functions/{identifier}")
def get_function_deep_observability(
    identifier: str,
    time_range: str = Query("1h", pattern="^(15m|1h|6h|24h|all)$"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Per-Function Comprehensive Observability Telemetry:
    Tracks Invocation Metrics, Latency Percentiles (avg, min, max, p50, p95, p99),
    Autoscaling & Replicas, Infrastructure Pods & Resources, Reliability & Versions.
    """
    # Lookup by id, public_id, or name
    query = db.query(Function).filter(Function.owner_id == user_id)
    if identifier.isdigit():
        fn = query.filter(Function.id == int(identifier)).first()
    else:
        fn = query.filter((Function.public_id == identifier) | (Function.name == identifier)).first()

    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{identifier}' not found.")

    since = _parse_time_range(time_range)
    window_sec = _get_window_seconds(time_range)

    # 1. Invocation Logs for this Function
    log_query = db.query(InvocationLog).filter(InvocationLog.function_id == fn.id)
    if since:
        log_query = log_query.filter(InvocationLog.timestamp >= since)
    logs = log_query.order_by(InvocationLog.timestamp.asc()).all()

    total_invocations = len(logs)
    successful_invocations = sum(1 for l in logs if l.status_code == 200)
    failed_invocations = total_invocations - successful_invocations

    success_rate_pct = round((successful_invocations / total_invocations * 100.0), 2) if total_invocations > 0 else 100.0
    error_rate_pct = round((failed_invocations / total_invocations * 100.0), 2) if total_invocations > 0 else 0.0

    timeout_count = sum(1 for l in logs if l.status_code == 504 or "timeout" in (l.error_message or "").lower())
    rejected_count = sum(1 for l in logs if l.status_code in (413, 429, 503))

    # 2. Performance & Percentiles
    exec_durations = [l.execution_duration_ms for l in logs]
    total_durations = [l.total_duration_ms for l in logs]
    exec_pcts = _compute_percentiles(exec_durations)
    total_pcts = _compute_percentiles(total_durations)

    cold_logs = [l for l in logs if l.is_cold_start]
    warm_logs = [l for l in logs if not l.is_cold_start]
    cold_start_count = len(cold_logs)
    warm_start_count = len(warm_logs)
    cold_start_pct = round((cold_start_count / total_invocations * 100.0), 1) if total_invocations > 0 else 0.0

    avg_provisioning_ms = round(sum(l.cold_start_duration_ms for l in cold_logs) / cold_start_count, 2) if cold_logs else 0.0
    avg_warm_latency_ms = round(sum(l.execution_duration_ms for l in warm_logs) / warm_start_count, 2) if warm_logs else 0.0

    # Invocation Rate & In-Flight
    current_inflight = get_current_inflight(fn.name)
    invocation_rate_rps = round(total_invocations / window_sec, 3) if window_sec > 0 else 0.0

    # 3. Kubernetes Pods & Resource Telemetry
    fn_k8s_key = function_key(fn.owner_id, fn.name)
    pod_metrics = k8s_service.get_pod_metrics(function_key=fn_k8s_key)

    # 4. Scaling Metrics & History
    scaling_events = get_recent_scaling_events(function_id=fn.id, limit=30)
    if not scaling_events:
        db_scaling = db.query(ScalingEvent).filter(
            ScalingEvent.function_id == fn.id
        ).order_by(ScalingEvent.timestamp.desc()).limit(30).all()
        scaling_events = [
            {
                "function_id": e.function_id,
                "function_name": e.function_name,
                "from_replicas": e.from_replicas,
                "to_replicas": e.to_replicas,
                "direction": e.direction,
                "reason": e.reason,
                "timestamp": _format_utc_iso(e.timestamp)
            }
            for e in db_scaling
        ]

    scale_up_count = sum(1 for e in scaling_events if e.get("direction") == "UP")
    scale_down_count = sum(1 for e in scaling_events if e.get("direction") == "DOWN")

    requests_per_replica = round(total_invocations / max(fn.active_replicas, 1), 1)

    # 5. Reliability & Versions
    versions = db.query(FunctionVersion).filter(FunctionVersion.function_id == fn.id).order_by(FunctionVersion.id.desc()).all()
    version_items = [
        {
            "id": v.id,
            "version_tag": v.version_tag,
            "image_tag": v.image_tag,
            "is_active": v.is_active,
            "build_duration_ms": v.build_duration_ms,
            "deploy_duration_ms": v.deploy_duration_ms,
            "status": v.status or "READY",
            "status_message": v.status_message or "",
            "created_at": _format_utc_iso(v.created_at)
        }
        for v in versions
    ]

    ready_pods = pod_metrics.get("ready_count", 0)
    total_pods = pod_metrics.get("pod_count", 0)
    pod_readiness_pct = round((ready_pods / total_pods * 100.0), 1) if total_pods > 0 else (100.0 if fn.active_replicas == 0 else 0.0)

    # 6. Time Series
    time_series = _build_time_series(logs, time_range)

    # Replicas live resolution (autoscaler -> k8s -> db)
    auto_reps = autoscaler.get_current_replicas(fn.id)
    if auto_reps is not None:
        curr_replicas = auto_reps
    elif k8s_service.k8s_available:
        r_status = k8s_service.get_replica_status(fn_k8s_key)
        curr_replicas = (r_status.get("desired") or fn.active_replicas or 0) if r_status else (fn.active_replicas or 0)
        ready_pods = max(ready_pods, (r_status.get("ready") or 0) if r_status else 0)
    else:
        curr_replicas = fn.active_replicas or 0

    return {
        "time_range": time_range,
        "function": {
            "id": fn.id,
            "name": fn.name,
            "public_id": fn.public_id,
            "runtime": fn.runtime,
            "description": fn.description,
            "status": fn.status,
            "status_message": fn.status_message,
            "memory_limit": fn.memory_limit,
            "cpu_limit": fn.cpu_limit,
            "timeout_seconds": fn.timeout_seconds,
            "active_replicas": curr_replicas,
            "min_replicas": fn.min_replicas,
            "max_replicas": fn.max_replicas,
            "target_concurrency": fn.target_concurrency,
            "last_invoked_at": _format_utc_iso(fn.last_invoked_at),
            "created_at": _format_utc_iso(fn.created_at)
        },
        "invocation_metrics": {
            "total_invocations": total_invocations,
            "successful_invocations": successful_invocations,
            "failed_invocations": failed_invocations,
            "success_rate_pct": success_rate_pct,
            "error_rate_pct": error_rate_pct,
            "invocation_rate_rps": invocation_rate_rps,
            "in_flight_requests": current_inflight,
            "timeout_count": timeout_count,
            "rejected_requests_count": rejected_count
        },
        "performance_metrics": {
            "avg_latency_ms": exec_pcts["avg"],
            "min_latency_ms": exec_pcts["min"],
            "max_latency_ms": exec_pcts["max"],
            "p50_latency_ms": exec_pcts["p50"],
            "p95_latency_ms": exec_pcts["p95"],
            "p99_latency_ms": exec_pcts["p99"],
            "avg_total_duration_ms": total_pcts["avg"],
            "cold_start_count": cold_start_count,
            "warm_start_count": warm_start_count,
            "cold_start_percentage": cold_start_pct,
            "avg_provisioning_duration_ms": avg_provisioning_ms,
            "avg_warm_latency_ms": avg_warm_latency_ms
        },
        "scaling_metrics": {
            "current_replicas": curr_replicas,
            "desired_replicas": curr_replicas,
            "ready_replicas": ready_pods,
            "min_replicas": fn.min_replicas,
            "max_replicas": fn.max_replicas,
            "target_concurrency": fn.target_concurrency,
            "scale_up_count": scale_up_count,
            "scale_down_count": scale_down_count,
            "scaling_delay_ms": avg_provisioning_ms,
            "requests_per_replica": requests_per_replica,
            "recent_scaling_events": scaling_events
        },
        "resource_metrics": {
            "configured_cpu_limit": fn.cpu_limit,
            "configured_memory_limit": fn.memory_limit,
            "cpu_usage_millicores": pod_metrics.get("cpu_usage_millicores", 0.0),
            "cpu_limit_millicores": pod_metrics.get("cpu_limit_millicores", 0.0),
            "cpu_utilization_pct": pod_metrics.get("cpu_utilization_pct", 0.0),
            "memory_usage_mb": pod_metrics.get("memory_usage_mb", 0.0),
            "memory_limit_mb": pod_metrics.get("memory_limit_mb", 0.0),
            "memory_utilization_pct": pod_metrics.get("memory_utilization_pct", 0.0),
            "peak_memory_mb": pod_metrics.get("peak_memory_mb", 0.0),
            "pod_restarts": pod_metrics.get("restarts_total", 0),
            "oom_kills": pod_metrics.get("oom_kills_total", 0),
            "cpu_throttling_status": "Normal (No throttling events)" if pod_metrics.get("oom_kills_total", 0) == 0 else "Throttling / OOM pressure detected",
            "k8s_available": pod_metrics.get("k8s_available", False),
            "metrics_server_available": pod_metrics.get("metrics_server_available", False),
            "pods": pod_metrics.get("pods", [])
        },
        "reliability_and_deployment": {
            "health_status": fn.status,
            "pod_readiness_pct": pod_readiness_pct,
            "runtime_errors_count": failed_invocations - timeout_count - rejected_count,
            "timeouts_count": timeout_count,
            "versions": version_items
        },
        "time_series": time_series
    }

@router.get("/functions/{identifier}/history")
def get_function_invocation_history(
    identifier: str,
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Retrieves detailed invocation logs for the selected function."""
    query = db.query(Function).filter(Function.owner_id == user_id)
    if identifier.isdigit():
        fn = query.filter(Function.id == int(identifier)).first()
    else:
        fn = query.filter((Function.public_id == identifier) | (Function.name == identifier)).first()

    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{identifier}' not found.")

    logs = db.query(InvocationLog).filter(
        InvocationLog.function_id == fn.id
    ).order_by(InvocationLog.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": l.id,
            "request_id": l.request_id,
            "timestamp": _format_utc_iso(l.timestamp),
            "status_code": l.status_code,
            "is_cold_start": l.is_cold_start,
            "cold_start_duration_ms": l.cold_start_duration_ms,
            "execution_duration_ms": l.execution_duration_ms,
            "total_duration_ms": l.total_duration_ms,
            "executed_on": l.executed_on,
            "payload_input": l.payload_input,
            "payload_output": l.payload_output,
            "error_message": l.error_message
        }
        for l in logs
    ]

@router.get("/scaling-events")
def get_all_scaling_events(
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Retrieves platform scaling operations."""
    user_fn_ids = [f.id for f in db.query(Function.id).filter(Function.owner_id == user_id).all()]
    events = [e for e in get_recent_scaling_events(limit=limit) if e.get("function_id") in user_fn_ids]
    if not events and user_fn_ids:
        db_events = db.query(ScalingEvent).filter(
            ScalingEvent.function_id.in_(user_fn_ids)
        ).order_by(ScalingEvent.timestamp.desc()).limit(limit).all()
        events = [
            {
                "function_id": e.function_id,
                "function_name": e.function_name,
                "from_replicas": e.from_replicas,
                "to_replicas": e.to_replicas,
                "direction": e.direction,
                "reason": e.reason,
                "timestamp": _format_utc_iso(e.timestamp)
            }
            for e in db_events
        ]
    return events
