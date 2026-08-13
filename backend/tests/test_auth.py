import pytest
from django.contrib.auth.models import User

from core.accounts.services import get_effective_permissions


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
def test_blacklisted_refresh_cannot_refresh(api_client):
    """logout 后被拉黑的 refresh token 不能再换取新 access token(验证真失效,而非仅不崩)。"""
    User.objects.create_user("frank", password="pw123456")
    resp = api_client.post(
        "/api/auth/", {"username": "frank", "password": "pw123456"}, format="json"
    )
    refresh = resp.data["refresh"]
    # 拉黑前:refresh 能换 access
    ok = api_client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert ok.status_code == 200
    # 登出拉黑该 refresh
    assert api_client.post(
        "/api/auth/logout/", {"refresh": refresh}, format="json"
    ).status_code == 204
    # 拉黑后:同一 refresh 不能再换 access(rotate 后原 token 已黑名单)
    denied = api_client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    assert denied.status_code == 401



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


# === 注册 API 测试(批次 A) ===

REGISTER_URL = "/api/auth/register/"
# 满足强度规则的密码:大写+小写+数字 = 3类,长度>=8
STRONG_PASS = "Abcdef1!"


@pytest.mark.django_db
def test_register_success_returns_tokens_and_user(api_client):
    """成功注册:返回 201,含 access/refresh/user,user.permissions 含 page:dashboard。"""
    resp = api_client.post(
        REGISTER_URL,
        {"username": "newuser", "password": STRONG_PASS},
        format="json",
    )
    assert resp.status_code == 201
    assert "access" in resp.data
    assert "refresh" in resp.data
    user_data = resp.data["user"]
    assert user_data["username"] == "newuser"
    assert user_data["is_superuser"] is False
    assert "page:dashboard" in user_data["permissions"]
    assert user_data["auth_source"] == "local"


@pytest.mark.django_db
def test_register_duplicate_username_returns_400(api_client):
    """重复用户名注册返回 400,code=user_exists。"""
    User.objects.create_user("taken", password="pw123456")
    resp = api_client.post(
        REGISTER_URL,
        {"username": "taken", "password": STRONG_PASS},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["code"] == "user_exists"


@pytest.mark.django_db
def test_register_weak_password_returns_400(api_client):
    """弱密码(如 'abc')注册返回 400,code=weak_password。"""
    resp = api_client.post(
        REGISTER_URL,
        {"username": "weakuser", "password": "abc"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["code"] == "weak_password"


@pytest.mark.django_db
def test_register_missing_username_returns_400(api_client):
    """缺少 username 返回 400,code=bad_request。"""
    resp = api_client.post(
        REGISTER_URL,
        {"password": STRONG_PASS},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["code"] == "bad_request"


@pytest.mark.django_db
def test_register_user_gets_dashboard_permission(api_client):
    """注册后新用户 get_effective_permissions 能解析出 page:dashboard。"""
    resp = api_client.post(
        REGISTER_URL,
        {"username": "dashuser", "password": STRONG_PASS},
        format="json",
    )
    assert resp.status_code == 201
    user = User.objects.get(username="dashuser")
    perms = get_effective_permissions(user)
    assert "page:dashboard" in perms


@pytest.mark.django_db
def test_register_with_email(api_client):
    """注册时可选传入 email,注册成功。"""
    resp = api_client.post(
        REGISTER_URL,
        {"username": "emailuser", "password": STRONG_PASS, "email": "e@example.com"},
        format="json",
    )
    assert resp.status_code == 201
    user = User.objects.get(username="emailuser")
    assert user.email == "e@example.com"


@pytest.mark.django_db
def test_register_idempotent_user_role_creation(api_client):
    """连续注册两个不同用户,user 角色只存在一份。"""
    api_client.post(
        REGISTER_URL,
        {"username": "user_a", "password": STRONG_PASS},
        format="json",
    )
    api_client.post(
        REGISTER_URL,
        {"username": "user_b", "password": STRONG_PASS},
        format="json",
    )
    from core.accounts.models import Role
    assert Role.objects.filter(name="user").count() == 1
