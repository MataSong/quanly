from django.contrib.auth.models import User
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit.decorators import audit
from core.accounts.models import (
    Role, UserRole, UserPermissionOverride, UserProfile,
)
from core.accounts.permissions_registry import PERMISSION_GROUPS
from core.accounts.serializers import (
    RoleSerializer, AdminUserSerializer, OverrideSerializer,
)
from core.auth.password_rules import validate_password_strength


class IsSuperUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_superuser)


class PermissionsListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get(self, request):
        return Response({"data": PERMISSION_GROUPS})


class RoleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSuperUser]
    queryset = Role.objects.all().order_by("name")
    serializer_class = RoleSerializer

    @audit("accounts.role.create")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @audit("accounts.role.update")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @audit("accounts.role.delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_system:
            return Response(
                {"code": "role_is_system", "message": "system role cannot be deleted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSuperUser]
    queryset = User.objects.all().order_by("username")
    serializer_class = AdminUserSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    @audit("accounts.user.delete")
    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        # 先查"删自己"再查"删超管":两条保护相互独立,
        # 避免 is_superuser 在前时 cannot_delete_self 分支永远不可达(死代码)。
        if user.id == request.user.id:
            return Response(
                {"code": "cannot_delete_self",
                 "message": "cannot delete yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_superuser:
            return Response(
                {"code": "cannot_delete_superuser",
                 "message": "superuser cannot be deleted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @audit("accounts.user.create")
    def create(self, request, *args, **kwargs):
        username = (request.data.get("username") or "").strip()
        email = request.data.get("email") or ""
        if not username:
            return Response(
                {"code": "bad_request", "message": "username required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username=username).exists():
            return Response(
                {"code": "user_exists", "message": "username already taken"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        password = request.data.get("password") or ""
        ok, msg = validate_password_strength(password)
        if not ok:
            return Response(
                {"code": "weak_password", "message": msg},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.create_user(
            username=username, password=password, email=email)
        UserProfile.objects.update_or_create(
            user=user, defaults={"auth_source": "local"})
        return Response(AdminUserSerializer(user).data,
                        status=status.HTTP_201_CREATED)

    @audit("accounts.user.set_roles")
    @action(detail=True, methods=["put"])
    def roles(self, request, pk=None):
        user = self.get_object()
        role_ids = request.data.get("role_ids", [])
        UserRole.objects.filter(user=user).delete()
        for rid in role_ids:
            role = Role.objects.filter(pk=rid).first()
            if role:
                UserRole.objects.create(user=user, role=role)
        return Response({"data": AdminUserSerializer(user).data})

    @audit("accounts.user.set_active")
    @action(detail=True, methods=["post"])
    def set_active(self, request, pk=None):
        user = self.get_object()
        user.is_active = bool(request.data.get("is_active", True))
        user.save(update_fields=["is_active"])
        return Response({"data": {"is_active": user.is_active}})

    @audit("accounts.user.reset_password")
    @action(detail=True, methods=["post"])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get("password") or ""
        ok, msg = validate_password_strength(password)
        if not ok:
            return Response(
                {"code": "weak_password", "message": msg},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(password)
        user.save(update_fields=["password"])
        return Response({"data": {"ok": True}})

    @action(detail=True, methods=["get", "post"])
    def overrides(self, request, pk=None):
        user = self.get_object()
        if request.method == "GET":
            qs = UserPermissionOverride.objects.filter(user=user)
            return Response({"data": OverrideSerializer(qs, many=True).data})
        return self._add_override(request, user)

    @audit("accounts.user.add_override")
    def _add_override(self, request, user):
        serializer = OverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj, _ = UserPermissionOverride.objects.update_or_create(
            user=user,
            permission=serializer.validated_data["permission"],
            defaults={"effect": serializer.validated_data["effect"]},
        )
        return Response(OverrideSerializer(obj).data,
                        status=status.HTTP_201_CREATED)

    @audit("accounts.user.delete_override")
    @action(detail=True, methods=["delete"],
            url_path=r"overrides/(?P<override_id>\d+)")
    def delete_override(self, request, pk=None, override_id=None):
        user = self.get_object()
        deleted, _ = UserPermissionOverride.objects.filter(
            user=user, pk=override_id).delete()
        if not deleted:
            return Response(
                {"code": "override_not_found", "message": "override not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
