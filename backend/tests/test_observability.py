import pytest
from datetime import datetime, timedelta
from backend.app.api.observability import _compute_percentiles, _parse_time_range, _build_time_series
from backend.app.services.k8s_client import _parse_cpu_millicores, _parse_memory_mb, k8s_service
from backend.app.services.telemetry import (
    inflight_inc,
    inflight_dec,
    get_current_inflight,
    record_scaling_event,
    get_recent_scaling_events,
    record_invocation_error
)
from backend.app.models.invocation import InvocationLog

def test_compute_percentiles():
    # Empty
    empty = _compute_percentiles([])
    assert empty["avg"] == 0.0
    assert empty["p50"] == 0.0
    assert empty["p95"] == 0.0
    assert empty["p99"] == 0.0

    # Single value
    single = _compute_percentiles([100.0])
    assert single["avg"] == 100.0
    assert single["min"] == 100.0
    assert single["max"] == 100.0
    assert single["p50"] == 100.0
    assert single["p95"] == 100.0
    assert single["p99"] == 100.0

    # Range of 100 values: 1 to 100
    vals = [float(i) for i in range(1, 101)]
    p = _compute_percentiles(vals)
    assert p["min"] == 1.0
    assert p["max"] == 100.0
    assert p["avg"] == 50.5
    assert p["p50"] == 50.0 or p["p50"] == 51.0
    assert p["p95"] >= 94.0
    assert p["p99"] >= 98.0

def test_k8s_resource_parsers():
    # CPU
    assert _parse_cpu_millicores("500m") == 500.0
    assert _parse_cpu_millicores("1000m") == 1000.0
    assert _parse_cpu_millicores("1") == 1000.0
    assert _parse_cpu_millicores("2.5") == 2500.0
    assert _parse_cpu_millicores("25000000n") == 25.0
    assert _parse_cpu_millicores("") == 0.0

    # Memory
    assert _parse_memory_mb("256Mi") == 256.0
    assert _parse_memory_mb("512Mi") == 512.0
    assert _parse_memory_mb("1Gi") == 1024.0
    assert _parse_memory_mb("1024Ki") == 1.0
    assert _parse_memory_mb("") == 0.0

def test_inflight_concurrency_tracking():
    fn_name = "test-inflight-fn"
    assert get_current_inflight(fn_name) == 0
    
    inflight_inc(fn_name)
    assert get_current_inflight(fn_name) == 1
    
    inflight_inc(fn_name)
    assert get_current_inflight(fn_name) == 2
    
    inflight_dec(fn_name)
    assert get_current_inflight(fn_name) == 1
    
    inflight_dec(fn_name)
    assert get_current_inflight(fn_name) == 0

def test_scaling_events_recording():
    fn_id = 9999
    fn_name = "scale-test-fn"
    event = record_scaling_event(
        db=None,
        function_id=fn_id,
        function_name=fn_name,
        from_replicas=0,
        to_replicas=2,
        direction="UP",
        reason="Burst traffic spike"
    )
    assert event["function_id"] == fn_id
    assert event["direction"] == "UP"
    assert event["from_replicas"] == 0
    assert event["to_replicas"] == 2

    recent = get_recent_scaling_events(function_id=fn_id, limit=10)
    assert any(e["function_id"] == fn_id and e["direction"] == "UP" for e in recent)

def test_time_range_parser():
    now = datetime.utcnow()
    t15m = _parse_time_range("15m")
    assert (now - t15m).total_seconds() > 800 and (now - t15m).total_seconds() < 1000

    t1h = _parse_time_range("1h")
    assert (now - t1h).total_seconds() > 3500 and (now - t1h).total_seconds() < 3700

    tall = _parse_time_range("all")
    assert tall is None

def test_build_time_series():
    now = datetime.utcnow()
    # Create fake invocation logs
    dummy_logs = [
        InvocationLog(
            function_id=1,
            request_id="r1",
            is_cold_start=True,
            cold_start_duration_ms=500.0,
            execution_duration_ms=45.0,
            total_duration_ms=545.0,
            status_code=200,
            timestamp=now - timedelta(minutes=5)
        ),
        InvocationLog(
            function_id=1,
            request_id="r2",
            is_cold_start=False,
            cold_start_duration_ms=0.0,
            execution_duration_ms=25.0,
            total_duration_ms=25.0,
            status_code=200,
            timestamp=now - timedelta(minutes=3)
        ),
        InvocationLog(
            function_id=1,
            request_id="r3",
            is_cold_start=False,
            cold_start_duration_ms=0.0,
            execution_duration_ms=120.0,
            total_duration_ms=120.0,
            status_code=500,
            timestamp=now - timedelta(minutes=1)
        )
    ]

    ts = _build_time_series(dummy_logs, "15m")
    assert len(ts) == 15
    total_in_buckets = sum(b["invocations"] for b in ts)
    assert total_in_buckets == 3
    total_cold = sum(b["cold_starts"] for b in ts)
    assert total_cold == 1
    total_errors = sum(b["errors"] for b in ts)
    assert total_errors == 1

def test_k8s_graceful_handling_when_offline():
    # Calling get_pod_metrics when K8s is not available returns valid dict, never crashes
    metrics = k8s_service.get_pod_metrics("unknown-key")
    assert isinstance(metrics, dict)
    assert "pod_count" in metrics
    assert "cpu_utilization_pct" in metrics
    assert "memory_utilization_pct" in metrics
    assert "pods" in metrics
