import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from core.accounts.models import Role, UserRole, UserPermissionOverride
from core.accounts.services import get_effective_permissions
from core.accounts.permissions_registry import ALL_PERMISSION_CODES
from core.accounts.drf import HasRequiredPermissions, require_perm

@pytest.mark.django_db
def test_superuser_gets_all_permissions():
    u = User.objects.create_superuser("root", "r@x.com", "pw")
    assert get_effective_permissions(u) == ALL_PERMISSION_CODES

@pytest.mark.django_db
def test_role_union_then_override():
    u = User.objects.create_user("alice", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard"])
    UserRole.objects.create(user=u, role=role)
    UserPermissionOverride.objects.create(user=u, permission="page:admin", effect="grant")
    perms = get_effective_permissions(u)
    assert "page:dashboard" in perms
    assert "page:admin" in perms

@pytest.mark.django_db
def test_deny_override_removes_role_permission():
    u = User.objects.create_user("bob", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard", "page:admin"])
    UserRole.objects.create(user=u, role=role)
    UserPermissionOverride.objects.create(user=u, permission="page:admin", effect="deny")
    perms = get_effective_permissions(u)
    assert "page:dashboard" in perms
    assert "page:admin" not in perms

@pytest.mark.django_db
def test_invalid_permission_code_filtered_out():
    u = User.objects.create_user("carol", password="pw")
    role = Role.objects.create(name="x", permissions=["page:dashboard", "bogus:perm"])
    UserRole.objects.create(user=u, role=role)
    assert "bogus:perm" not in get_effective_permissions(u)

@pytest.mark.django_db
def test_grant_override_cannot_introduce_invalid_code():
    # 回归保护:grant 一个不在 ALL_PERMISSION_CODES 里的权限码,
    # 必须被最终的交集过滤掉(否则任何人都能通过 override 越权)。
    u = User.objects.create_user("dave", password="pw")
    UserPermissionOverride.objects.create(user=u, permission="bogus:grant", effect="grant")
    assert "bogus:grant" not in get_effective_permissions(u)


# === DRF Permission Tests (Task 3) ===

class _SimpleView(APIView):
    """Test view with required_permissions as list."""
    permission_classes = [HasRequiredPermissions]
    required_permissions = ["page:admin"]

    def get(self, request):
        return Response({"ok": True})


class _MethodSpecificView(APIView):
    """Test view with required_permissions as dict."""
    permission_classes = [HasRequiredPermissions]
    required_permissions = {
        "GET": ["page:dashboard"],
        "POST": ["page:admin"],
    }

    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        return Response({"ok": True})


class _NoPermView(APIView):
    """Test view with no required_permissions."""
    permission_classes = [HasRequiredPermissions]

    def get(self, request):
        return Response({"ok": True})


@pytest.mark.django_db
def test_has_required_permissions_denied_without_perm():
    """User without required permission should be denied."""
    u = User.objects.create_user("noperm", password="pw")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _SimpleView()
    permission = HasRequiredPermissions()
    assert permission.has_permission(request, view) is False


@pytest.mark.django_db
def test_has_required_permissions_granted_with_perm():
    """User with required permission should be granted."""
    u = User.objects.create_user("withperm", password="pw")
    role = Role.objects.create(name="admin", permissions=["page:admin"])
    UserRole.objects.create(user=u, role=role)
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _SimpleView()
    permission = HasRequiredPermissions()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_has_required_permissions_superuser_always_granted():
    """Superuser should always be granted."""
    u = User.objects.create_superuser("root", "r@x.com", "pw")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _SimpleView()
    permission = HasRequiredPermissions()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_has_required_permissions_no_required_always_granted():
    """View with no required_permissions should always grant access."""
    u = User.objects.create_user("anyone", password="pw")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _NoPermView()
    permission = HasRequiredPermissions()
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_has_required_permissions_dict_method_specific_get():
    """Dict-based required_permissions should check per method (GET)."""
    u = User.objects.create_user("user", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard"])
    UserRole.objects.create(user=u, role=role)
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _MethodSpecificView()
    permission = HasRequiredPermissions()
    # GET requires page:dashboard, user has it
    assert permission.has_permission(request, view) is True


@pytest.mark.django_db
def test_has_required_permissions_dict_method_specific_post_denied():
    """Dict-based required_permissions should check per method (POST denied)."""
    u = User.objects.create_user("user", password="pw")
    role = Role.objects.create(name="viewer", permissions=["page:dashboard"])
    UserRole.objects.create(user=u, role=role)
    factory = APIRequestFactory()
    request = factory.post("/")
    request.user = u
    view = _MethodSpecificView()
    permission = HasRequiredPermissions()
    # POST requires page:admin, user doesn't have it
    assert permission.has_permission(request, view) is False


@pytest.mark.django_db
def test_has_required_permissions_dict_method_not_in_keys_allowed():
    """Dict 模式下,请求方法不在 keys 里时(如 PUT)走空元组回退 -> 放通。
    这是刻意的宽松回退:未声明的方法视为无权限要求。"""
    u = User.objects.create_user("nokeyuser", password="pw")
    factory = APIRequestFactory()
    request = factory.put("/")
    request.user = u
    view = _MethodSpecificView()  # 只声明了 GET/POST,没有 PUT
    permission = HasRequiredPermissions()
    assert permission.has_permission(request, view) is True



@pytest.mark.django_db
def test_require_perm_granted():
    """require_perm should not raise when user has permission."""
    u = User.objects.create_user("user", password="pw")
    role = Role.objects.create(name="admin", permissions=["page:admin"])
    UserRole.objects.create(user=u, role=role)
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    # Should not raise
    require_perm(request, "page:admin")


@pytest.mark.django_db
def test_require_perm_denied():
    """require_perm should raise PermissionDenied when user lacks permission."""
    u = User.objects.create_user("user", password="pw")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    with pytest.raises(PermissionDenied):
        require_perm(request, "page:admin")


@pytest.mark.django_db
def test_require_perm_superuser_always_granted():
    """require_perm should not raise for superuser."""
    u = User.objects.create_superuser("root", "r@x.com", "pw")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    # Should not raise even with nonexistent permission
    require_perm(request, "page:admin")


@pytest.mark.django_db
def test_has_required_permissions_caching():
    """Permissions should be cached on request object."""
    u = User.objects.create_user("user", password="pw")
    role = Role.objects.create(name="admin", permissions=["page:admin"])
    UserRole.objects.create(user=u, role=role)
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = u
    view = _SimpleView()
    permission = HasRequiredPermissions()
    # First call
    result1 = permission.has_permission(request, view)
    # Verify cache is set
    assert hasattr(request, "_perm_cache")
    cache_before = request._perm_cache
    # Second call should use cached value
    result2 = permission.has_permission(request, view)
    assert result1 == result2
    assert request._perm_cache is cache_before


# === Task 5: 用户/角色管理 API 测试 ===

@pytest.mark.django_db
def test_non_superuser_cannot_list_users(api_client):
    u = User.objects.create_user("plain", password="pw123456")
    api_client.force_authenticate(u)
    assert api_client.get("/api/accounts/users/").status_code == 403


@pytest.mark.django_db
def test_superuser_can_list_users(api_client):
    su = User.objects.create_superuser("root", "r@x.com", "pw123456")
    api_client.force_authenticate(su)
    assert api_client.get("/api/accounts/users/").status_code == 200


@pytest.mark.django_db
def test_permissions_list_endpoint(api_client):
    su = User.objects.create_superuser("root2", "r@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.get("/api/accounts/permissions/")
    assert resp.status_code == 200
    assert "page:dashboard" in str(resp.data)


@pytest.mark.django_db
def test_superuser_can_create_role(api_client):
    su = User.objects.create_superuser("su_role", "s@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.post("/api/accounts/roles/", {
        "name": "trader",
        "permissions": ["page:dashboard"],
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["name"] == "trader"


@pytest.mark.django_db
def test_cannot_delete_superuser(api_client):
    su = User.objects.create_superuser("su_del", "s@x.com", "pw123456")
    target = User.objects.create_superuser("su_target", "t@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.delete(f"/api/accounts/users/{target.id}/")
    assert resp.status_code == 400
    assert resp.data["code"] == "cannot_delete_superuser"


@pytest.mark.django_db
def test_cannot_delete_self(api_client):
    # C1 修复后:destroy 先查"删自己"再查"删超管",两条保护相互独立。
    # 超管删自己 -> 精确命中 cannot_delete_self。
    su = User.objects.create_superuser("su_self", "s@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.delete(f"/api/accounts/users/{su.id}/")
    assert resp.status_code == 400
    assert resp.data["code"] == "cannot_delete_self"


@pytest.mark.django_db
def test_cannot_delete_other_superuser(api_client):
    # 删"另一个"超管(非自己) -> 命中 cannot_delete_superuser。
    su = User.objects.create_superuser("su_actor", "a@x.com", "pw123456")
    other = User.objects.create_superuser("su_other", "o@x.com", "pw123456")
    api_client.force_authenticate(su)
    resp = api_client.delete(f"/api/accounts/users/{other.id}/")
    assert resp.status_code == 400
    assert resp.data["code"] == "cannot_delete_superuser"



@pytest.mark.django_db
def test_set_active(api_client):
    su = User.objects.create_superuser("su_active", "s@x.com", "pw123456")
    u = User.objects.create_user("target_active", password="pw123456")
    api_client.force_authenticate(su)
    resp = api_client.post(f"/api/accounts/users/{u.id}/set_active/",
                           {"is_active": False}, format="json")
    assert resp.status_code == 200
    assert resp.data["data"]["is_active"] is False


@pytest.mark.django_db
def test_reset_password_too_short(api_client):
    su = User.objects.create_superuser("su_pw", "s@x.com", "pw123456")
    u = User.objects.create_user("target_pw", password="pw123456")
    api_client.force_authenticate(su)
    resp = api_client.post(f"/api/accounts/users/{u.id}/reset_password/",
                           {"password": "short"}, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "weak_password"


@pytest.mark.django_db
def test_reset_password_ok(api_client):
    su = User.objects.create_superuser("su_pw2", "s@x.com", "pw123456")
    u = User.objects.create_user("target_pw2", password="pw123456")
    api_client.force_authenticate(su)
    resp = api_client.post(f"/api/accounts/users/{u.id}/reset_password/",
                           {"password": "NewPassword1"}, format="json")
    assert resp.status_code == 200
    assert resp.data["data"]["ok"] is True


@pytest.mark.django_db
def test_set_user_roles(api_client):
    su = User.objects.create_superuser("su_roles", "s@x.com", "pw123456")
    u = User.objects.create_user("target_roles", password="pw123456")
    role = Role.objects.create(name="analyst", permissions=["page:dashboard"])
    api_client.force_authenticate(su)
    resp = api_client.put(f"/api/accounts/users/{u.id}/roles/",
                          {"role_ids": [role.id]}, format="json")
    assert resp.status_code == 200
    assert role.id in resp.data["data"]["roles"]


@pytest.mark.django_db
def test_overrides_add_and_list(api_client):
    su = User.objects.create_superuser("su_ovr", "s@x.com", "pw123456")
    u = User.objects.create_user("target_ovr", password="pw123456")
    api_client.force_authenticate(su)
    # Add override
    resp = api_client.post(f"/api/accounts/users/{u.id}/overrides/",
                           {"permission": "page:dashboard", "effect": "deny"},
                           format="json")
    assert resp.status_code == 201
    # List overrides
    resp2 = api_client.get(f"/api/accounts/users/{u.id}/overrides/")
    assert resp2.status_code == 200
    assert len(resp2.data["data"]) == 1
    assert resp2.data["data"][0]["effect"] == "deny"


@pytest.mark.django_db
def test_delete_override(api_client):
    su = User.objects.create_superuser("su_del_ovr", "s@x.com", "pw123456")
    u = User.objects.create_user("target_del_ovr", password="pw123456")
    override = UserPermissionOverride.objects.create(
        user=u, permission="page:dashboard", effect="grant")
    api_client.force_authenticate(su)
    resp = api_client.delete(f"/api/accounts/users/{u.id}/overrides/{override.id}/")
    assert resp.status_code == 204


@pytest.mark.django_db
def test_delete_override_not_found(api_client):
    # I4 修复:删不存在的 override 应返回 404,而非静默 204。
    su = User.objects.create_superuser("su_del_ovr_404", "s@x.com", "pw123456")
    u = User.objects.create_user("target_del_ovr_404", password="pw123456")
    api_client.force_authenticate(su)
    resp = api_client.delete(f"/api/accounts/users/{u.id}/overrides/999999/")
    assert resp.status_code == 404
    assert resp.data["code"] == "override_not_found"


@pytest.mark.django_db
def test_audit_log_written_on_role_create(api_client):
    from core.audit.models import AuditLog
    su = User.objects.create_superuser("su_audit", "s@x.com", "pw123456")
    api_client.force_authenticate(su)
    api_client.post("/api/accounts/roles/", {
        "name": "audit_role",
        "permissions": [],
    }, format="json")
    assert AuditLog.objects.filter(action="accounts.role.create").exists()

