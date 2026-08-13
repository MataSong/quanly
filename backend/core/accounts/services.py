from .permissions_registry import ALL_PERMISSION_CODES


def get_effective_permissions(user) -> set[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSION_CODES)
    perms: set[str] = set()
    for ur in user.userrole_set.select_related("role").all():
        perms |= set(ur.role.permissions or [])
    for ov in user.userpermissionoverride_set.all():
        if ov.effect == "grant":
            perms.add(ov.permission)
        elif ov.effect == "deny":
            perms.discard(ov.permission)
    return perms & set(ALL_PERMISSION_CODES)


def get_effective_permissions_cached(request) -> set[str]:
    if not hasattr(request, "_perm_cache"):
        request._perm_cache = get_effective_permissions(request.user)
    return request._perm_cache
