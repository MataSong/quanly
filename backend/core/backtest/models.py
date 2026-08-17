"""Backtest models: Backtest, BacktestTrade."""
from django.contrib.auth.models import User
from django.db import models

from core.strategy.models import Strategy


class Backtest(models.Model):
    """A single backtest run request: strategy + time range + params → results."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_ERROR, "Error"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="backtests",
        db_index=True,
    )
    strategy = models.ForeignKey(
        Strategy,
        on_delete=models.PROTECT,
        related_name="backtests",
    )
    symbol = models.CharField(max_length=32)
    bar = models.CharField(max_length=8, default="1m")
    # millisecond epoch timestamps for the backtest window
    start_ts = models.BigIntegerField()
    end_ts = models.BigIntegerField()
    params = models.JSONField(default=dict)
    init_cash = models.FloatField(default=10000.0)
    fee_rate = models.FloatField(default=0.001)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # Results populated after engine completes
    metrics = models.JSONField(default=dict)
    equity_curve = models.JSONField(default=list)
    error_msg = models.TextField(default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_backtest"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"<Backtest id={self.pk} user={self.user_id} "
            f"strategy={self.strategy_id} status={self.status}>"
        )


class BacktestTrade(models.Model):
    """A simulated fill produced by the backtest engine."""

    SIDE_BUY = "buy"
    SIDE_SELL = "sell"
    SIDE_CHOICES = [
        (SIDE_BUY, "Buy"),
        (SIDE_SELL, "Sell"),
    ]

    backtest = models.ForeignKey(
        Backtest,
        on_delete=models.CASCADE,
        related_name="trades",
        db_index=True,
    )
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    ts = models.BigIntegerField()          # millisecond epoch of the fill bar
    price = models.FloatField()
    sz = models.FloatField()
    fee = models.FloatField()
    pnl = models.FloatField(default=0.0)   # realised PnL on close (sell)

    class Meta:
        app_label = "core_backtest"
        ordering = ["ts"]

    def __str__(self) -> str:
        return (
            f"<BacktestTrade backtest={self.backtest_id} side={self.side} "
            f"ts={self.ts} price={self.price}>"
        )
