"""Celery 任务:定时用 OKX REST 全量校正本地余额/持仓(兜底 WS 可能遗漏的增量)。"""
from celery import shared_task


@shared_task
def periodic_okx_sync():
    from apps.credentials.models import Env, ExchangeCredential
    from apps.exchanges.factory import AdapterFactory
    from apps.trading import sync

    for cred in ExchangeCredential.objects.filter(exchange="okx"):
        x_env = Env.SIM if cred.env == "sim" else Env.LIVE
        try:
            adapter = AdapterFactory.create("okx", x_env, cred)
            sync.full_sync(cred.user, cred.env, adapter)
        except Exception:  # noqa: BLE001
            continue
