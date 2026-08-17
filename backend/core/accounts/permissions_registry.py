"""权限点常量清单。权限点随代码走，管理员只能分配、不能新造。"""

# 分组双语权限注册表。权限点随代码走，管理员只分配不新造。
PERMISSION_GROUPS: dict[str, dict] = {
    "page": {
        "label_zh": "页面访问",
        "label_en": "Page Access",
        "items": {
            "page:dashboard": {"zh": "查看仪表盘", "en": "View Dashboard"},
            "page:admin": {"zh": "查看权限管理", "en": "View Admin"},
            "page:credentials": {"zh": "密钥管理", "en": "Credentials"},
            "page:market": {"zh": "行情页面", "en": "Market Page"},
            "page:trading": {"zh": "交易页面", "en": "Trading Page"},
            "page:strategy": {"zh": "策略页面", "en": "Strategy Page"},
            "page:backtest": {"zh": "回测页面", "en": "Backtest Page"},
        },
    },
    "credentials": {
        "label_zh": "密钥管理",
        "label_en": "Credentials",
        "items": {
            "credentials:view": {"zh": "查看", "en": "View Credentials"},
            "credentials:manage": {"zh": "管理", "en": "Manage Credentials"},
        },
    },
    "market": {
        "label_zh": "行情",
        "label_en": "Market",
        "items": {
            "market:view": {"zh": "查看行情", "en": "View Market Data"},
        },
    },
    "trading": {
        "label_zh": "交易",
        "label_en": "Trading",
        "items": {
            "trading:view": {"zh": "查看持仓/余额/订单", "en": "View Positions/Balance/Orders"},
            "trading:place_order": {"zh": "下单", "en": "Place Order"},
            "trading:cancel": {"zh": "撤单", "en": "Cancel Order"},
        },
    },
    "strategy": {
        "label_zh": "策略",
        "label_en": "Strategy",
        "items": {
            "strategy:view": {"zh": "查看策略/运行", "en": "View Strategies/Runs"},
            "strategy:create": {"zh": "创建策略", "en": "Create Strategy"},
            "strategy:update": {"zh": "更新策略", "en": "Update Strategy"},
            "strategy:delete": {"zh": "删除策略", "en": "Delete Strategy"},
            "strategy:run": {"zh": "启停策略运行", "en": "Start/Stop Strategy Run"},
        },
    },
    "backtest": {
        "label_zh": "回测",
        "label_en": "Backtest",
        "items": {
            "backtest:view": {"zh": "查看回测", "en": "View Backtests"},
            "backtest:create": {"zh": "创建回测", "en": "Create Backtest"},
        },
    },
}

# 扁平所有 code（供 services 交集、serializer 校验用），必须保持是所有权限码的 set
ALL_PERMISSION_CODES: set[str] = {
    code for g in PERMISSION_GROUPS.values() for code in g["items"]
}
