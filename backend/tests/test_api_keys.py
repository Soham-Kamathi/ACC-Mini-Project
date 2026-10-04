import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.api_keys import rate_limiter
from backend.app.core.config import settings

API = "/api/v1"

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter.reset()

def _user(client):
    username = f"k_{uuid.uuid4().hex[:8]}"
    client.post(f"{API}/auth/register", json={"username": username, "email": f"{username}@faas.com", "password": "Password123"})
    tok = client.post(f"{API}/auth/login", data={"username": username, "password": "Password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

def _code(tag):
    return f"def handler(event):\n    return {{'from': '{tag}'}}"

def _fn(client, h, tag="one"):
    name = f"fn-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{API}/functions/", headers=h, json={"name": name, "code": _code(tag)})
    assert r.status_code == 201, r.text
    return name, r.json()["public_id"]

def _key(client, h, name, **body):
    r = client.post(f"{API}/functions/{name}/keys", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()

def test_key_is_shown_once_and_only_hash_listed(client):
    h = _user(client)
    name, public_id = _fn(client, h)
    created = _key(client, h, name, label="mobile app")
    assert created["api_key"].startswith("fk_") and created["endpoint"] == f"{API}/f/{public_id}"
    listed = client.get(f"{API}/functions/{name}/keys", headers=h).json()
    assert len(listed) == 1 and "api_key" not in listed[0] and "key_hash" not in listed[0]
    assert created["api_key"].startswith(listed[0]["key_prefix"])

def test_call_public_endpoint_with_key_header(client):
    h = _user(client)
    name, public_id = _fn(client, h, "pub")
    key = _key(client, h, name)["api_key"]
    r = client.post(f"{API}/f/{public_id}", headers={"X-API-Key": key}, json={})
    assert r.status_code == 200 and r.json()["result"] == {"from": "pub"}
    # also valid as a bearer token and on the name-based route
    assert client.post(f"{API}/f/{public_id}", headers={"Authorization": f"Bearer {key}"}, json={}).status_code == 200
    assert client.post(f"{API}/invoke/{name}", headers={"X-API-Key": key}, json={}).status_code == 200

def test_owner_jwt_still_works_on_both_routes(client):
    h = _user(client)
    name, public_id = _fn(client, h)
    assert client.post(f"{API}/invoke/{name}", headers=h, json={}).status_code == 200
    assert client.post(f"{API}/f/{public_id}", headers=h, json={}).status_code == 200

def test_missing_wrong_and_revoked_keys_are_rejected(client):
    h = _user(client)
    name, public_id = _fn(client, h)
    assert client.post(f"{API}/f/{public_id}", json={}).status_code == 401
    assert client.post(f"{API}/f/{public_id}", headers={"X-API-Key": "fk_nope"}, json={}).status_code == 401
    created = _key(client, h, name)
    assert client.delete(f"{API}/functions/{name}/keys/{created['id']}", headers=h).status_code == 204
    assert client.post(f"{API}/f/{public_id}", headers={"X-API-Key": created["api_key"]}, json={}).status_code == 401

def test_key_cannot_call_another_function(client):
    h = _user(client)
    name_a, pub_a = _fn(client, h)
    name_b, pub_b = _fn(client, h)
    key_a = _key(client, h, name_a)["api_key"]
    assert client.post(f"{API}/f/{pub_b}", headers={"X-API-Key": key_a}, json={}).status_code == 404
    assert client.post(f"{API}/invoke/{name_b}", headers={"X-API-Key": key_a}, json={}).status_code == 404

def test_key_is_not_a_login_token(client):
    h = _user(client)
    name, _ = _fn(client, h)
    key = _key(client, h, name)["api_key"]
    for path in (f"/functions/{name}", f"/functions/{name}/keys", "/functions/"):
        assert client.get(f"{API}{path}", headers={"X-API-Key": key}).status_code == 401

def test_other_users_cannot_manage_or_use_keys(client):
    owner, intruder = _user(client), _user(client)
    name, public_id = _fn(client, owner)
    created = _key(client, owner, name)
    assert client.get(f"{API}/functions/{name}/keys", headers=intruder).status_code == 404
    assert client.post(f"{API}/functions/{name}/keys", headers=intruder, json={}).status_code == 404
    assert client.delete(f"{API}/functions/{name}/keys/{created['id']}", headers=intruder).status_code == 404
    assert client.post(f"{API}/f/{public_id}", headers=intruder, json={}).status_code == 404

def test_rotate_revokes_old_key_and_keeps_pin(client):
    h = _user(client)
    name, public_id = _fn(client, h)
    old = _key(client, h, name, label="svc", version_tag="v1")
    new = client.post(f"{API}/functions/{name}/keys/{old['id']}/rotate", headers=h).json()
    assert new["label"] == "svc" and new["version_tag"] == "v1" and new["api_key"] != old["api_key"]
    assert client.post(f"{API}/f/{public_id}", headers={"X-API-Key": old["api_key"]}, json={}).status_code == 401
    assert client.post(f"{API}/f/{public_id}", headers={"X-API-Key": new["api_key"]}, json={}).status_code == 200

def test_version_pinned_key(client):
    h = _user(client)
    name, public_id = _fn(client, h, "one")
    client.put(f"{API}/functions/{name}", headers=h, json={"code": _code("two")})
    pinned = _key(client, h, name, version_tag="v1")["api_key"]
    unpinned = _key(client, h, name)["api_key"]
    k = {"X-API-Key": pinned}
    assert client.post(f"{API}/f/{public_id}", headers=k, json={}).json()["result"] == {"from": "one"}
    assert client.post(f"{API}/f/{public_id}/v2", headers=k, json={}).status_code == 403
    assert client.post(f"{API}/f/{public_id}", headers={"X-API-Key": unpinned}, json={}).json()["result"] == {"from": "two"}
    assert client.post(f"{API}/functions/{name}/keys", headers=h, json={"version_tag": "v9"}).status_code == 404

def test_rate_limit_per_key(client, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_RATE_LIMIT_PER_MINUTE", 3)
    h = _user(client)
    name, public_id = _fn(client, h)
    k = {"X-API-Key": _key(client, h, name)["api_key"]}
    codes = [client.post(f"{API}/f/{public_id}", headers=k, json={}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    # the owner's JWT is not subject to the key limit
    assert client.post(f"{API}/f/{public_id}", headers=h, json={}).status_code == 200

def test_oversized_payload_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PAYLOAD_BYTES", 100)
    h = _user(client)
    name, public_id = _fn(client, h)
    assert client.post(f"{API}/f/{public_id}", headers=h, json={"blob": "x" * 500}).status_code == 413

def test_key_limit_per_function(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_API_KEYS_PER_FUNCTION", 2)
    h = _user(client)
    name, _ = _fn(client, h)
    _key(client, h, name); _key(client, h, name)
    assert client.post(f"{API}/functions/{name}/keys", headers=h, json={}).status_code == 400
