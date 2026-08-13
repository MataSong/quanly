import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.accounts.drf import HasRequiredPermissions
from . import okx_client

logger = logging.getLogger("quanly.market")


class _MarketViewMixin:
    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["market:view"]


@api_view(["GET"])
@permission_classes([IsAuthenticated, HasRequiredPermissions])
def candles_view(request: Request) -> Response:
    """GET /api/market/candles?symbol=BTC-USDT&bar=1m&limit=100

    Returns historical K-line data for chart initialisation.
    Requires permission: market:view
    """
    # Manual permission check (function-based views don't run class-based required_permissions)
    from core.accounts.services import get_effective_permissions_cached
    if not request.user.is_superuser:
        effective = get_effective_permissions_cached(request)
        if "market:view" not in effective:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("缺少权限: market:view")

    symbol = request.query_params.get("symbol", "BTC-USDT")
    bar = request.query_params.get("bar", "1m")
    try:
        limit = int(request.query_params.get("limit", "100"))
        limit = max(1, min(limit, 300))
    except (ValueError, TypeError):
        limit = 100

    try:
        data = okx_client.get_candles(symbol=symbol, bar=bar, limit=limit)
    except Exception as exc:
        logger.error("OKX candles error symbol=%s bar=%s: %s", symbol, bar, exc)
        return Response({"detail": str(exc)}, status=502)

    return Response({"symbol": symbol, "bar": bar, "data": data})


@api_view(["GET"])
@permission_classes([IsAuthenticated, HasRequiredPermissions])
def symbols_view(request: Request) -> Response:
    """GET /api/market/symbols

    Returns list of live SPOT instruments.
    Requires permission: market:view
    """
    from core.accounts.services import get_effective_permissions_cached
    if not request.user.is_superuser:
        effective = get_effective_permissions_cached(request)
        if "market:view" not in effective:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("缺少权限: market:view")

    try:
        data = okx_client.get_spot_symbols()
    except Exception as exc:
        logger.error("OKX symbols error: %s", exc)
        return Response({"detail": str(exc)}, status=502)

    return Response({"data": data})
