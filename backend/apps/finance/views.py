from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Transfer

D = Decimal


def _okx(user, env):
    """取该用户该环境的 OKX 适配器(用其 credential);无则 None。"""
    from apps.credentials.models import Env, ExchangeCredential
    from apps.exchanges.factory import AdapterFactory

    cred = ExchangeCredential.objects.filter(user=user, env=env, exchange="okx").first()
    if not cred:
        return None
    return AdapterFactory.create("okx", Env.SIM if env == "sim" else Env.LIVE, cred)


@api_view(["POST"])
def transfer(request):
    env = request.data.get("env", "sim")
    ccy = request.data["ccy"]
    amount = D(str(request.data["amount"]))
    adapter = _okx(request.user, env)
    if not adapter:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    try:
        adapter.transfer(ccy, amount)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"OKX 划转失败: {e}"}, status=502)
    t = Transfer.objects.create(
        user=request.user,
        env=env,
        ccy=ccy,
        amount=amount,
        from_acct=request.data.get("from_acct", "trading"),
        to_acct=request.data.get("to_acct", "funding"),
    )
    return Response({"id": t.id}, status=201)


@api_view(["GET"])
def transfers(request):
    env = request.query_params.get("env", "sim")
    qs = Transfer.objects.filter(user=request.user, env=env)[:100]
    return Response(
        [
            {
                "id": t.id, "ccy": t.ccy, "amount": float(t.amount),
                "from_acct": t.from_acct, "to_acct": t.to_acct,
                "created_at": t.created_at.isoformat(),
            }
            for t in qs
        ]
    )
