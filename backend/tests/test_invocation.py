import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_function_invocation():
    # Register & Create Function
    username = "invoker_user"
    password = "Password123"
    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@faas.com",
        "password": password
    })
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password
    })
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/v1/functions/", headers=headers, json={
        "name": "multiplier",
        "runtime": "python311",
        "code": "def handler(event):\n    return {'product': event.get('a', 1) * event.get('b', 1)}",
        "description": "Multiplies a and b"
    })

    # Invoke Function
    inv_resp = client.post("/api/v1/invoke/multiplier", headers=headers, json={"a": 6, "b": 7})
    assert inv_resp.status_code == 200
    data = inv_resp.json()
    assert data["status_code"] == 200
    assert data["result"] == {"product": 42}
    assert "cold_start_duration_ms" in data
    assert "execution_duration_ms" in data
    assert "total_duration_ms" in data
    assert data["executed_on"] == "sandbox"

    # Check metrics
    metrics_resp = client.get("/api/v1/metrics")
    assert metrics_resp.status_code == 200
    assert "faas_invocations_total" in metrics_resp.text
