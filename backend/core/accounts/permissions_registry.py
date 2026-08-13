"""权限点常量清单。权限点随代码走，管理员只能分配、不能新造。"""

PERMISSIONS: dict[str, str] = {
    "page:dashboard": "查看仪表盘",
    "page:admin": "查看权限管理",
}

ALL_PERMISSION_CODES: set[str] = set(PERMISSIONS.keys())
