"""Strategy models: Strategy, StrategyRun, StrategyLog, StrategyOrder."""
from django.contrib.auth.models import User
from django.db import models

from core.credentials.models import Credential


class Strategy(models.Model):
    """Describes a trading strategy (builtin or user-uploaded)."""

    SOURCE_BUILTIN = "builtin"
    SOURCE_UPLOADED = "uploaded"
    SOURCE_CHOICES = [
        (SOURCE_BUILTIN, "Built-in"),
        (SOURCE_UPLOADED, "Uploaded"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_PUBLIC, "Public"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    name = models.CharField(max_length=128)
    source_type = models.CharField(
        max_length=16, choices=SOURCE_CHOICES, default=SOURCE_BUILTIN
    )
    # For builtin: identifier like "dual_ma". For uploaded: filename/ref.
    code_ref = models.CharField(max_length=128)
    default_params = models.JSONField(default=dict)
    is_builtin = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── 商城字段 ──────────────────────────────────────────────────────────────
    # 内置策略 owner=None;用户参数化实例 owner=创建者。
    owner = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="strategies"
    )
    # 用户参数化实例指向的内置模板 code_ref(内置策略自身此字段为空)。
    template_ref = models.CharField(max_length=128, blank=True, default="")
    # 用户调好的参数(内置策略用 default_params)。
    params = models.JSONField(default=dict)
    visibility = models.CharField(
        max_length=16, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    description = models.TextField(blank=True, default="")
    reject_reason = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core_strategy"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"<Strategy {self.name!r} source={self.source_type} ref={self.code_ref!r}>"


class StrategyRun(models.Model):
    """A single execution run of a strategy for a user."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_STOPPED = "stopped"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_STOPPED, "Stopped"),
        (STATUS_ERROR, "Error"),
    ]

    ENV_SIM = "sim"
    ENV_LIVE = "live"
    ENV_CHOICES = [
        (ENV_SIM, "Simulated"),
        (ENV_LIVE, "Live"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="strategy_runs",
        db_index=True,
    )
    strategy = models.ForeignKey(
        Strategy,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    credential = models.ForeignKey(
        Credential,
        on_delete=models.PROTECT,
        related_name="strategy_runs",
        null=True,
        blank=True,
    )
    env = models.CharField(max_length=8, choices=ENV_CHOICES)
    symbol = models.CharField(max_length=32)
    params = models.JSONField(default=dict)
    # Human-readable run name (optional; auto-generated if empty).
    name = models.CharField(max_length=128, blank=True, default="")
    # SHA-256 hex digest of the run token — never store the plaintext token.
    run_token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # Docker container ID once the run is started.
    container_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_strategy"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["run_token_hash"]),
        ]

    def __str__(self) -> str:
        return (
            f"<StrategyRun id={self.pk} user={self.user_id} "
            f"strategy={self.strategy_id} status={self.status}>"
        )


class StrategyLog(models.Model):
    """A log entry emitted by a running strategy."""

    LEVEL_INFO = "info"
    LEVEL_BUY = "buy"
    LEVEL_SELL = "sell"
    LEVEL_WARN = "warn"
    LEVEL_ERROR = "error"
    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_BUY, "Buy"),
        (LEVEL_SELL, "Sell"),
        (LEVEL_WARN, "Warn"),
        (LEVEL_ERROR, "Error"),
    ]

    run = models.ForeignKey(
        StrategyRun,
        on_delete=models.CASCADE,
        related_name="logs",
        db_index=True,
    )
    level = models.CharField(max_length=8, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    message = models.TextField()
    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_strategy"
        ordering = ["ts"]

    def __str__(self) -> str:
        return f"<StrategyLog run={self.run_id} level={self.level} ts={self.ts}>"


class StrategyOrder(models.Model):
    """An order placed by a strategy run — links trading activity to the run."""

    SIDE_BUY = "buy"
    SIDE_SELL = "sell"
    SIDE_CHOICES = [
        (SIDE_BUY, "Buy"),
        (SIDE_SELL, "Sell"),
    ]

    ORD_TYPE_MARKET = "market"
    ORD_TYPE_LIMIT = "limit"
    ORD_TYPE_CHOICES = [
        (ORD_TYPE_MARKET, "Market"),
        (ORD_TYPE_LIMIT, "Limit"),
    ]

    ENV_SIM = "sim"
    ENV_LIVE = "live"
    ENV_CHOICES = [
        (ENV_SIM, "Simulated"),
        (ENV_LIVE, "Live"),
    ]

    run = models.ForeignKey(
        StrategyRun,
        on_delete=models.CASCADE,
        related_name="strategy_orders",
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="strategy_orders",
        db_index=True,
    )
    credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        related_name="strategy_orders",
    )
    env = models.CharField(max_length=8, choices=ENV_CHOICES)
    inst_type = models.CharField(max_length=8, default="SPOT")
    inst_id = models.CharField(max_length=32)
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    ord_type = models.CharField(max_length=16, choices=ORD_TYPE_CHOICES)
    sz = models.CharField(max_length=32)
    px = models.CharField(max_length=32, blank=True, default="")
    td_mode = models.CharField(max_length=16, default="cash")
    okx_ord_id = models.CharField(max_length=64, db_index=True)
    cl_ord_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_strategy"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run", "-created_at"]),
            models.Index(fields=["okx_ord_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"<StrategyOrder run={self.run_id} side={self.side} "
            f"inst={self.inst_id} ordId={self.okx_ord_id}>"
        )
