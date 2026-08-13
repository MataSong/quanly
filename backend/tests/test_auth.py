import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_login_returns_tokens_and_permissions(api_client):
    User.objects.create_user("alice", password="pw123456")
    resp = api_client.post(
        "/api/auth/", {"username": "alice", "password": "pw123456"}, format="json"
    )
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert "permissions" in resp.data["user"]


@pytest.mark.django_db
def test_me_requires_auth(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
def test_login_invalid_credentials(api_client):
    User.objects.create_user("bob", password="correct")
    resp = api_client.post(
        "/api/auth/", {"username": "bob", "password": "wrong"}, format="json"
    )
    assert resp.status_code == 401
    assert resp.data["code"] == "auth_failed"


@pytest.mark.django_db
def test_login_inactive_account(api_client):
    User.objects.create_user("charlie", password="pw123456", is_active=False)
    resp = api_client.post(
        "/api/auth/", {"username": "charlie", "password": "pw123456"}, format="json"
    )
    assert resp.status_code == 403
    assert resp.data["code"] == "account_inactive"


@pytest.mark.django_db
def test_me_returns_user_fields(api_client):
    user = User.objects.create_user("diana", password="pw123456")
    # Login to get access token
    resp = api_client.post(
        "/api/auth/", {"username": "diana", "password": "pw123456"}, format="json"
    )
    assert resp.status_code == 200
    access = resp.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["username"] == "diana"
    assert "permissions" in me.data
    assert "auth_source" in me.data
    assert me.data["auth_source"] == "local"


@pytest.mark.django_db
def test_logout_blacklists_refresh(api_client):
    User.objects.create_user("eve", password="pw123456")
    resp = api_client.post(
        "/api/auth/", {"username": "eve", "password": "pw123456"}, format="json"
    )
    assert resp.status_code == 200
    refresh = resp.data["refresh"]
    logout_resp = api_client.post(
        "/api/auth/logout/", {"refresh": refresh}, format="json"
    )
    assert logout_resp.status_code == 204
    # Second logout with same token should still return 204 (graceful)
    logout_resp2 = api_client.post(
        "/api/auth/logout/", {"refresh": refresh}, format="json"
    )
    assert logout_resp2.status_code == 204


@pytest.mark.django_db
def test_login_user_data_structure(api_client):
    User.objects.create_user("frank", password="pw123456")
    resp = api_client.post(
        "/api/auth/", {"username": "frank", "password": "pw123456"}, format="json"
    )
    assert resp.status_code == 200
    user_data = resp.data["user"]
    assert "id" in user_data
    assert "username" in user_data
    assert "is_superuser" in user_data
    assert "permissions" in user_data
    assert "auth_source" in user_data
    assert isinstance(user_data["permissions"], list)
