import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.k8s_client import k8s_service

API = "/api/v1"

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def _user(client, prefix="u"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = client.post(f"{API}/auth/register", json={
        "username": username, "email": f"{username}@faas.com", "password": "Password123"})
    assert resp.status_code == 201, resp.text
    login = client.post(f"{API}/auth/login", data={"username": username, "password": "Password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}

def _code(tag):
    return f"def handler(event):\n    return {{'from': '{tag}'}}"

def _create(client, headers, name, tag):
    resp = client.post(f"{API}/functions/", headers=headers, json={"name": name, "code": _code(tag)})
    assert resp.status_code == 201, resp.text

def test_invoke_requires_auth(client):
    assert client.post(f"{API}/invoke/anything", json={}).status_code == 401

def test_same_function_name_is_isolated_between_users(client):
    a, b = _user(client, "a"), _user(client, "b")
    _create(client, a, "hello", "user-a")
    _create(client, b, "hello", "user-b")
    assert client.post(f"{API}/invoke/hello", headers=a, json={}).json()["result"] == {"from": "user-a"}
    assert client.post(f"{API}/invoke/hello", headers=b, json={}).json()["result"] == {"from": "user-b"}

def test_user_cannot_invoke_someone_elses_function(client):
    a, b = _user(client, "a"), _user(client, "b")
    name = f"private-{uuid.uuid4().hex[:6]}"
    _create(client, a, name, "secret")
    assert client.post(f"{API}/invoke/{name}", headers=b, json={}).status_code == 404

@pytest.mark.parametrize("bad", ["Bad_Name", "-lead", "trail-", "x" * 31, "has space"])
def test_function_name_must_be_dns_label(client, bad):
    resp = client.post(f"{API}/functions/", headers=_user(client), json={"name": bad, "code": _code("x")})
    assert resp.status_code == 422

def test_versioned_invoke_runs_requested_version(client):
    h = _user(client)
    name = f"ver-{uuid.uuid4().hex[:6]}"
    _create(client, h, name, "one")
    assert client.put(f"{API}/functions/{name}", headers=h, json={"code": _code("two")}).status_code == 200

    latest = client.post(f"{API}/invoke/{name}", headers=h, json={}).json()
    old = client.post(f"{API}/invoke/{name}/v1", headers=h, json={}).json()
    assert (latest["version"], latest["result"]) == ("v2", {"from": "two"})
    assert (old["version"], old["result"]) == ("v1", {"from": "one"})
    assert client.post(f"{API}/invoke/{name}/v9", headers=h, json={}).status_code == 404

def test_each_version_routes_to_its_own_deployment(client, monkeypatch):
    h = _user(client)
    name = f"k8s-{uuid.uuid4().hex[:6]}"
    _create(client, h, name, "one")
    client.put(f"{API}/functions/{name}", headers=h, json={"code": _code("two")})

    called = []
    monkeypatch.setattr(k8s_service, "has_deployment", lambda resource: True)
    monkeypatch.setattr(k8s_service, "scale_deployment", lambda resource, n: True)
    monkeypatch.setattr(k8s_service, "wait_for_ready_pod", lambda resource, t=30: "10.0.0.1")
    def fake_invoke(resource, payload, timeout=10.0):
        called.append(resource)
        return {"status_code": 200, "result": {}, "execution_time_ms": 1.0, "error": None}
    monkeypatch.setattr(k8s_service, "invoke_function", fake_invoke)

    client.post(f"{API}/invoke/{name}/v1", headers=h, json={})
    client.post(f"{API}/invoke/{name}", headers=h, json={})
    assert len(called) == 2 and called[0].endswith(f"-{name}-v1") and called[1].endswith(f"-{name}-v2")
    assert called[0].split("-")[0] == called[1].split("-")[0]  # same owner id prefix

def test_version_tag_not_reused_after_conflict(client):
    h = _user(client)
    name = f"tag-{uuid.uuid4().hex[:6]}"
    _create(client, h, name, "one")
    assert client.put(f"{API}/functions/{name}", headers=h, json={"code": _code("x"), "version_tag": "v1"}).status_code == 400

@pytest.mark.no_sandbox
def test_sandbox_disabled_by_default_refuses_to_exec(client):
    h = _user(client)
    name = f"nosb-{uuid.uuid4().hex[:6]}"
    _create(client, h, name, "one")
    data = client.post(f"{API}/invoke/{name}", headers=h, json={}).json()
    assert data["status_code"] == 503 and data["executed_on"] == "none" and data["result"] is None

def test_sandbox_reports_where_it_ran(client):
    h = _user(client)
    name = f"sb-{uuid.uuid4().hex[:6]}"
    _create(client, h, name, "one")
    assert client.post(f"{API}/invoke/{name}", headers=h, json={}).json()["executed_on"] == "sandbox"
