from django.contrib.auth.models import User
from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    permissions = models.JSONField(default=list)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "role")


class UserPermissionOverride(models.Model):
    GRANT = "grant"
    DENY = "deny"
    EFFECT_CHOICES = [(GRANT, "grant"), (DENY, "deny")]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission = models.CharField(max_length=64)
    effect = models.CharField(max_length=8, choices=EFFECT_CHOICES)

    class Meta:
        unique_together = ("user", "permission")


class UserProfile(models.Model):
    LOCAL = "local"
    SSO = "sso"
    AUTH_SOURCE_CHOICES = [(LOCAL, "local"), (SSO, "sso")]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    auth_source = models.CharField(
        max_length=16,
        choices=AUTH_SOURCE_CHOICES,
        default=LOCAL,
    )
    external_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
