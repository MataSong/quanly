"""资产聚合:把现货余额、合约持仓折算成统一净值视图。

净值折算用 Redis 缓存的真实 OKX 最新价;读不到价则该项折 0(不再有假数据兜底)。
"""
from decimal import Decimal

from apps.trading.models import Balance, Position, PosSide
from apps.trading.prices import get_last_price

D = Decimal


def _price(symbol: str) -> Decimal:
    p = get_last_price(symbol)
    return D(str(p)) if p is not None else D("0")


def summarize(user, env: str) -> dict:
    # 现货:各币种折 USDT
    spot_value = D("0")
    available_usdt = D("0")
    for bal in Balance.objects.filter(user=user, env=env):
        if bal.ccy == "USDT":
            val = bal.total
            available_usdt += (bal.total - bal.frozen)
        else:
            val = bal.total * _price(f"{bal.ccy}-USDT")
        spot_value += val

    # 合约:保证金 + 未实现盈亏
    swap_margin = D("0")
    upl = D("0")
    positions_dist = []
    for pos in Position.objects.filter(user=user, env=env, qty__gt=0):
        px = _price(pos.symbol)
        if pos.pos_side == PosSide.LONG:
            p_upl = (px - pos.avg_px) * pos.qty
        else:
            p_upl = (pos.avg_px - px) * pos.qty
        notional = px * pos.qty
        swap_margin += pos.margin
        upl += p_upl
        positions_dist.append(
            {
                "symbol": pos.symbol,
                "pos_side": pos.pos_side,
                "notional": float(notional),
                "upl": float(p_upl),
            }
        )

    swap_value = swap_margin + upl
    frozen = swap_margin

    total_equity = spot_value + swap_value

    return {
        "env": env,
        "total_equity": float(total_equity),
        "available": float(available_usdt),
        "frozen": float(frozen),
        "upl": float(upl),
        "spot_value": float(spot_value),
        "swap_value": float(swap_value),
        "positions_dist": positions_dist,
    }
