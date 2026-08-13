from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.accounts.drf import HasRequiredPermissions
from core.audit.decorators import audit
from core.credentials.models import Credential
from core.credentials.serializers import CredentialReadSerializer, CredentialWriteSerializer


class CredentialViewSet(viewsets.ModelViewSet):
    """CRUD for the current user's OKX credentials.

    Multi-tenant: queryset is always scoped to request.user.
    Permissions: GET requires credentials:view; write ops require credentials:manage.
    """

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    # 密钥不支持编辑,只能删除后重建 —— 禁用 PUT/PATCH(否则 WriteSerializer 无 update() 会 500)。
    http_method_names = ["get", "post", "delete", "head", "options"]
    required_permissions = {
        "GET": ["credentials:view"],
        "POST": ["credentials:manage"],
        "DELETE": ["credentials:manage"],
    }

    # Serializer selection: different serializers for read vs write.
    def get_serializer_class(self):
        if self.request.method == "POST":
            return CredentialWriteSerializer
        return CredentialReadSerializer

    def get_queryset(self):
        """Always return only the current user's credentials."""
        return Credential.objects.filter(user=self.request.user)

    @audit("credentials.create")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            CredentialReadSerializer(obj).data,
            status=status.HTTP_201_CREATED,
        )

    @audit("credentials.delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
