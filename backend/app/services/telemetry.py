import time
from collections import deque
from datetime import datetime
from typing import Dict, Any, Optional, List, Deque
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy.orm import Session
from backend.app.models.function import ScalingEvent

# ---- Extended Prometheus Metric Definitions ----

# Invocations & Errors
FAAS_INVOCATIONS_TOTAL = Counter(
    "faas_invocations_total",
    "Total number of serverless function invocations",
    ["function_name", "status"]
)

FAAS_INVOCATION_ERRORS_TOTAL = Counter(
    "faas_invocation_errors_total",
    "Total invocation errors categorized by error type",
    ["function_name", "error_type"]
)

FAAS_COLD_STARTS_TOTAL = Counter(
    "faas_cold_starts_total",
    "Total number of cold starts",
    ["function_name"]
)

# Durations
FAAS_INVOCATION_DURATION = Histogram(
    "faas_invocation_duration_seconds",
    "Total invocation duration (cold-start + execution) in seconds",
    ["function_name", "type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

FAAS_EXECUTION_DURATION = Histogram(
    "faas_execution_duration_seconds",
    "Function execution duration excluding cold-start provisioning in seconds",
    ["function_name"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

FAAS_COLD_START_DURATION = Histogram(
    "faas_cold_start_duration_seconds",
    "Cold-start container provisioning duration in seconds",
    ["function_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

FAAS_BUILD_DURATION = Histogram(
    "faas_build_duration_seconds",
    "Docker container image build duration in seconds",
    ["function_name"],
    buckets=[1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

FAAS_DEPLOYMENT_DURATION = Histogram(
    "faas_deployment_duration_seconds",
    "Kubernetes deployment rollout duration in seconds",
    ["function_name"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Scaling & Concurrency Gauges
FAAS_ACTIVE_REPLICAS = Gauge(
    "faas_active_replicas",
    "Active replicas per function",
    ["function_name"]
)

FAAS_DESIRED_REPLICAS = Gauge(
    "faas_desired_replicas",
    "Desired replicas computed by autoscaler",
    ["function_name"]
)

FAAS_INFLIGHT_CURRENT = Gauge(
    "faas_inflight_current_requests",
    "Current active concurrent invocations in-flight",
    ["function_name"]
)

FAAS_INFLIGHT_PEAK = Gauge(
    "faas_inflight_peak_requests",
    "Peak requests in flight seen by autoscaler in last interval",
    ["function_name"]
)

FAAS_SCALE_EVENTS_TOTAL = Counter(
    "faas_scale_events_total",
    "Autoscaler scale operations",
    ["function_name", "direction"]
)

# Infrastructure Reliability Gauges
FAAS_POD_RESTARTS = Gauge(
    "faas_pod_restarts_total",
    "Total pod restarts observed in Kubernetes cluster",
    ["function_name"]
)

FAAS_POD_OOM_KILLS = Gauge(
    "faas_pod_oom_kills_total",
    "Total pod OOM kills observed in Kubernetes cluster",
    ["function_name"]
)

# ---- In-Memory Telemetry State ----
_current_inflight: Dict[str, int] = {}
_scaling_events_buffer: Deque[Dict[str, Any]] = deque(maxlen=200)

def inflight_inc(function_name: str) -> int:
    val = _current_inflight.get(function_name, 0) + 1
    _current_inflight[function_name] = val
    FAAS_INFLIGHT_CURRENT.labels(function_name=function_name).set(val)
    return val

def inflight_dec(function_name: str) -> int:
    val = max(0, _current_inflight.get(function_name, 1) - 1)
    if val == 0:
        _current_inflight.pop(function_name, None)
    else:
        _current_inflight[function_name] = val
    FAAS_INFLIGHT_CURRENT.labels(function_name=function_name).set(val)
    return val

def get_current_inflight(function_name: Optional[str] = None) -> int:
    if function_name:
        return _current_inflight.get(function_name, 0)
    return sum(_current_inflight.values())

def record_invocation_error(function_name: str, status_code: int, error_msg: Optional[str] = None):
    error_msg_lower = (error_msg or "").lower()
    if status_code == 504 or "timeout" in error_msg_lower or "timed out" in error_msg_lower:
        etype = "timeout"
    elif status_code == 429:
        etype = "rate_limited"
    elif status_code == 413:
        etype = "rejected_payload"
    elif status_code == 503:
        etype = "capacity_exhausted"
    elif status_code in (500, 502):
        etype = "runtime_error"
    else:
        etype = "system_error"
    FAAS_INVOCATION_ERRORS_TOTAL.labels(function_name=function_name, error_type=etype).inc()

def record_scaling_event(
    db: Optional[Session],
    function_id: int,
    function_name: str,
    from_replicas: int,
    to_replicas: int,
    direction: str,
    reason: str
) -> Dict[str, Any]:
    """Records a scaling operation to Prometheus, memory buffer, and the DB."""
    direction_norm = direction.upper()
    FAAS_SCALE_EVENTS_TOTAL.labels(function_name=function_name, direction=direction.lower()).inc()
    FAAS_ACTIVE_REPLICAS.labels(function_name=function_name).set(to_replicas)
    
    event_data = {
        "function_id": function_id,
        "function_name": function_name,
        "from_replicas": from_replicas,
        "to_replicas": to_replicas,
        "direction": direction_norm,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    _scaling_events_buffer.append(event_data)

    if db is not None:
        try:
            db_event = ScalingEvent(
                function_id=function_id,
                function_name=function_name,
                from_replicas=from_replicas,
                to_replicas=to_replicas,
                direction=direction_norm,
                reason=reason
            )
            db.add(db_event)
            db.commit()
        except Exception as e:
            print(f"[Telemetry Warning] Could not persist scaling event: {e}")
            try:
                db.rollback()
            except Exception:
                pass

    return event_data

def get_recent_scaling_events(function_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    events = list(_scaling_events_buffer)
    if function_id:
        events = [e for e in events if e.get("function_id") == function_id]
    events.reverse()
    return events[:limit]
