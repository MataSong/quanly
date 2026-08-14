import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.accounts.drf import require_perm
from . import okx_client

logger = logging.getLogger("quanly.market")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candles_view(request: Request) -> Response:
    """GET /api/market/candles?symbol=BTC-USDT&bar=1m&limit=100[&after=<ms>]

    Returns historical K-line data for chart initialisation.
    When ``after`` is supplied, fetches data *before* that timestamp
    (pagination backward in time) via get_history_candles.
    Requires permission: market:view
    """
    # 函数视图不走类视图的 required_permissions,用命令式 require_perm 校验。
    require_perm(request, "market:view")

    symbol = request.query_params.get("symbol", "BTC-USDT")
    bar = request.query_params.get("bar", "1m")
    after = request.query_params.get("after")  # optional ms timestamp string
    try:
        limit = int(request.query_params.get("limit", "100"))
        limit = max(1, min(limit, 300))
    except (ValueError, TypeError):
        limit = 100

    try:
        if after is not None:
            data = okx_client.get_history_candles(
                symbol=symbol, bar=bar, after=after, limit=min(limit, 100)
            )
        else:
            data = okx_client.get_candles(symbol=symbol, bar=bar, limit=limit)
    except Exception as exc:
        logger.error("OKX candles error symbol=%s bar=%s after=%s: %s", symbol, bar, after, exc)
        return Response({"detail": str(exc)}, status=502)

    return Response({"symbol": symbol, "bar": bar, "data": data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def symbols_view(request: Request) -> Response:
    """GET /api/market/symbols

    Returns list of live SPOT instruments.
    Requires permission: market:view
    """
    require_perm(request, "market:view")

    try:
        data = okx_client.get_spot_symbols()
    except Exception as exc:
        logger.error("OKX symbols error: %s", exc)
        return Response({"detail": str(exc)}, status=502)

    return Response({"data": data})
