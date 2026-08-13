from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .services import get_effective_permissions_cached


class HasRequiredPermissions(BasePermission):
    """DRF permission class that validates required permissions from view.required_permissions.

    Supports:
    - view.required_permissions as list[str]: all permissions required for all methods
    - view.required_permissions as dict[method, list[str]]: per-method permission requirements
    """

    def has_permission(self, request, view) -> bool:
        required = getattr(view, "required_permissions", None)
        if not required:
            return True
        if getattr(request.user, "is_superuser", False):
            return True
        if isinstance(required, dict):
            required = required.get(request.method, ())
        if not required:
            return True
        effective = get_effective_permissions_cached(request)
        return all(p in effective for p in required)


def require_perm(request, code: str) -> None:
    """Dynamic permission check: raises DRF PermissionDenied (403) if user lacks the permission.

    Usage in views:
        def my_view(request):
            require_perm(request, "page:admin")
            # proceed with operation
    """
    if getattr(request.user, "is_superuser", False):
        return
    if code not in get_effective_permissions_cached(request):
        raise PermissionDenied(f"缺少权限: {code}")
