import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    username = "test_func_user"
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
    return {"Authorization": f"Bearer {token}"}

def test_create_and_list_functions(auth_headers):
    # 1. Create function
    create_resp = client.post("/api/v1/functions/", headers=auth_headers, json={
        "name": "calc-double",
        "runtime": "python311",
        "code": "def handler(event):\n    return {'result': event.get('x', 0) * 2}",
        "description": "Double input x"
    })
    assert create_resp.status_code in [201, 400]

    # 2. List functions
    list_resp = client.get("/api/v1/functions/", headers=auth_headers)
    assert list_resp.status_code == 200
    functions = list_resp.json()
    assert any(fn["name"] == "calc-double" for fn in functions)

    # 3. Get single function
    get_resp = client.get("/api/v1/functions/calc-double", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "calc-double"
