"""最新价读取：仅走 Redis 缓存（由 collector 写入），无假数据兜底。"""
import json

import redis
from django.conf import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL)
    return _client


def _key(symbol: str) -> str:
    return f"last_price:{symbol}"


def set_last_price(symbol: str, price: float) -> None:
    _get_client().set(_key(symbol), json.dumps(price), ex=300)


def _redis_get(symbol: str):
    raw = _get_client().get(_key(symbol))
    if raw is None:
        return None
    return json.loads(raw)


def get_last_price(symbol: str):
    """返回最新价 float，读不到返回 None（调用方需自行处理）。"""
    return _redis_get(symbol)
