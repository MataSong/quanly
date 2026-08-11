# collector 默认订阅的主流交易对与默认周期；/market/symbols 优先返回 OKX 全量
# instruments，仅在拉取失败时回落到此列表作为兜底。
SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
DEFAULT_BAR = "1m"
