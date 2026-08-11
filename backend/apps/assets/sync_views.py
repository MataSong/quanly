"""手动/进入页触发 OKX 全量同步。"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.credentials.models import Env, ExchangeCredential
from apps.exchanges.factory import AdapterFactory
from apps.trading import sync


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def full_sync(request):
    env = request.data.get("env", "sim")
    cred = ExchangeCredential.objects.filter(
        user=request.user, env=env, exchange="okx"
    ).first()
    if not cred:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    x_env = Env.SIM if env == "sim" else Env.LIVE
    adapter = AdapterFactory.create("okx", x_env, cred)
    try:
        sync.full_sync(request.user, env, adapter)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"同步失败: {e}"}, status=502)
    return Response({"ok": True})
