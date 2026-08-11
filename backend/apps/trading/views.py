from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.credentials.models import ExchangeCredential


class TradeRateThrottle(UserRateThrottle):
    """交易下单专用限流(rate 取 settings 的 'trade' scope,120/min)。"""

    scope = "trade"

from .engine import get_engine
from .models import Balance, Order, Position, Trade
from .notify import notify_trade
from .serializers import (
    BalanceSerializer,
    OrderSerializer,
    PlaceOrderSerializer,
    PositionSerializer,
    TradeSerializer,
)


@api_view(["GET"])
def list_credentials(request):
    """当前用户某环境的密钥列表(供交易页选择用哪套 key)。secret 不返回。"""
    env = request.query_params.get("env")
    qs = ExchangeCredential.objects.filter(user=request.user)
    if env:
        qs = qs.filter(env=env)
    data = [
        {
            "id": c.id,
            "label": c.label,
            "exchange": c.exchange,
            "env": c.env,
            "api_key_masked": "****" + c.api_key[-4:],
        }
        for c in qs
    ]
    return Response(data)


@api_view(["POST"])
@throttle_classes([TradeRateThrottle])
def place_order(request):
    ser = PlaceOrderSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    # 幂等:同一 client_order_id 已存在则返回原订单,防并发/重复下单
    coid = request.data.get("client_order_id")
    if coid:
        existing = Order.objects.filter(user=request.user, client_order_id=coid).first()
        if existing:
            return Response(OrderSerializer(existing).data, status=200)
    credential = None
    cred_id = request.data.get("credential_id")
    if cred_id:
        credential = get_object_or_404(
            ExchangeCredential, pk=cred_id, user=request.user
        )
    order = Order.objects.create(
        user=request.user,
        env=d["env"],
        inst_type=d["inst_type"],
        symbol=d["symbol"],
        side=d["side"],
        pos_side=d.get("pos_side", "net"),
        ord_type=d["ord_type"],
        px=d.get("px"),
        sz=d["sz"],
        td_mode=d.get("td_mode", "cash"),
        lever=d.get("lever", 1),
        strike=d.get("strike"),
        expiry=d.get("expiry", ""),
        opt_type=d.get("opt_type", ""),
        tp_px=d.get("tp_px"),
        sl_px=d.get("sl_px"),
        credential=credential,
        client_order_id=coid or "",
    )
    get_engine().place(order)
    order.refresh_from_db()
    notify_trade(request.user.id, d["env"])
    return Response(OrderSerializer(order).data, status=201)


@api_view(["GET"])
def list_orders(request):
    qs = Order.objects.filter(user=request.user)
    env = request.query_params.get("env")
    state = request.query_params.get("state")
    if env:
        qs = qs.filter(env=env)
    if state:
        qs = qs.filter(state=state)
    return Response(OrderSerializer(qs[:200], many=True).data)


@api_view(["POST"])
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    get_engine().cancel(order)
    order.refresh_from_db()
    notify_trade(request.user.id, order.env)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
def set_tpsl(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    order.tp_px = request.data.get("tp_px") or None
    order.sl_px = request.data.get("sl_px") or None
    order.save()
    return Response(OrderSerializer(order).data)


@api_view(["GET"])
def list_positions(request):
    qs = Position.objects.filter(user=request.user, qty__gt=0)
    env = request.query_params.get("env")
    if env:
        qs = qs.filter(env=env)
    return Response(PositionSerializer(qs, many=True).data)


@api_view(["POST"])
def close_position(request, pk):
    pos = get_object_or_404(Position, pk=pk, user=request.user)
    get_engine().close_position(pos)
    pos.refresh_from_db()
    notify_trade(request.user.id, pos.env)
    return Response(PositionSerializer(pos).data)


@api_view(["GET"])
def list_balances(request):
    qs = Balance.objects.filter(user=request.user)
    env = request.query_params.get("env")
    if env:
        qs = qs.filter(env=env)
    return Response(BalanceSerializer(qs, many=True).data)


@api_view(["GET"])
def list_trades(request):
    qs = Trade.objects.filter(order__user=request.user)
    env = request.query_params.get("env")
    if env:
        qs = qs.filter(order__env=env)
    return Response(TradeSerializer(qs[:100], many=True).data)


@api_view(["GET"])
def reconcile_view(request):
    from .reconcile import reconcile

    env = request.query_params.get("env", "sim")
    return Response(reconcile(request.user, env))
