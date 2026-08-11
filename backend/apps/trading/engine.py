"""OKX 真实交易引擎：下单/撤单/平仓直调 OKXAdapter。

不再本地撮合/结算：成交、持仓、余额变化由 OKX 私有 WS（run_private_ws）
与 REST 同步（sync.py）回填。本模块只负责把用户动作转发给交易所并回填订单号。
"""
from decimal import Decimal

from .models import OrderState

D = Decimal


def _get_balance(user, env, ccy):
    """获取余额行，不存在则建零余额（不再注资 mock 初始资金）。"""
    from .models import Balance

    bal, _ = Balance.objects.get_or_create(
        user=user, env=env, ccy=ccy, defaults={"total": D("0")}
    )
    return bal


class OKXEngine:
    """真实 OKX 交易引擎。下单/撤单/平仓走 OKXAdapter，状态回填由 WS/REST 同步负责。"""

    def _adapter(self, order):
        from apps.credentials.models import Env
        from apps.exchanges.factory import AdapterFactory

        env = Env.SIM if order.env == "sim" else Env.LIVE
        return AdapterFactory.create("okx", env, order.credential)

    def place(self, order):
        from apps.exchanges.types import InstType as XInstType
        from apps.exchanges.types import OrderRequest

        adapter = self._adapter(order)
        req = OrderRequest(
            symbol=order.symbol,
            inst_type=XInstType(order.inst_type),
            side=order.side,
            ord_type=order.ord_type,
            sz=float(order.sz),
            px=float(order.px) if order.px else None,
            td_mode=order.td_mode,
            lever=int(order.lever) if order.lever else None,
            pos_side=order.pos_side if order.pos_side and order.pos_side != "net" else None,
        )
        result = adapter.place_order(req)
        order.exchange_order_id = result.order_id
        order.state = OrderState.LIVE if result.state == "live" else order.state
        order.save()
        return order

    def cancel(self, order):
        adapter = self._adapter(order)
        adapter.cancel_order(order.exchange_order_id, symbol=order.symbol)
        order.state = OrderState.CANCELED
        order.save()
        return order

    def close_position(self, position):
        from apps.credentials.models import Env
        from apps.exchanges.factory import AdapterFactory

        env = Env.SIM if position.env == "sim" else Env.LIVE
        cred = (
            position.user.exchangecredential_set.filter(
                env=position.env, exchange="okx"
            ).first()
            if hasattr(position.user, "exchangecredential_set")
            else None
        )
        adapter = AdapterFactory.create("okx", env, cred)
        adapter.close_position(position.symbol, position.pos_side, "cross")
        return position


def get_engine():
    return OKXEngine()
