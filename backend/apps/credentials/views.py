from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.exchanges.factory import AdapterFactory
from apps.exchanges.types import Env

from .connectivity import check_okx
from .crypto import decrypt
from .models import ExchangeCredential
from .serializers import CredentialReadSerializer, CredentialWriteSerializer


class CredentialViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return ExchangeCredential.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CredentialWriteSerializer
        return CredentialReadSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """测试已保存凭证的连通性:解密后调 OKX 私有接口。"""
        cred = self.get_object()
        ok, msg = check_okx(
            cred.env,
            cred.api_key,
            decrypt(cred.secret_enc),
            decrypt(cred.passphrase_enc),
        )
        return Response({"ok": ok, "detail": "OK" if ok else msg},
                        status=200 if ok else 400)
