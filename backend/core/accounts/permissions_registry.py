"""权限点常量清单。权限点随代码走，管理员只能分配、不能新造。"""

# 分组双语权限注册表。权限点随代码走，管理员只分配不新造。
PERMISSION_GROUPS: dict[str, dict] = {
    "page": {
        "label_zh": "页面访问",
        "label_en": "Page Access",
        "items": {
            "page:dashboard": {"zh": "查看仪表盘", "en": "View Dashboard"},
            "page:admin": {"zh": "查看权限管理", "en": "View Admin"},
        },
    },
}

# 扁平所有 code（供 services 交集、serializer 校验用），必须保持是所有权限码的 set
ALL_PERMISSION_CODES: set[str] = {
    code for g in PERMISSION_GROUPS.values() for code in g["items"]
}
