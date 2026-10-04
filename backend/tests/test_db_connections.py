import uuid
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.db import SessionLocal, get_db
from backend.app.services.k8s_client import k8s_service

API = "/api/v1"

def test_db_connection_is_released_before_the_slow_pod_call(monkeypatch):
    """
    A burst of invocations must not pin one DB connection each for the whole call (waiting for a Pod can take
    seconds), or the pool runs dry and every other request - including the dashboard's - times out.
    """
    sessions = []

    def tracking_get_db():
        db = SessionLocal()
        sessions.append(db)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = tracking_get_db
    try:
        with TestClient(app) as client:
            username = f"db_{uuid.uuid4().hex[:8]}"
            client.post(f"{API}/auth/register", json={"username": username, "email": f"{username}@faas.com", "password": "Password123"})
            tok = client.post(f"{API}/auth/login", data={"username": username, "password": "Password123"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {tok}"}
            name = f"db-{uuid.uuid4().hex[:6]}"
            assert client.post(f"{API}/functions/", headers=headers, json={"name": name, "code": "def handler(event):\n    return {}"}).status_code == 201

            held_during_pod_call = []
            monkeypatch.setattr(k8s_service, "has_deployment", lambda resource: True)
            monkeypatch.setattr(k8s_service, "scale_deployment", lambda resource, n: True)
            monkeypatch.setattr(k8s_service, "wait_for_ready_pod", lambda resource, t=30: "10.0.0.1")
            def fake_invoke(resource, payload, timeout=10.0):
                held_during_pod_call.extend(s.in_transaction() for s in sessions)
                return {"status_code": 200, "result": {}, "execution_time_ms": 1.0, "error": None}
            monkeypatch.setattr(k8s_service, "invoke_function", fake_invoke)

            sessions.clear()
            assert client.post(f"{API}/invoke/{name}", headers=headers, json={}).status_code == 200
            assert held_during_pod_call, "the Pod call was never made"
            assert not any(held_during_pod_call), "a DB connection was still held while calling the Pod"
    finally:
        app.dependency_overrides.pop(get_db, None)
