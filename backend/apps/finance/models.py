from django.conf import settings
from django.db import models

from apps.credentials.models import Env


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
