"""Backtest views: create/list/detail endpoints."""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.accounts.drf import HasRequiredPermissions, require_perm
from core.backtest.models import Backtest, BacktestTrade
from core.strategy.models import Strategy

logger = logging.getLogger("quanly.backtest")


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class BacktestTradeSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = BacktestTrade
        fields = ["id", "side", "ts", "price", "sz", "fee", "pnl"]


class BacktestSerializer(drf_serializers.ModelSerializer):
    strategy_name = drf_serializers.CharField(source="strategy.name", read_only=True)
    trades = BacktestTradeSerializer(many=True, read_only=True)

    class Meta:
        model = Backtest
        fields = [
            "id", "strategy", "strategy_name", "symbol", "bar",
            "start_ts", "end_ts", "params", "init_cash", "fee_rate",
            "status", "metrics", "equity_curve", "error_msg",
            "trades", "created_at",
        ]


class BacktestListSerializer(drf_serializers.ModelSerializer):
    """Lightweight serializer for list endpoint — omits equity_curve and trades."""
    strategy_name = drf_serializers.CharField(source="strategy.name", read_only=True)

    class Meta:
        model = Backtest
        fields = [
            "id", "strategy", "strategy_name", "symbol", "bar",
            "start_ts", "end_ts", "params", "init_cash", "fee_rate",
            "status", "metrics", "error_msg", "created_at",
        ]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class BacktestListCreateView(APIView):
    """
    GET  /api/backtest/backtests  — list current user's backtests.
    POST /api/backtest/backtests  — create and enqueue a new backtest.
    """

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = {
        "GET": ["backtest:view"],
        "POST": ["backtest:create"],
    }

    def get(self, request):
        require_perm(request, "backtest:view")
        backtests = Backtest.objects.filter(user=request.user).select_related("strategy")
        return Response(BacktestListSerializer(backtests, many=True).data)

    def post(self, request):
        require_perm(request, "backtest:create")

        strategy_id = request.data.get("strategy_id")
        symbol = (request.data.get("symbol") or "").strip()
        bar = (request.data.get("bar") or "1m").strip()
        start_ts = request.data.get("start_ts")
        end_ts = request.data.get("end_ts")
        params = request.data.get("params") or {}
        init_cash = request.data.get("init_cash", 10_000.0)
        fee_rate = request.data.get("fee_rate", 0.001)

        # Validate required fields.
        errors = {}
        if not strategy_id:
            errors["strategy_id"] = "Required."
        if not symbol:
            errors["symbol"] = "Required."
        if start_ts is None:
            errors["start_ts"] = "Required (millisecond epoch)."
        if end_ts is None:
            errors["end_ts"] = "Required (millisecond epoch)."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_ts = int(start_ts)
            end_ts = int(end_ts)
        except (TypeError, ValueError):
            return Response(
                {"detail": "start_ts and end_ts must be integer millisecond timestamps."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if end_ts <= start_ts:
            return Response(
                {"detail": "end_ts must be greater than start_ts."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        strategy = get_object_or_404(Strategy, pk=strategy_id)

        try:
            init_cash = float(init_cash)
            fee_rate = float(fee_rate)
        except (TypeError, ValueError):
            return Response(
                {"detail": "init_cash and fee_rate must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bt = Backtest.objects.create(
            user=request.user,
            strategy=strategy,
            symbol=symbol,
            bar=bar,
            start_ts=start_ts,
            end_ts=end_ts,
            params=params,
            init_cash=init_cash,
            fee_rate=fee_rate,
            status=Backtest.STATUS_PENDING,
        )

        from core.backtest.tasks import run_backtest

        run_backtest.apply_async(args=[bt.pk], queue="backtest")
        logger.info(
            "backtest.create: enqueued run_backtest backtest=%s user=%s", bt.pk, request.user.id
        )

        return Response({"id": bt.pk, "status": bt.status}, status=status.HTTP_201_CREATED)


class BacktestDetailView(APIView):
    """GET /api/backtest/backtests/<id> — full detail including trades and equity curve."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["backtest:view"]

    def get(self, request, pk):
        require_perm(request, "backtest:view")
        bt = get_object_or_404(Backtest, pk=pk, user=request.user)
        return Response(BacktestSerializer(bt).data)
