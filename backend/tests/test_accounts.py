import pytest
from django.contrib.auth.models import User
from core.accounts.models import Role, UserRole, UserPermissionOverride
from core.accounts.services import get_effective_permissions
from core.accounts.permissions_registry import ALL_PERMISSION_CODES

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
