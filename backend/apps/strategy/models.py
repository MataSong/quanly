import secrets

from django.conf import settings
from django.db import models

from apps.credentials.models import Env, ExchangeCredential


def gen_run_token() -> str:
    return secrets.token_urlsafe(32)


class Strategy(models.Model):
    class Kind(models.TextChoices):
        BUILTIN = "builtin", "内置"
        UPLOADED = "uploaded", "自定义"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    language = models.CharField(max_length=16, default="python")
    source = models.TextField()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.UPLOADED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class StrategyRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "启动中"
        RUNNING = "running", "运行中"
        STOPPED = "stopped", "已停止"
        ERROR = "error", "异常"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="runs")
    env = models.CharField(max_length=4, choices=Env.choices)
    credential = models.ForeignKey(
        ExchangeCredential, null=True, blank=True, on_delete=models.SET_NULL
    )
    symbol = models.CharField(max_length=32, default="BTC-USDT")
    interval_sec = models.IntegerField(default=5)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    container_id = models.CharField(max_length=80, blank=True, default="")
    run_token = models.CharField(max_length=64, unique=True, default=gen_run_token)
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class StrategyLog(models.Model):
    run = models.ForeignKey(StrategyRun, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=8, default="info")
    message = models.TextField()
    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ts"]
