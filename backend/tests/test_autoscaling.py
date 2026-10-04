import asyncio
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.db import engine
from backend.app.services.autoscaler import autoscaler
from backend.app.services.controller import faas_controller
from backend.app.services.k8s_client import k8s_service

API = "/api/v1"
CODE = "def handler(event):\n    return {}"

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def user(client):
    username = f"as_{uuid.uuid4().hex[:8]}"
    client.post(f"{API}/auth/register", json={"username": username, "email": f"{username}@faas.com", "password": "Password123"})
    tok = client.post(f"{API}/auth/login", data={"username": username, "password": "Password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}

@pytest.fixture
def fake_k8s(monkeypatch):
    """Replica counts live in a dict; scale calls are recorded."""
    state = {"calls": []}
    monkeypatch.setattr(k8s_service, "get_replicas", lambda resource: state.get(resource))
    def scale(resource, n):
        state["calls"].append((resource, n))
        state[resource] = n
        return True
    monkeypatch.setattr(k8s_service, "scale_deployment", scale)
    return state

def _create(client, headers, **scaling):
    name = f"as-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{API}/functions/", headers=headers, json={"name": name, "code": CODE, **scaling})
    assert r.status_code == 201, r.text
    # the create-time build task already registered the real v1 Deployment; tests drive their own resources
    autoscaler.forget_function(r.json()["id"])
    return name, r.json()["id"]

def _tick(now):
    asyncio.run(autoscaler.tick(now=now))

def _load(stack, resource, n):
    for _ in range(n):
        stack.enter_context(autoscaler.in_flight(resource))

def _replicas_in_api(client, headers, name):
    return client.get(f"{API}/functions/{name}", headers=headers).json()["active_replicas"]

def test_defaults_and_validation(client, user):
    name, _ = _create(client, user)
    fn = client.get(f"{API}/functions/{name}", headers=user).json()
    assert (fn["min_replicas"], fn["max_replicas"], fn["target_concurrency"]) == (0, 5, 5)
    bad = client.post(f"{API}/functions/", headers=user, json={"name": "bad-one", "code": CODE, "min_replicas": 6, "max_replicas": 2})
    assert bad.status_code == 422
    assert client.post(f"{API}/functions/", headers=user, json={"name": "bad-two", "code": CODE, "max_replicas": 99}).status_code == 422

def test_update_scaling_and_reject_min_above_max(client, user):
    name, _ = _create(client, user)
    ok = client.put(f"{API}/functions/{name}", headers=user, json={"min_replicas": 1, "max_replicas": 8, "target_concurrency": 10})
    assert ok.status_code == 200
    assert (ok.json()["min_replicas"], ok.json()["max_replicas"], ok.json()["target_concurrency"]) == (1, 8, 10)
    assert client.put(f"{API}/functions/{name}", headers=user, json={"min_replicas": 9}).status_code == 400
    scaling = client.get(f"{API}/functions/{name}/scaling", headers=user).json()
    assert scaling["max_replicas"] == 8 and scaling["target_concurrency"] == 10

def test_scales_up_with_load_and_respects_max(client, user, fake_k8s):
    name, fid = _create(client, user, max_replicas=5, target_concurrency=5)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    with ExitStack() as load:
        _load(load, res, 12)
        _tick(now=1000.0)
        assert fake_k8s[res] == 3          # ceil(12 / 5)
        _load(load, res, 88)               # 100 in flight
        _tick(now=1002.0)
        assert fake_k8s[res] == 5          # capped at max_replicas
    assert _replicas_in_api(client, user, name) == 5
    autoscaler.forget_function(fid)

def test_burst_between_ticks_is_not_missed(client, user, fake_k8s):
    _, fid = _create(client, user)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    with ExitStack() as burst:
        _load(burst, res, 20)
    # all 20 requests finished before the tick, but the peak is remembered
    _tick(now=2000.0)
    assert fake_k8s[res] == 4
    autoscaler.forget_function(fid)

def test_scale_down_waits_for_stabilization_window(client, user, fake_k8s, monkeypatch):
    monkeypatch.setattr(settings, "SCALE_DOWN_STABILIZATION_SECONDS", 30)
    _, fid = _create(client, user)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    with ExitStack() as load:
        _load(load, res, 25)
        _tick(now=3000.0)
    assert fake_k8s[res] == 5
    _tick(now=3010.0)                      # lull, but the burst is still inside the 30s window
    assert fake_k8s[res] == 5
    _tick(now=3031.0)                      # window has passed -> back to the floor of 1
    assert fake_k8s[res] == 1
    autoscaler.forget_function(fid)

def test_min_replicas_is_a_floor(client, user, fake_k8s):
    _, fid = _create(client, user, min_replicas=3, max_replicas=5)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    _tick(now=4000.0)                      # no traffic at all
    assert fake_k8s[res] == 3
    autoscaler.forget_function(fid)

def test_fixed_replica_count_when_min_equals_max(client, user, fake_k8s):
    _, fid = _create(client, user, min_replicas=4, max_replicas=4)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    with ExitStack() as load:
        _load(load, res, 200)
        _tick(now=5000.0)
        assert fake_k8s[res] == 4
    _tick(now=5100.0)
    assert fake_k8s[res] == 4
    autoscaler.forget_function(fid)

def test_forgotten_function_is_no_longer_scaled(client, user, fake_k8s):
    _, fid = _create(client, user)
    res = f"res-{uuid.uuid4().hex[:6]}"
    autoscaler.track(fid, res, current=1)
    autoscaler.forget_function(fid)
    with ExitStack() as load:
        _load(load, res, 50)
        _tick(now=6000.0)
    assert res not in fake_k8s

def test_reaper_never_scales_to_zero_when_min_replicas_is_set(client, user, monkeypatch):
    keep, keep_id = _create(client, user, min_replicas=1)
    idle, idle_id = _create(client, user, min_replicas=0)
    old = datetime.utcnow() - timedelta(hours=1)
    with engine.begin() as conn:
        for fid in (keep_id, idle_id):
            conn.execute(text("UPDATE functions SET active_replicas = 1, status = 'READY', created_at = :t, last_invoked_at = NULL WHERE id = :i"),
                         {"t": old, "i": fid})
    scaled = []
    monkeypatch.setattr(k8s_service, "scale_function", lambda key, n: scaled.append((key, n)) or True)
    asyncio.run(faas_controller.check_idle_functions())
    keys = {k for k, _ in scaled}
    assert not any(k.endswith(f"-{keep}") for k in keys)
    assert any(k.endswith(f"-{idle}") for k in keys)
    assert client.get(f"{API}/functions/{keep}", headers=user).json()["active_replicas"] == 1
    assert client.get(f"{API}/functions/{idle}", headers=user).json()["active_replicas"] == 0


def test_transient_api_error_does_not_mark_deployment_missing(monkeypatch):
    """A throttled/failed Deployment lookup must not be cached as 'not deployed'."""
    from kubernetes.client.rest import ApiException
    svc = k8s_service
    monkeypatch.setattr(svc, "k8s_available", True)
    monkeypatch.setattr(svc, "_deployment_cache", {})
    class FakeApps:
        outcome = None
        def read_namespaced_deployment(self, name, namespace):
            raise FakeApps.outcome
    monkeypatch.setattr(svc, "apps_v1", FakeApps())
    # conftest stubs has_deployment on the instance for every test; call the real class method
    real = type(svc).has_deployment

    FakeApps.outcome = ApiException(status=503)
    assert real(svc, "r1") is True                    # unknown -> assume it exists, do not cache a negative
    assert "r1" not in svc._deployment_cache
    FakeApps.outcome = ApiException(status=404)
    assert real(svc, "r2") is False                   # a genuine 404 is cached as missing
    assert svc._deployment_cache["r2"][0] is False
    svc._deployment_cache["r3"] = (True, 0.0)         # expired positive entry
    FakeApps.outcome = TimeoutError()
    assert real(svc, "r3") is True                    # keeps the last known answer
