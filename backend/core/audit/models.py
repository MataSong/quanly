from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="quanly_audit_logs",
    )
    action = models.CharField(max_length=100)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_audit"
        db_table = "quanly_audit_log"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user_id} at {self.created_at}"
