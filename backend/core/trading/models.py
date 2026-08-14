from django.contrib.auth.models import User
from django.db import models

from core.credentials.models import Credential


class Order(models.Model):
    """Local record of an order placed via OKX.

    Stores only metadata — never stores raw API keys or secrets.
    The credential FK links back to the encrypted credential used.
    """

    INST_TYPE_SPOT = "SPOT"
    INST_TYPE_SWAP = "SWAP"
    INST_TYPE_CHOICES = [
        (INST_TYPE_SPOT, "Spot"),
        (INST_TYPE_SWAP, "Perpetual Swap"),
    ]

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

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="trading_orders",
        db_index=True,
    )
    credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        related_name="trading_orders",
    )
    env = models.CharField(max_length=8, choices=ENV_CHOICES)
    inst_type = models.CharField(max_length=8, choices=INST_TYPE_CHOICES)
    inst_id = models.CharField(max_length=32)
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    ord_type = models.CharField(max_length=16, choices=ORD_TYPE_CHOICES)
    pos_side = models.CharField(max_length=8, blank=True, default="")
    sz = models.CharField(max_length=32)
    px = models.CharField(max_length=32, blank=True, default="")
    td_mode = models.CharField(max_length=16)
    reduce_only = models.BooleanField(default=False)
    okx_ord_id = models.CharField(max_length=64, db_index=True)
    cl_ord_id = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=32, default="live")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_trading"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["okx_ord_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"<Order user={self.user_id} env={self.env} "
            f"inst={self.inst_id} side={self.side} ordId={self.okx_ord_id}>"
        )
