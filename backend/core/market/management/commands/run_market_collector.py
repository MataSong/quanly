"""run_market_collector — subscribe to OKX public WS candle channel and
broadcast updates via Django Channels channel layer.

Usage:
    python manage.py run_market_collector [--symbols BTC-USDT,ETH-USDT] [--bar 1m]

Connects to OKX public WebSocket (no API key required).
Broadcasts received candle updates to group market_<symbol> so that
MarketConsumer instances can forward them to connected browsers.

Zero mock: only real OKX data.  On OKX connection error the command
logs and retries with exponential back-off.
"""
import asyncio
import json
import logging
import os
import time

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

logger = logging.getLogger("quanly.market")

DEFAULT_SYMBOLS = ["BTC-USDT", "ETH-USDT"]
DEFAULT_BAR = "1m"

_OKX_FLAG = int(os.environ.get("OKX_FLAG", "0"))
# OKX public WS endpoints
_WS_PUBLIC_PROD = "wss://ws.okx.com:8443/ws/v5/public"
_WS_PUBLIC_DEMO = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"


def _ws_url() -> str:
    return _WS_PUBLIC_DEMO if _OKX_FLAG == 1 else _WS_PUBLIC_PROD


async def _run(symbols: list[str], bar: str) -> None:
    """Main async loop: connect OKX WS, subscribe, broadcast."""
    import websockets  # type: ignore[import]
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    url = _ws_url()

    # Build subscription args
    args = [{"channel": f"candle{bar}", "instId": sym} for sym in symbols]
    subscribe_msg = json.dumps({"op": "subscribe", "args": args})

    retry_delay = 5
    while True:
        try:
            logger.info("Connecting to OKX WS: %s (symbols=%s bar=%s)", url, symbols, bar)
            async with websockets.connect(url, ping_interval=20, ping_timeout=30) as ws:
                await ws.send(subscribe_msg)
                logger.info("Subscribed to channels: %s", [a["channel"] for a in args])
                retry_delay = 5  # reset on successful connect

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # OKX sends {"event":"subscribe",...} on ack — skip
                    if "event" in msg:
                        logger.debug("OKX event: %s", msg)
                        continue

                    # Candle push: {"arg":{"channel":"candle1m","instId":"BTC-USDT"},"data":[[ts,o,h,l,c,vol,...]]}
                    arg = msg.get("arg", {})
                    data_rows = msg.get("data", [])
                    if not data_rows:
                        continue

                    inst_id = arg.get("instId", "")
                    group_name = f"market_{inst_id}"

                    for row in data_rows:
                        if len(row) < 6:
                            continue
                        candle = {
                            "ts": int(row[0]),
                            "o": row[1],
                            "h": row[2],
                            "l": row[3],
                            "c": row[4],
                            "vol": row[5],
                        }
                        try:
                            await channel_layer.group_send(
                                group_name,
                                {
                                    "type": "market.update",
                                    "symbol": inst_id,
                                    "candle": candle,
                                },
                            )
                        except Exception as exc:
                            logger.warning("channel_layer.group_send error: %s", exc)

        except Exception as exc:
            logger.error("OKX WS error: %s — retrying in %ss", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)


class Command(BaseCommand):
    help = "Connect to OKX public WebSocket and broadcast candle updates via channel layer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols",
            default=",".join(DEFAULT_SYMBOLS),
            help="Comma-separated list of instIds, e.g. BTC-USDT,ETH-USDT",
        )
        parser.add_argument(
            "--bar",
            default=DEFAULT_BAR,
            help="Candle bar size, e.g. 1m, 5m, 1H",
        )

    def handle(self, *args, **options):
        symbols = [s.strip() for s in options["symbols"].split(",") if s.strip()]
        bar = options["bar"]
        self.stdout.write(f"Starting market collector: symbols={symbols} bar={bar}")
        try:
            asyncio.run(_run(symbols, bar))
        except KeyboardInterrupt:
            self.stdout.write("Market collector stopped.")
