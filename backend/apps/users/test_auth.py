import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_register_then_login():
    c = APIClient()
    r = c.post(
        "/api/auth/register",
        {"username": "u1", "email": "u1@x.com", "password": "pass12345"},
        format="json",
    )
    assert r.status_code == 201

    r = c.post(
        "/api/auth/login",
        {"username": "u1", "password": "pass12345"},
        format="json",
    )
    assert r.status_code == 200 and "access" in r.data

    token = r.data["access"]
    r = c.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 200 and r.data["username"] == "u1"


@pytest.mark.django_db
def test_me_requires_auth():
    c = APIClient()
    r = c.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.django_db
def test_register_rejects_weak_password():
    c = APIClient()
    # 纯数字,无字母 -> 拒绝
    r = c.post(
        "/api/auth/register",
        {"username": "u2", "email": "u2@x.com", "password": "123456789"},
        format="json",
    )
    assert r.status_code == 400
    # 太短 -> 拒绝
    r = c.post(
        "/api/auth/register",
        {"username": "u3", "email": "u3@x.com", "password": "ab12"},
        format="json",
    )
    assert r.status_code == 400
