"""交易事件推送:成交/撤单/持仓变更时通知前端刷新。

发布到 Redis 频道 trade:{user_id}:{env};Channels 的 TradeConsumer 订阅后推给前端。
"""
import json

import redis
from django.conf import settings

_r = None


def _client():
    global _r
    if _r is None:
        _r = redis.from_url(settings.REDIS_URL)
    return _r


def notify_trade(user_id: int, env: str):
    try:
        _client().publish(
            f"trade:{user_id}:{env}",
            json.dumps({"type": "refresh", "env": env}),
        )
    except Exception:
        # 推送失败不应影响下单主流程(前端仍可手动刷新)
        pass
