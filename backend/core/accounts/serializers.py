from django.contrib.auth.models import User
from rest_framework import serializers

from core.accounts.models import Role, UserPermissionOverride
from core.accounts.permissions_registry import ALL_PERMISSION_CODES


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "description", "permissions", "is_system", "created_at"]
        read_only_fields = ["is_system", "created_at"]

    def validate_permissions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("permissions must be a list")
        bad = [p for p in value if p not in ALL_PERMISSION_CODES]
        if bad:
            raise serializers.ValidationError(f"unknown permissions: {bad}")
        return value


class AdminUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    auth_source = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_active",
                  "is_superuser", "roles", "auth_source"]

    def get_roles(self, obj):
        return list(
            Role.objects.filter(userrole__user=obj)
            .values_list("id", flat=True)
        )

    def get_auth_source(self, obj) -> str:
        try:
            profile = obj.userprofile
            return profile.auth_source
        except Exception:
            return "local"


class OverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPermissionOverride
        fields = ["id", "permission", "effect"]

    def validate_permission(self, value):
        if value not in ALL_PERMISSION_CODES:
            raise serializers.ValidationError(f"unknown permission: {value}")
        return value
