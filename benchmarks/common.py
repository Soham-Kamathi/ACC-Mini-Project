"""Shared helpers for the benchmark scripts."""
import time
import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"

FIB_CODE = """def handler(event):
    n = event.get("n", 30)
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"fibonacci": a, "n": n}
"""

def register_user(prefix="benchuser"):
    username = f"{prefix}_{int(time.time())}"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "username": username, "email": f"{username}@test.com", "password": "Password123!"})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}

def create_function(headers, name, code=FIB_CODE):
    resp = requests.post(f"{BASE_URL}/functions/", headers=headers, json={
        "name": name, "runtime": "python311", "code": code,
        "description": "Fibonacci benchmark function"})
    resp.raise_for_status()

def wait_for_status(headers, name, wanted, timeout=180):
    """Polls the function until its status is in `wanted` (a set of status strings)."""
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = requests.get(f"{BASE_URL}/functions/{name}", headers=headers).json().get("status")
        if status in wanted:
            return status
        if status == "ERROR":
            raise RuntimeError(f"Function '{name}' build/deploy failed")
        time.sleep(2)
    raise TimeoutError(f"Function '{name}' did not reach {wanted} (last status: {status})")

def require_k8s(executed_on_values):
    """Benchmark numbers are only meaningful if every call ran in a Pod."""
    bad = [v for v in executed_on_values if v != "k8s"]
    if bad:
        raise SystemExit(
            f"INVALID RUN: {len(bad)}/{len(executed_on_values)} invocations did not run on Kubernetes "
            f"(executed_on={sorted(set(bad))}). Check the cluster and run the backend with ALLOW_LOCAL_SANDBOX=false.")
