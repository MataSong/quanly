"""风控:强平价、保证金率(OKX 逐仓 USDT 本位公式)。

MMR 档位当前用 OKX 文档默认值兜底(本机连不上 OKX)。
接通后换成 `GET /api/v5/public/position-tiers` 拉取的实时分档 MMR,公式不变。
"""
from decimal import Decimal

D = Decimal

# 维持保证金率默认档位(OKX 文档常见首档值);连不上 OKX 时用此兜底
MMR_DEFAULT = {"BTC": D("0.004"), "ETH": D("0.005"), "SOL": D("0.0075")}
MMR_FALLBACK = D("0.01")
FEE_RATE = D("0.0005")  # taker

# 实时档位缓存:{base_ccy: mmr};接通 OKX 后由 fetch_position_tiers 填充
_tier_cache: dict = {}


def _base_ccy(symbol: str) -> str:
    return symbol.split("-")[0].replace("3L", "").replace("3S", "")


def fetch_position_tiers(symbol: str):
    """尝试从 OKX 拉取该品种维持保证金率档位(首档),缓存;失败静默(用默认)。
    接通 OKX 后生效;本机连不上时抛异常被吞,_mmr 回落默认档位。
    """
    base = _base_ccy(symbol)
    if base in _tier_cache:
        return _tier_cache[base]
    try:
        from okx import PublicData

        api = PublicData.PublicAPI(flag="0")
        resp = api.get_position_tiers(instType="SWAP", tdMode="cross", uly=f"{base}-USDT")
        first = resp["data"][0]
        _tier_cache[base] = D(str(first["mmr"]))
        return _tier_cache[base]
    except Exception:
        return None


def _mmr(symbol: str) -> Decimal:
    live = fetch_position_tiers(symbol)
    if live is not None:
        return live
    base = _base_ccy(symbol)
    return MMR_DEFAULT.get(base, MMR_FALLBACK)


def liq_price(pos) -> Decimal:
    """OKX 逐仓强平价(USDT 本位)。
    多头 = 开仓价 × (1 - 1/lever + MMR + fee)
    空头 = 开仓价 × (1 + 1/lever - MMR - fee)
    """
    if pos.lever <= 0 or pos.avg_px <= 0:
        return D("0")
    mmr = _mmr(pos.symbol)
    inv_lev = D("1") / D(pos.lever)
    if pos.pos_side == "long":
        return pos.avg_px * (D("1") - inv_lev + mmr + FEE_RATE)
    return pos.avg_px * (D("1") + inv_lev - mmr - FEE_RATE)


def margin_ratio(pos, mark_price) -> Decimal:
    """保证金率 = (保证金 + 未实现盈亏) / 名义价值。越低越危险。"""
    mark = D(str(mark_price))
    notional = mark * pos.qty
    if notional <= 0:
        return D("1")
    if pos.pos_side == "long":
        upl = (mark - pos.avg_px) * pos.qty
    else:
        upl = (pos.avg_px - mark) * pos.qty
    return (pos.margin + upl) / notional


def near_liquidation(pos, mark_price, threshold=D("0.05")) -> bool:
    """现价距强平价 < threshold(默认 5%)视为逼近强平。"""
    lp = liq_price(pos)
    if lp <= 0:
        return False
    mark = D(str(mark_price))
    return abs(mark - lp) / mark < threshold
