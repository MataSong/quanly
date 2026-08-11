"""资金一致性对账:本地 Balance 与 OKX REST 实拉余额比对,列出差异。"""
from decimal import Decimal

from apps.credentials.models import Env, ExchangeCredential
from apps.exchanges.factory import AdapterFactory

from .models import Balance

D = Decimal


def reconcile(user, env: str) -> dict:
    cred = ExchangeCredential.objects.filter(
        user=user, env=env, exchange="okx"
    ).first()
    if not cred:
        return {"env": env, "consistent": True, "items": [], "detail": "未配置 OKX 凭证"}

    x_env = Env.SIM if env == "sim" else Env.LIVE
    adapter = AdapterFactory.create("okx", x_env, cred)
    try:
        remote = {b.ccy: D(str(b.total)) for b in adapter.get_balances()}
    except Exception as e:  # noqa: BLE001
        return {"env": env, "consistent": False, "items": [], "detail": f"拉取 OKX 余额失败: {e}"}

    items = []
    ccys = set(remote) | {
        b.ccy for b in Balance.objects.filter(user=user, env=env)
    }
    for ccy in sorted(ccys):
        local = next(
            (b.total for b in Balance.objects.filter(user=user, env=env, ccy=ccy)),
            D("0"),
        )
        r = remote.get(ccy, D("0"))
        delta = local - r
        consistent = abs(delta) < D("0.00000001")
        items.append({
            "ccy": ccy,
            "local": float(local),
            "remote": float(r),
            "delta": float(delta),
            "consistent": consistent,
        })
    all_ok = all(i["consistent"] for i in items)
    return {"env": env, "consistent": all_ok, "items": items}
