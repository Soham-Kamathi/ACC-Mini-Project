import httpx
from .config import settings

class FaaSError(Exception):
    pass

async def invoke(code: str, stdin: str):
    if not settings.faas_public_id or not settings.faas_api_key:
        raise FaaSError("FaaS credentials are not configured. Add FAAS_PUBLIC_ID and FAAS_API_KEY to backend/.env.")
    
    base = settings.faas_base_url.rstrip("/")
    pub_id = settings.faas_public_id.strip()

    # Self-healing normalization: if the user pasted the entire endpoint into FAAS_BASE_URL
    if "/api/v1/f" in base:
        parts = base.split("/api/v1/f")
        base = parts[0].rstrip("/")
        suffix = parts[1].strip("/")
        if suffix:
            pub_id = suffix.split("/")[0]

    url = f"{base}/api/v1/f/{pub_id}"
    payload = {"language": "python", "code": code, "stdin": stdin, "timeout_seconds": 5}
    headers = {"X-API-Key": settings.faas_api_key, "Content-Type": "application/json", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient(timeout=settings.faas_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise FaaSError("The FaaS service timed out while processing this request.") from exc
    except httpx.HTTPError as exc:
        raise FaaSError("The FaaS service is unreachable. Check FAAS_BASE_URL and the service status.") from exc
    if response.status_code in (401, 403):
        raise FaaSError("The FaaS service rejected the API key.")
    if response.status_code >= 500:
        raise FaaSError(f"The FaaS infrastructure returned HTTP {response.status_code}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise FaaSError("The FaaS service returned malformed JSON.") from exc
    if response.status_code >= 400:
        raise FaaSError(body.get("detail", "FaaS invocation failed"))
    inner = body.get("result") if isinstance(body.get("result"), dict) else {}
    return {"request_id": body.get("request_id"), "status": inner.get("status", "success"),
            "stdout": inner.get("stdout", ""), "stderr": inner.get("stderr", ""),
            "exit_code": inner.get("exit_code"), "timed_out": inner.get("timed_out", False),
            "execution_time_ms": body.get("execution_duration_ms", inner.get("execution_time_ms", 0)),
            "total_duration_ms": body.get("total_duration_ms", 0), "cold_start_duration_ms": body.get("cold_start_duration_ms", 0),
            "is_cold_start": body.get("is_cold_start", False), "executed_on": body.get("executed_on", "unknown"),
            "invocation_id": body.get("request_id")}

