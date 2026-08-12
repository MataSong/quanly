"""策略专用 API:供 strategy-runner 容器调用,用 RUN_TOKEN 鉴权(非 JWT)。

策略容器拿不到真实密钥;下单经此处用 run.credential + env 走撮合引擎。
"""
from decimal import Decimal

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.trading.engine import get_engine
from apps.trading.models import Balance, Order, Position
from apps.trading.prices import get_last_price

from .models import StrategyLog, StrategyRun


def _run_from_token(request):
    token = request.headers.get("X-Run-Token") or request.query_params.get("run_token")
    if not token:
        return None
    return StrategyRun.objects.filter(run_token=token, status=StrategyRun.Status.RUNNING).first()


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def market(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    symbol = request.query_params.get("symbol", run.symbol)
    return Response({"symbol": symbol, "price": get_last_price(symbol)})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def candles(request):
    """历史 K 线(供策略算指标),走真实 OKX 适配器。"""
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)

    symbol = request.query_params.get("symbol", run.symbol)
    bar = request.query_params.get("bar", "1m")
    limit = int(request.query_params.get("limit", 100))
    from dataclasses import asdict

    from apps.exchanges.factory import AdapterFactory
    from apps.exchanges.types import Env

    adapter = AdapterFactory.create("okx", Env.SIM, credential=None)
    data = [asdict(c) for c in adapter.get_candles(symbol, bar, limit)]
    return Response({"symbol": symbol, "bar": bar, "candles": data})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def positions(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    qs = Position.objects.filter(user=run.user, env=run.env, qty__gt=0)
    return Response(
        [
            {"symbol": p.symbol, "pos_side": p.pos_side, "qty": float(p.qty), "avg_px": float(p.avg_px)}
            for p in qs
        ]
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def balances(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    qs = Balance.objects.filter(user=run.user, env=run.env)
    return Response([{"ccy": b.ccy, "total": float(b.total), "available": float(b.available)} for b in qs])


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def order(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    d = request.data
    o = Order.objects.create(
        user=run.user,
        env=run.env,
        inst_type=d.get("inst_type", "SPOT"),
        symbol=d.get("symbol", run.symbol),
        side=d["side"],
        ord_type=d.get("ord_type", "market"),
        px=Decimal(str(d["px"])) if d.get("px") else None,
        sz=Decimal(str(d["sz"])),
        td_mode=d.get("td_mode", "cash"),
        lever=d.get("lever", 1),
        credential=run.credential,
    )
    get_engine().place(o)
    o.refresh_from_db()
    return Response({"id": o.id, "state": o.state, "avg_px": float(o.avg_px)}, status=201)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def log(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    msg = request.data.get("message", "")
    level = request.data.get("level") or _infer_level(msg)
    StrategyLog.objects.create(run=run, level=level, message=msg)
    # 转发到 redis 供 WS 推前端
    try:
        import json

        import redis
        from django.conf import settings

        r = redis.from_url(settings.REDIS_URL)
        r.publish(f"strategy:{run.id}", json.dumps({"level": level, "message": msg}))
    except Exception:
        pass
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def heartbeat(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    from django.utils import timezone

    run.last_heartbeat = timezone.now()
    run.save(update_fields=["last_heartbeat"])
    return Response({"ok": True})


def _infer_level(msg: str) -> str:
    """无显式 level 时按关键词推断,供前端着色。"""
    u = str(msg).upper()
    if any(k in u for k in ("开多", "开仓做多", "买入", "BUY ")):
        return "buy"
    if any(k in u for k in ("平仓", "卖出", "STOP", "止损", "止盈", "TAKE-PROFIT", "TRAILING", "SELL ")):
        return "sell"
    if any(k in u for k in ("WARN", "预警", "ERROR", "错误", "失败", "异常")):
        return "warn"
    return "info"
