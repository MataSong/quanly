import json
from dataclasses import asdict

import redis
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.exchanges.factory import AdapterFactory
from apps.exchanges.types import Env

from .constants import DEFAULT_BAR, SYMBOLS

# OKX 五大可交易品类;MARGIN(现货杠杆)复用 SPOT 交易对,无独立 instruments 接口
INST_TYPES = ["SPOT", "SWAP", "FUTURES", "OPTION"]
_INSTRUMENTS_CACHE_KEY = "market:instruments:v2"
_INSTRUMENTS_TTL = 600  # 10 分钟


def _redis():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _load_instruments():
    """拉取全品类 instruments 元数据,带 Redis 缓存;失败回落最小列表。"""
    r = _redis()
    cached = r.get(_INSTRUMENTS_CACHE_KEY)
    if cached:
        return json.loads(cached)

    adapter = AdapterFactory.create("okx", Env.LIVE, credential=None)
    by_type = {}
    flat = {}
    for t in INST_TYPES:
        try:
            items = adapter.get_instruments(t)
        except Exception:  # noqa: BLE001 —— 单品类失败不影响其余
            items = []
        by_type[t] = items
        for it in items:
            flat[it["instId"]] = it

    data = {"by_type": by_type, "flat": flat}
    if flat:
        r.setex(_INSTRUMENTS_CACHE_KEY, _INSTRUMENTS_TTL, json.dumps(data))
    return data


@api_view(["GET"])
@permission_classes([AllowAny])
def symbols(request):
    """返回全品类可交易 instrument,按品类分组;带最大杠杆等元数据。

    响应形如:{"by_type": {"SPOT": [{instId, lever, ...}], "SWAP": [...]},
              "symbols": ["BTC-USDT", ...]}  # symbols 为扁平 instId,兼容旧前端
    """
    try:
        data = _load_instruments()
        flat = data.get("flat") or {}
        if flat:
            return Response(
                {
                    "by_type": data["by_type"],
                    "symbols": sorted(flat.keys()),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    return Response({"by_type": {"SPOT": [{"instId": s, "lever": 1} for s in SYMBOLS]},
                     "symbols": SYMBOLS})


@api_view(["GET"])
@permission_classes([AllowAny])
def instrument(request, symbol):
    """返回单个 instrument 的完整元数据(含最大杠杆),供下单/杠杆校验。"""
    try:
        data = _load_instruments()
        it = (data.get("flat") or {}).get(symbol)
        if it:
            return Response(it)
    except Exception:  # noqa: BLE001
        pass
    return Response({"instId": symbol, "lever": 1, "instType": "SPOT"})


@api_view(["GET"])
@permission_classes([AllowAny])
def candles(request, symbol):
    bar = request.query_params.get("bar", DEFAULT_BAR)
    limit = int(request.query_params.get("limit", 200))
    # 公共行情免鉴权,统一用 LIVE:OKX 模拟盘对多数合约(尤其 FUTURES)无 K线历史。
    adapter = AdapterFactory.create("okx", Env.LIVE, credential=None)
    data = [asdict(c) for c in adapter.get_candles(symbol, bar, limit)]
    return Response({"symbol": symbol, "bar": bar, "candles": data})
