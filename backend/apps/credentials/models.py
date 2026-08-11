from django.conf import settings
from django.db import models


class Env(models.TextChoices):
    SIM = "sim", "模拟盘"
    LIVE = "live", "实盘"


class ExchangeCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exchange = models.CharField(max_length=16, default="okx")
    env = models.CharField(max_length=4, choices=Env.choices)
    label = models.CharField(max_length=64, default="default")
    api_key = models.CharField(max_length=128)
    secret_enc = models.TextField()
    passphrase_enc = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "exchange", "env", "label")

    def __str__(self):
        return f"{self.exchange}:{self.env}:{self.label}"
