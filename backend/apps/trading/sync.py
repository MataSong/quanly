"""OKX 真实数据 upsert：把 REST/WS 拉到的余额/持仓/订单写入本地表并推前端。"""
import json
from decimal import Decimal

import redis
from django.conf import settings

from .models import Balance, Order, OrderState, Position, PosSide

D = Decimal


def _redis():
    return redis.from_url(settings.REDIS_URL)


def _publish(user_id, env, payload):
    try:
        _redis().publish(f"trade:{user_id}:{env}", json.dumps(payload))
    except Exception:
        pass


def upsert_balances(user, env, rows):
    """rows: 可迭代对象，元素含 ccy/total/available/frozen 属性。"""
    for r in rows:
        Balance.objects.update_or_create(
            user=user,
            env=env,
            ccy=r.ccy,
            defaults={
                "total": D(str(r.total)),
                "frozen": D(str(getattr(r, "frozen", 0) or 0)),
            },
        )
    _publish(user.id, env, {"type": "balance_update"})


def upsert_positions(user, env, rows):
    """rows: 元素含 symbol/side/qty/avg_price/upl/liq_price。qty=0 视为平仓。"""
    seen = set()
    for r in rows:
        pos_side = PosSide.LONG if str(r.side).lower() == "long" else PosSide.SHORT
        seen.add((r.symbol, pos_side))
        Position.objects.update_or_create(
            user=user,
            env=env,
            symbol=r.symbol,
            pos_side=pos_side,
            defaults={
                "qty": D(str(r.qty)),
                "avg_px": D(str(r.avg_price)),
                "liq_px": D(str(getattr(r, "liq_price", 0) or 0)),
            },
        )
    Position.objects.filter(user=user, env=env).exclude(
        symbol__in=[s for s, _ in seen]
    ).update(qty=D("0"))
    _publish(user.id, env, {"type": "position_update"})


def upsert_order(user, env, o):
    """o: 元素含 order_id/symbol/state/filled_sz/avg_px。"""
    state_map = {
        "live": OrderState.LIVE,
        "filled": OrderState.FILLED,
        "canceled": OrderState.CANCELED,
        "partially_filled": OrderState.LIVE,
    }
    Order.objects.filter(user=user, env=env, exchange_order_id=o.order_id).update(
        state=state_map.get(str(o.state).lower(), OrderState.LIVE),
        filled_sz=D(str(getattr(o, "filled_sz", 0) or 0)),
        avg_px=D(str(getattr(o, "avg_px", 0) or 0)),
    )
    _publish(user.id, env, {"type": "order_update"})


def full_sync(user, env, adapter):
    """进入页面/启动时的 REST 全量校正。"""
    upsert_balances(user, env, adapter.get_balances())
    upsert_positions(user, env, adapter.get_positions())
