from django.conf import settings
from django.db import models

from apps.credentials.models import Env, ExchangeCredential


class InstType(models.TextChoices):
    SPOT = "SPOT", "现货"
    MARGIN = "MARGIN", "杠杆"
    SWAP = "SWAP", "永续合约"
    FUTURES = "FUTURES", "交割合约"
    OPTION = "OPTION", "期权"
    ETF = "ETF", "杠杆ETF"


class OrderSide(models.TextChoices):
    BUY = "buy", "买"
    SELL = "sell", "卖"


class PosSide(models.TextChoices):
    LONG = "long", "多"
    SHORT = "short", "空"
    NET = "net", "净"


class OrdType(models.TextChoices):
    MARKET = "market", "市价"
    LIMIT = "limit", "限价"


class OrderState(models.TextChoices):
    PENDING = "pending", "待成交"
    LIVE = "live", "挂单中"
    FILLED = "filled", "已成交"
    CANCELED = "canceled", "已撤销"


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    inst_type = models.CharField(max_length=8, choices=InstType.choices)
    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=4, choices=OrderSide.choices)
    pos_side = models.CharField(max_length=5, choices=PosSide.choices, default=PosSide.NET)
    ord_type = models.CharField(max_length=8, choices=OrdType.choices)
    px = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    sz = models.DecimalField(max_digits=24, decimal_places=8)
    td_mode = models.CharField(max_length=10, default="cash")
    lever = models.IntegerField(default=1)
    tp_px = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    sl_px = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    strike = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    expiry = models.CharField(max_length=32, blank=True, default="")
    opt_type = models.CharField(max_length=4, blank=True, default="")  # call/put
    state = models.CharField(max_length=10, choices=OrderState.choices, default=OrderState.PENDING)
    filled_sz = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    avg_px = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    exchange_order_id = models.CharField(max_length=64, blank=True, default="")
    client_order_id = models.CharField(max_length=64, blank=True, default="")
    credential = models.ForeignKey(
        ExchangeCredential, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "env", "state"])]


class Trade(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="trades")
    price = models.DecimalField(max_digits=24, decimal_places=8)
    sz = models.DecimalField(max_digits=24, decimal_places=8)
    ts = models.DateTimeField(auto_now_add=True)


class Position(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    inst_type = models.CharField(max_length=8, choices=InstType.choices, default=InstType.SWAP)
    symbol = models.CharField(max_length=32)
    pos_side = models.CharField(max_length=5, choices=PosSide.choices, default=PosSide.LONG)
    qty = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    avg_px = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    lever = models.IntegerField(default=1)
    margin = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    liq_px = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "env", "symbol", "pos_side")


class Balance(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    ccy = models.CharField(max_length=16)
    total = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    frozen = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        unique_together = ("user", "env", "ccy")

    @property
    def available(self):
        return self.total - self.frozen


class Bill(models.Model):
    class BillType(models.TextChoices):
        TRADE = "trade", "交易"
        CLOSE_PNL = "close_pnl", "平仓盈亏"
        FEE = "fee", "手续费"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    bill_type = models.CharField(max_length=12, choices=BillType.choices)
    ccy = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    symbol = models.CharField(max_length=32, blank=True, default="")
    balance_after = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ts"]
        indexes = [models.Index(fields=["user", "env"])]
