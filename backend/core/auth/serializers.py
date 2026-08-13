from django.contrib.auth.models import User
from rest_framework import serializers

from core.accounts.services import get_effective_permissions


class UserSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    auth_source = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "is_superuser", "permissions", "auth_source"]

    def get_permissions(self, obj) -> list[str]:
        return sorted(get_effective_permissions(obj))

    def get_auth_source(self, obj) -> str:
        profile = getattr(obj, "userprofile", None)
        return profile.auth_source if profile else "local"
