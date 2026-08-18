"""Strategy app views.

Two families:
  1. Management API  — JWT + permission checks (strategy:* perms).
  2. Runner API      — RunTokenAuthentication only (no JWT, no page perm).
"""
import logging

from django.db.models import Q
from django.db.models import ProtectedError
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
    """Full serializer for Strategy, including marketplace / CRUD fields.

    Params visibility rules (防御性脱敏):
      - 内置策略 (owner=None): params 正常返回 (就是 default_params)
      - 自己的策略: params 正常返回
      - 他人的 public+approved 策略: params 正常返回 (供参考)
      - 他人的私有策略: params 返回 {} (防御; 理论上 detail 端点对他人私有返回 404,
        list 端点已过滤不出现他人私有, 但保留此 guard 防止未来 query 变化时泄露)
    """

    owner_username = drf_serializers.SerializerMethodField()
    is_owner = drf_serializers.SerializerMethodField()
    params = drf_serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = [
            "id", "name", "source_type", "code_ref", "default_params", "is_builtin",
            "created_at", "updated_at",
            # marketplace fields
            "owner_username", "template_ref", "params", "visibility", "status",
            "description", "reject_reason", "is_owner",
        ]

    def _request(self):
        return self.context.get("request")

    def get_owner_username(self, obj) -> str:
        return obj.owner.username if obj.owner_id else ""

    def get_is_owner(self, obj) -> bool:
        req = self._request()
        if req is None or obj.owner_id is None:
            return False
        return obj.owner_id == req.user.id

    def get_params(self, obj) -> dict:
        req = self._request()
        # 内置策略: return params (内置用 default_params, 用户实例用 params)
        if obj.owner_id is None:
            return obj.params if obj.params else obj.default_params
        # 自己的策略: 正常返回
        if req is not None and obj.owner_id == req.user.id:
            return obj.params
        # 他人策略: 只有 public+approved 才暴露 params
        if obj.visibility == Strategy.VISIBILITY_PUBLIC and obj.status == Strategy.STATUS_APPROVED:
            return obj.params
        # 他人私有/pending/rejected: 脱敏
        return {}


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
# Helpers
# ---------------------------------------------------------------------------

def _marketplace_qs(user):
    """Return strategies visible to user: public+approved | own | builtin."""
    return Strategy.objects.filter(
        Q(status=Strategy.STATUS_APPROVED, visibility=Strategy.VISIBILITY_PUBLIC)
        | Q(owner=user)
        | Q(owner__isnull=True)
    ).distinct()


def _serialize(strategy, request):
    return StrategySerializer(strategy, context={"request": request}).data


def _serialize_many(qs, request):
    return StrategySerializer(qs, many=True, context={"request": request}).data


# ---------------------------------------------------------------------------
# Management API — JWT authenticated
# ---------------------------------------------------------------------------

class StrategyListView(APIView):
    """GET /api/strategy/strategies — list available strategies (marketplace view)."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request):
        strategies = _marketplace_qs(request.user)
        return Response(_serialize_many(strategies, request))


# ---------------------------------------------------------------------------
# Marketplace & My Strategies
# ---------------------------------------------------------------------------

class MarketplaceListView(APIView):
    """GET /api/strategy/marketplace — public+approved strategies + own + builtin."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request):
        qs = _marketplace_qs(request.user)
        return Response(_serialize_many(qs, request))


class MyStrategiesListView(APIView):
    """GET /api/strategy/mine — strategies owned by the current user."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:view"]

    def get(self, request):
        qs = Strategy.objects.filter(owner=request.user)
        return Response(_serialize_many(qs, request))


# ---------------------------------------------------------------------------
# Strategy CRUD
# ---------------------------------------------------------------------------

class StrategyCreateView(APIView):
    """POST /api/strategy/strategies — create a user parameterized strategy instance."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:create"]

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        template_ref = (request.data.get("template_ref") or "").strip()
        params = request.data.get("params") or {}
        description = (request.data.get("description") or "").strip()
        visibility = request.data.get("visibility", Strategy.VISIBILITY_PRIVATE)

        if not name:
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not template_ref:
            return Response({"detail": "template_ref is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate template_ref: must exist as a builtin strategy (owner=None)
        if not Strategy.objects.filter(owner__isnull=True, code_ref=template_ref).exists():
            return Response(
                {"detail": f"Invalid template_ref '{template_ref}': no builtin strategy found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if visibility not in (Strategy.VISIBILITY_PRIVATE, Strategy.VISIBILITY_PUBLIC):
            visibility = Strategy.VISIBILITY_PRIVATE

        strategy = Strategy.objects.create(
            owner=request.user,
            name=name,
            source_type=Strategy.SOURCE_UPLOADED,
            is_builtin=False,
            code_ref=template_ref,          # tasks.py picks up template via code_ref/template_ref
            template_ref=template_ref,
            params=params,
            default_params={},
            description=description,
            visibility=visibility,
            status=Strategy.STATUS_DRAFT,
        )
        return Response(_serialize(strategy, request), status=status.HTTP_201_CREATED)


class StrategyDetailView(APIView):
    """GET  /api/strategy/strategies/<pk> — detail; 404 for other-user private.
    PUT  /api/strategy/strategies/<pk> — update own strategy.
    DELETE /api/strategy/strategies/<pk> — delete own strategy.
    """

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = {
        "GET": ["strategy:view"],
        "PUT": ["strategy:update"],
        "DELETE": ["strategy:delete"],
    }

    def _get_for_read(self, pk, user):
        """Return strategy or raise 404 with access control."""
        strategy = get_object_or_404(Strategy, pk=pk)
        # 内置策略: always readable
        if strategy.owner_id is None:
            return strategy
        # Own strategy: always readable
        if strategy.owner_id == user.id:
            return strategy
        # Other-user public+approved: readable
        if strategy.visibility == Strategy.VISIBILITY_PUBLIC and strategy.status == Strategy.STATUS_APPROVED:
            return strategy
        # All other cases (other user's private / pending / rejected): 404
        from django.http import Http404
        raise Http404

    def get(self, request, pk):
        strategy = self._get_for_read(pk, request.user)
        data = _serialize(strategy, request)
        data["performance"] = {}  # reserved for M-T4
        return Response(data)

    def put(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk, owner=request.user)

        name = (request.data.get("name") or "").strip() or strategy.name
        params = request.data.get("params", strategy.params)
        description = request.data.get("description", strategy.description)
        visibility = request.data.get("visibility", strategy.visibility)

        if visibility not in (Strategy.VISIBILITY_PRIVATE, Strategy.VISIBILITY_PUBLIC):
            visibility = strategy.visibility

        # Reset status to draft if strategy was not already draft
        new_status = strategy.status
        if strategy.status in (Strategy.STATUS_APPROVED, Strategy.STATUS_PENDING, Strategy.STATUS_REJECTED):
            new_status = Strategy.STATUS_DRAFT

        strategy.name = name
        strategy.params = params
        strategy.description = description
        strategy.visibility = visibility
        strategy.status = new_status
        strategy.save(update_fields=["name", "params", "description", "visibility", "status", "updated_at"])

        return Response(_serialize(strategy, request))

    def delete(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk, owner=request.user)
        try:
            strategy.delete()
        except ProtectedError:
            return Response(
                {"detail": "该策略有运行记录，请先停止并删除相关运行。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StrategySubmitView(APIView):
    """POST /api/strategy/strategies/<pk>/submit — submit own strategy for review."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:update"]

    def post(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk, owner=request.user)
        strategy.visibility = Strategy.VISIBILITY_PUBLIC
        strategy.status = Strategy.STATUS_PENDING
        strategy.save(update_fields=["visibility", "status", "updated_at"])
        return Response(_serialize(strategy, request))


# ---------------------------------------------------------------------------
# Admin review endpoints
# ---------------------------------------------------------------------------

class AdminPendingView(APIView):
    """GET /api/strategy/admin/pending — list strategies pending review."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:audit"]

    def get(self, request):
        qs = Strategy.objects.filter(status=Strategy.STATUS_PENDING)
        return Response(_serialize_many(qs, request))


class AdminReviewView(APIView):
    """POST /api/strategy/admin/strategies/<pk>/review — approve or reject a strategy."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["strategy:audit"]

    def post(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk)
        action = (request.data.get("action") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        if action == "approve":
            strategy.status = Strategy.STATUS_APPROVED
            strategy.reject_reason = ""
            strategy.save(update_fields=["status", "reject_reason", "updated_at"])
        elif action == "reject":
            strategy.status = Strategy.STATUS_REJECTED
            strategy.reject_reason = reason
            strategy.save(update_fields=["status", "reject_reason", "updated_at"])
        else:
            return Response(
                {"detail": "action must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(_serialize(strategy, request))


# ---------------------------------------------------------------------------
# Strategy Runs
# ---------------------------------------------------------------------------

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

        # ── Run authorization guard (security core) ──────────────────────────
        # Allow if: builtin strategy (owner=None), OR own strategy, OR
        # public+approved strategy. Deny everything else with 403.
        is_builtin = strategy.owner_id is None
        is_own = strategy.owner_id == request.user.id
        is_public_approved = (
            strategy.visibility == Strategy.VISIBILITY_PUBLIC
            and strategy.status == Strategy.STATUS_APPROVED
        )
        if not (is_builtin or is_own or is_public_approved):
            return Response(
                {"detail": "您无权使用该策略。"},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        # Use strategy's stored params for user-parameterized strategies;
        # fall back to request params (or empty dict) for builtin strategies.
        run_params = strategy.params if strategy.params else params

        # 创建时不生成 token —— token 由 start(run_strategy task)时才生成并注入容器,
        # 避免 pending run 持有一个永不生效的 token(会混淆)。
        # run_token_hash 有 unique 约束,pending 期用唯一占位(非真 token hash,
        # 加 "pending:" 前缀避免与 sha256 hash 碰撞),防止多个 pending run 空串冲突。
        import uuid

        run = StrategyRun.objects.create(
            user=request.user,
            strategy=strategy,
            credential=credential,
            env=env,
            symbol=symbol,
            params=run_params,
            name=name,
            run_token_hash=f"pending:{uuid.uuid4().hex}",
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
