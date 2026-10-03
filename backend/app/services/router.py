import time
import uuid
import json
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, Gauge
from backend.app.core.config import settings
from backend.app.models.function import Function, FunctionVersion
from backend.app.models.invocation import InvocationLog
from backend.app.services.k8s_client import k8s_service

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

# In-memory caches and batch log queue to eliminate DB lock contention
_version_cache: Dict[str, Tuple[Any, float]] = {}
_log_queue: Optional[asyncio.Queue] = None
_log_worker_task: Optional[asyncio.Task] = None

def invalidate_router_cache(fn_id: Optional[int] = None):
    global _version_cache
    if fn_id:
        keys_to_del = [k for k in list(_version_cache.keys()) if k.startswith(f"{fn_id}:")]
        for k in keys_to_del:
            _version_cache.pop(k, None)
    else:
        _version_cache.clear()

def _execute_sandbox(code: str, payload: Any) -> Tuple[int, Any, Optional[str]]:
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
    async def invoke_function(
        self, 
        db: Session, 
        function: Function, 
        version_tag: Optional[str] = None, 
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a function, handling cold-start provisioning if scaled to zero.
        """
        request_id = str(uuid.uuid4())
        payload = payload or {}
        
        # 1. Resolve Function Version (with 15s in-memory cache)
        cache_key = f"{function.id}:{version_tag or 'latest'}"
        now_time = time.time()
        version = None
        if cache_key in _version_cache:
            c_ver, c_ts = _version_cache[cache_key]
            if (now_time - c_ts) < 15.0:
                version = c_ver

        if version is None:
            if version_tag:
                version = db.query(FunctionVersion).filter(
                    FunctionVersion.function_id == function.id,
                    FunctionVersion.version_tag == version_tag
                ).first()
                if not version:
                    raise ValueError(f"Version '{version_tag}' not found for function '{function.name}'")
            else:
                version = db.query(FunctionVersion).filter(
                    FunctionVersion.function_id == function.id
                ).order_by(FunctionVersion.created_at.desc()).first()
            if version:
                _version_cache[cache_key] = (version, now_time)

        is_cold_start = (function.active_replicas == 0 or function.status == "SCALED_TO_ZERO")
        cold_start_duration_ms = 0.0
        exec_start_time = time.perf_counter()

        has_k8s_deployment = await asyncio.to_thread(k8s_service.has_deployment, function.name)

        # 2. Cold Start Activation if replicas == 0
        if is_cold_start:
            COLD_START_COUNT.labels(function_name=function.name).inc()
            cold_start_begin = time.perf_counter()
            
            if has_k8s_deployment:
                print(f"[RouterService] Cold start detected for '{function.name}'. Scaling up to 1 replica in K8s...")
                await asyncio.to_thread(k8s_service.scale_deployment, function.name, 1)
                ready_ip = await asyncio.to_thread(k8s_service.wait_for_ready_pod, function.name, 30)
                if not ready_ip and k8s_service.k8s_available:
                    raise RuntimeError(f"Timed out waiting for Pod readiness for function '{function.name}'")
            else:
                print(f"[RouterService] Cold start for local sandbox function '{function.name}'...")
                
            cold_start_duration_ms = (time.perf_counter() - cold_start_begin) * 1000.0
            print(f"[RouterService] Cold start completed in {cold_start_duration_ms:.2f}ms")

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

        # 3. Dispatch Invocation
        status_code = 200
        result = None
        error_msg = None
        execution_duration_ms = 0.0

        if has_k8s_deployment:
            try:
                timeout_val = float(function.timeout_seconds)
                inv_res = await asyncio.to_thread(
                    k8s_service.invoke_function,
                    function.name,
                    payload,
                    timeout_val
                )
                status_code = inv_res["status_code"]
                result = inv_res["result"]
                execution_duration_ms = inv_res.get("execution_time_ms", 0.0)
                error_msg = inv_res.get("error")

                # If Kubernetes proxy returns 500 or 503 (e.g. pod still initializing or endpoints lag),
                # fallback to standalone execution sandbox if version code is present
                if status_code >= 500 and version and version.code:
                    print(f"[RouterService Warning] K8s returned status {status_code}: {error_msg}. Falling back to sandbox.")
                    sim_start = time.perf_counter()
                    status_code, result, error_msg = _execute_sandbox(version.code, payload)
                    execution_duration_ms = (time.perf_counter() - sim_start) * 1000.0
            except Exception as e:
                # If Kubernetes proxy fails, fallback to local sandbox if version code is present
                print(f"[RouterService Warning] Kubernetes invocation failed: {e}. Falling back to sandbox.")
                if version and version.code:
                    sim_start = time.perf_counter()
                    status_code, result, error_msg = _execute_sandbox(version.code, payload)
                    execution_duration_ms = (time.perf_counter() - sim_start) * 1000.0
                else:
                    status_code = 500
                    error_msg = f"Invocation proxy error: {str(e)}"
        else:
            # Standalone execution sandbox fallback (e.g. during local tests before k8s is up or mock functions)
            sim_start = time.perf_counter()
            if version and version.code:
                status_code, result, error_msg = _execute_sandbox(version.code, payload)
            else:
                status_code = 500
                error_msg = f"No code version found for function '{function.name}'"
            execution_duration_ms = (time.perf_counter() - sim_start) * 1000.0

        total_duration_ms = cold_start_duration_ms + execution_duration_ms

        # 5. Record Metrics & Logs
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
            "version_id": version.id if version else None,
            "request_id": request_id,
            "is_cold_start": is_cold_start,
            "cold_start_duration_ms": round(cold_start_duration_ms, 2),
            "execution_duration_ms": round(execution_duration_ms, 2),
            "total_duration_ms": round(total_duration_ms, 2),
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
            "version": version.version_tag if version else "v1",
            "status_code": status_code,
            "is_cold_start": is_cold_start,
            "cold_start_duration_ms": round(cold_start_duration_ms, 2),
            "execution_duration_ms": round(execution_duration_ms, 2),
            "total_duration_ms": round(total_duration_ms, 2),
            "result": result,
            "error": error_msg
        }

router_service = RouterService()
