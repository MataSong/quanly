import asyncio
import json
import logging

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from okx.websocket.WsPublicAsync import WsPublicAsync

from apps.market import storage
from apps.market.constants import DEFAULT_BAR, SYMBOLS
from apps.trading.prices import set_last_price

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "采集 OKX 实时 K 线与 Ticker,写 InfluxDB、缓存最新价并转发 Redis"

    def add_arguments(self, parser):
        parser.add_argument("--env", choices=["sim", "live"], default="live")

    def handle(self, *args, **options):
        asyncio.run(self._run_okx(options["env"]))

    def _publish_candle(self, r, symbol, ts, o, h, l, c, vol):
        try:
            storage.write_candle(symbol, DEFAULT_BAR, ts, o, h, l, c, vol)
        except Exception as e:
            logger.warning("influx write failed: %s", e)
        set_last_price(symbol, float(c))
        payload = json.dumps(
            {
                "type": "candle",
                "symbol": symbol,
                "bar": DEFAULT_BAR,
                "ts": ts,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "vol": float(vol),
            }
        )
        r.publish(f"market:{symbol}:{DEFAULT_BAR}", payload)

    async def _run_okx(self, env):
        r = redis.from_url(settings.REDIS_URL)
        url = settings.OKX_PUBLIC_WS_SIM if env == "sim" else settings.OKX_PUBLIC_WS_LIVE
        bar_channel = "candle" + DEFAULT_BAR  # OKX 频道名如 candle1m

        def on_message(raw):
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                return
            arg = msg.get("arg", {})
            data = msg.get("data")
            if not data:
                return
            channel = arg.get("channel", "")
            symbol = arg.get("instId", "")

            if channel.startswith("candle"):
                row = data[0]  # [ts,o,h,l,c,vol,...]
                self._publish_candle(
                    r, symbol, int(row[0]), row[1], row[2], row[3], row[4], row[5]
                )
            elif channel == "tickers":
                d = data[0]
                last = float(d["last"])
                set_last_price(symbol, last)
                r.publish(
                    f"market:{symbol}:ticker",
                    json.dumps({"type": "ticker", "symbol": symbol, "last": last}),
                )

        while True:
            try:
                ws = WsPublicAsync(url=url)
                await ws.start()
                params = []
                for sym in SYMBOLS:
                    params.append({"channel": bar_channel, "instId": sym})
                    params.append({"channel": "tickers", "instId": sym})
                await ws.subscribe(params, callback=on_message)
                self.stdout.write(self.style.SUCCESS(f"OKX collector 已订阅({env}): {SYMBOLS}"))
                while True:
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error("collector 连接异常,5s 后重连: %s", e)
                await asyncio.sleep(5)
