from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import FinanceHolding, FinanceProduct, Transfer

D = Decimal


def _okx(user, env):
    """取该用户该环境的 OKX 适配器(用其 credential);无则 None。"""
    from apps.credentials.models import Env, ExchangeCredential
    from apps.exchanges.factory import AdapterFactory

    cred = ExchangeCredential.objects.filter(user=user, env=env, exchange="okx").first()
    if not cred:
        return None
    return AdapterFactory.create("okx", Env.SIM if env == "sim" else Env.LIVE, cred)


@api_view(["GET"])
def products(request):
    """活期理财可申购币种,来自 OKX 公共借贷利率(真实)。

    以 OKX 返回的币种为准回填 FinanceProduct 展示缓存(仅 flexible)。
    未配置凭证时返回已有缓存。
    """
    env = request.query_params.get("env", "sim")
    adapter = _okx(request.user, env)
    if adapter:
        try:
            for item in adapter.get_savings_products():
                FinanceProduct.objects.update_or_create(
                    category="flexible",
                    ccy=item["ccy"],
                    defaults={
                        "name": f"{item['ccy']} 活期",
                        "apr": D(str(item["apr"])),
                        "term_days": 0,
                        "min_amount": D("0"),
                    },
                )
        except Exception:  # noqa: BLE001
            pass

    qs = FinanceProduct.objects.all()
    cat = request.query_params.get("category")
    if cat == "loan":
        qs = qs.filter(category="loan")
    elif cat == "earn":
        qs = qs.exclude(category="loan")
    return Response(
        [
            {
                "id": p.id, "name": p.name, "category": p.category, "ccy": p.ccy,
                "apr": float(p.apr), "term_days": p.term_days, "min_amount": float(p.min_amount),
            }
            for p in qs
        ]
    )


@api_view(["GET"])
def holdings(request):
    env = request.query_params.get("env", "sim")
    qs = FinanceHolding.objects.filter(user=request.user, env=env, active=True)
    return Response(
        [
            {
                "id": h.id, "product": h.product.name, "category": h.product.category,
                "ccy": h.product.ccy, "apr": float(h.product.apr),
                "principal": float(h.principal), "earnings": float(h.earnings),
            }
            for h in qs
        ]
    )


@api_view(["POST"])
def subscribe(request):
    env = request.data.get("env", "sim")
    product = get_object_or_404(FinanceProduct, pk=request.data["product_id"])
    amount = D(str(request.data["amount"]))
    adapter = _okx(request.user, env)
    if not adapter:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    try:
        adapter.subscribe_savings(product.ccy, amount)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"OKX 申购失败: {e}"}, status=502)
    holding = FinanceHolding.objects.create(
        user=request.user, env=env, product=product, principal=amount
    )
    return Response({"id": holding.id}, status=201)


@api_view(["POST"])
def redeem(request, pk):
    env = request.data.get("env", "sim")
    holding = get_object_or_404(FinanceHolding, pk=pk, user=request.user, active=True)
    adapter = _okx(request.user, env)
    if not adapter:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    try:
        adapter.redeem_savings(holding.product.ccy, holding.principal)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"OKX 赎回失败: {e}"}, status=502)
    holding.active = False
    holding.save()
    return Response({"principal": float(holding.principal), "earnings": float(holding.earnings)})


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
