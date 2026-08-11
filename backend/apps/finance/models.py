from django.conf import settings
from django.db import models

from apps.credentials.models import Env


class FinanceProduct(models.Model):
    class Category(models.TextChoices):
        FLEXIBLE = "flexible", "活期理财"
        FIXED = "fixed", "定期理财"
        DUAL = "dual", "双币理财"
        STAKING = "staking", "Staking 质押"
        LOAN = "loan", "借贷"

    name = models.CharField(max_length=64)
    category = models.CharField(max_length=12, choices=Category.choices)
    ccy = models.CharField(max_length=16, default="USDT")
    apr = models.DecimalField(max_digits=6, decimal_places=4, default=0)  # 年化,如 0.03
    term_days = models.IntegerField(default=0)  # 0=活期
    min_amount = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        ordering = ["category", "id"]


class FinanceHolding(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    product = models.ForeignKey(FinanceProduct, on_delete=models.CASCADE)
    principal = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    earnings = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Transfer(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    ccy = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    from_acct = models.CharField(max_length=24)  # trading/funding/earn
    to_acct = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
