import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert data["status"] == "online"

def test_user_registration_and_login():
    username = "testuser_auth"
    email = "testuser_auth@faas.com"
    password = "SecurePassword123"

    # 1. Register
    reg_response = client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert reg_response.status_code in [201, 400]

    # 2. Login
    login_response = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password
    })
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data

    # 3. Get /me
    token = token_data["access_token"]
    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["username"] == username
