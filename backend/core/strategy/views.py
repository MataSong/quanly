"""Strategy app views.

Two families:
  1. Management API  — JWT + permission checks (strategy:* perms).
  2. Runner API      — RunTokenAuthentication only (no JWT, no page perm).
"""
import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.accounts.drf import HasRequiredPermissions, require_perm
from core.audit.decorators import audit
from core.strategy.auth import RunTokenAuthentication
from core.strategy.models import Strategy, StrategyLog, StrategyRun

logger = logging.getLogger("quanly.strategy")


# ---------------------------------------------------------------------------
# Serializers (inline — small app, no need for separate serializers.py)
# ---------------------------------------------------------------------------

class StrategySerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = ["id", "name", "source_type", "code_ref", "default_params", "is_builtin", "created_at"]


class StrategyRunReadSerializer(drf_serializers.ModelSerializer):
    strategy_name = drf_serializers.CharField(source="strategy.name", read_only=True)
    credential_label = drf_serializers.SerializerMethodField()
    credential_env = drf_serializers.SerializerMethodField()

    class Meta:
        model = StrategyRun
        fields = [
            "id", "name", "strategy", "strategy_name", "env", "symbol", "params",
            "status", "container_id", "created_at",
            "credential_label", "credential_env",
        ]

    def get_credential_label(self, obj) -> str:
        return obj.credential.label if obj.credential else ""

    def get_credential_env(self, obj) -> str:
        return obj.credential.env if obj.credential else ""


class StrategyLogSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = StrategyLog
        fields = ["id", "level", "message", "ts"]


# ---------------------------------------------------------------------------
# Management API — JWT authenticated
# ---------------------------------------------------------------------------

class StrategyListView(APIView):
    """GET /api/strategy/strategies — list available strategies."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request):
        strategies = Strategy.objects.all()
        return Response(StrategySerializer(strategies, many=True).data)


class StrategyRunListCreateView(APIView):
    """
    GET  /api/strategy/runs  — list current user's runs.
    POST /api/strategy/runs  — create a new run.
    """

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = {
        "GET": ["strategy:view"],
        "POST": ["strategy:run"],
    }

    def get(self, request):
        runs = StrategyRun.objects.filter(user=request.user).select_related("strategy")
        return Response(StrategyRunReadSerializer(runs, many=True).data)

    def post(self, request):
        require_perm(request, "strategy:run")

        strategy_id = request.data.get("strategy_id")
        credential_id = request.data.get("credential_id")
        symbol = request.data.get("symbol", "").strip()
        params = request.data.get("params", {})
        name = (request.data.get("name") or "").strip()

        if not strategy_id or not symbol:
            return Response(
                {"detail": "strategy_id and symbol are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        strategy = get_object_or_404(Strategy, pk=strategy_id)

        # Multi-tenant: credential must belong to request.user
        from core.credentials.models import Credential

        credential = None
        if credential_id:
            credential = get_object_or_404(
                Credential, pk=credential_id, user=request.user
            )

        env = credential.env if credential else StrategyRun.ENV_SIM

        # Auto-generate name if not provided
        if not name:
            name = f"{strategy.name}-{symbol}-{timezone.now().strftime('%m%d-%H%M')}"

        # 创建时不生成 token —— token 由 start(run_strategy task)时才生成并注入容器,
        # 避免 pending run 持有一个永不生效的 token(会混淆)。
        run = StrategyRun.objects.create(
            user=request.user,
            strategy=strategy,
            credential=credential,
            env=env,
            symbol=symbol,
            params=params,
            name=name,
            run_token_hash="",
            status=StrategyRun.STATUS_PENDING,
        )

        data = StrategyRunReadSerializer(run).data
        return Response(data, status=status.HTTP_201_CREATED)


class StrategyRunDetailView(APIView):
    """GET /api/strategy/runs/<id> — detail of a single run (own runs only)."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request, pk):
        run = get_object_or_404(StrategyRun, pk=pk, user=request.user)
        return Response(StrategyRunReadSerializer(run).data)


class StrategyRunStartView(APIView):
    """POST /api/strategy/runs/<id>/start — trigger celery task to start container."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:run"]

    @audit("strategy.run.start")
    def post(self, request, pk):
        run = get_object_or_404(StrategyRun, pk=pk, user=request.user)

        if run.status == StrategyRun.STATUS_RUNNING:
            return Response(
                {"detail": "Run is already running."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from core.strategy.tasks import run_strategy

        run_strategy.delay(run.pk)
        logger.info("strategy.run.start: enqueued run_strategy task for run=%s", run.pk)

        return Response({"detail": "Start task enqueued.", "run_id": run.pk})


class StrategyRunStopView(APIView):
    """POST /api/strategy/runs/<id>/stop — trigger celery task to stop container."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:run"]

    @audit("strategy.run.stop")
    def post(self, request, pk):
        run = get_object_or_404(StrategyRun, pk=pk, user=request.user)

        if run.status not in (StrategyRun.STATUS_RUNNING, StrategyRun.STATUS_PENDING):
            return Response(
                {"detail": f"Cannot stop a run with status '{run.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from core.strategy.tasks import stop_strategy

        stop_strategy.delay(run.pk)
        logger.info("strategy.run.stop: enqueued stop_strategy task for run=%s", run.pk)

        return Response({"detail": "Stop task enqueued.", "run_id": run.pk})


class StrategyRunLogsView(APIView):
    """GET /api/strategy/runs/<id>/logs — retrieve logs for a run."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request, pk):
        run = get_object_or_404(StrategyRun, pk=pk, user=request.user)
        logs = run.logs.order_by("ts")
        return Response(StrategyLogSerializer(logs, many=True).data)


# ---------------------------------------------------------------------------
# Runner API — RunTokenAuthentication (no JWT)
# ---------------------------------------------------------------------------

class _RunnerBaseView(APIView):
    """Base class for runner API endpoints.

    Uses RunTokenAuthentication exclusively.  IsAuthenticated is still
    required — the RunTokenAuthentication sets request.user = run.user,
    so it satisfies the IsAuthenticated check.
    """

    authentication_classes = [RunTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @property
    def run(self):
        """Convenience: return the StrategyRun from request.auth."""
        return self.request.auth


class RunnerCandlesView(_RunnerBaseView):
    """GET /api/strategy/runner/candles?bar=1m&limit=100"""

    def get(self, request):
        bar = request.query_params.get("bar", "1m")
        limit = int(request.query_params.get("limit", 100))
        limit = max(1, min(limit, 300))  # clamp to sensible range

        from core.strategy.okx_bridge import runner_candles

        try:
            candles = runner_candles(self.run, bar=bar, limit=limit)
        except Exception as exc:
            logger.error("runner_candles error run=%s: %s", self.run.pk, exc)
            return Response(
                {"detail": f"OKX error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"candles": candles})


class RunnerOrderView(_RunnerBaseView):
    """POST /api/strategy/runner/order  body={side, sz, ord_type, px?}"""

    @audit("strategy.runner.order")
    def post(self, request):
        side = request.data.get("side", "")
        sz = request.data.get("sz", "")
        ord_type = request.data.get("ord_type", "market")
        px = request.data.get("px") or None

        if side not in ("buy", "sell") or not sz:
            return Response(
                {"detail": "side (buy/sell) and sz are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from core.strategy.okx_bridge import runner_place_order

        try:
            ord_id = runner_place_order(self.run, side=side, sz=sz, ord_type=ord_type, px=px)
        except Exception as exc:
            logger.error("runner_place_order error run=%s: %s", self.run.pk, exc)
            return Response(
                {"detail": f"Order error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"ordId": ord_id})


class RunnerLogView(_RunnerBaseView):
    """POST /api/strategy/runner/log  body={level, message}"""

    def post(self, request):
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        level = request.data.get("level", StrategyLog.LEVEL_INFO)
        message = request.data.get("message", "")

        if level not in dict(StrategyLog.LEVEL_CHOICES):
            level = StrategyLog.LEVEL_INFO

        log_entry = StrategyLog.objects.create(
            run=self.run,
            level=level,
            message=message,
        )

        # Broadcast to WS group so connected clients receive the log in real time.
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"strategy_run_{self.run.pk}",
                    {
                        "type": "strategy.log",
                        "run_id": self.run.pk,
                        "level": level,
                        "message": message,
                        "ts": log_entry.ts.isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "runner_log: channel_layer broadcast failed run=%s: %s",
                    self.run.pk,
                    exc,
                )

        return Response({"id": log_entry.pk}, status=status.HTTP_201_CREATED)
