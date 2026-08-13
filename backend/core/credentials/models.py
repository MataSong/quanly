from django.contrib.auth.models import User
from django.db import models


class Credential(models.Model):
    """Stores an OKX API credential for a user, encrypted at rest."""

    ENV_SIM = "sim"
    ENV_LIVE = "live"
    ENV_CHOICES = [
        (ENV_SIM, "Simulated"),
        (ENV_LIVE, "Live"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="credentials",
        db_index=True,
    )
    env = models.CharField(max_length=8, choices=ENV_CHOICES)
    label = models.CharField(max_length=64)

    # Encrypted fields — stored as Fernet tokens (TextField, variable length).
    api_key_enc = models.TextField()
    secret_enc = models.TextField()
    passphrase_enc = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core_credentials"
        # Each user may have at most one credential per (env, label) pair.
        unique_together = [("user", "env", "label")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"<Credential user={self.user_id} env={self.env} label={self.label!r}>"
