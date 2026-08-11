from django.conf import settings
from django.db import models


class Backtest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    strategy = models.ForeignKey(
        "strategy.Strategy", null=True, blank=True, on_delete=models.SET_NULL
    )
    name = models.CharField(max_length=80, blank=True, default="")
    symbol = models.CharField(max_length=32, default="BTC-USDT")
    bar = models.CharField(max_length=8, default="1m")
    bars = models.IntegerField(default=500)
    initial_capital = models.DecimalField(max_digits=24, decimal_places=8, default=10000)
    fee_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0.0005)
    result_json = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
