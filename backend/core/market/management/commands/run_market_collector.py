"""run_market_collector — dynamically subscribe to OKX public WS candle+tickers
channels based on the active viewer set registered in Redis DB2 by MarketConsumer,
and broadcast updates via Django Channels channel layer.

Usage:
    python manage.py run_market_collector [--symbols BTC-USDT,ETH-USDT] [--bar 1m]

    --symbols / --bar are treated as *extra always-on subscriptions* (i.e. they are
    merged into the target subscription set on every sync tick).  They do NOT disable
    the dynamic behaviour driven by Redis; they just ensure those pairs are always
    subscribed even when no browser is connected.  Passing neither flag means the
    only always-on fallback is BTC-USDT/candle1m + tickers/BTC-USDT (see FALLBACK
    constant), which prevents the collector from spinning completely idle.

Zero mock: only real OKX data.  On OKX or Redis connection error the command
logs and retries with exponential back-off.

Redis DB layout:
    DB0 — Channels channel-layer
    DB1 — Celery broker/backend
    DB2 — market active-subscription registry (this module + consumers.py)
"""
import asyncio
import json
import logging
import os
import time

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand
from core.market.consumers import _sanitize_symbol

logger = logging.getLogger("quanly.market")

DEFAULT_SYMBOLS = ["BTC-USDT", "ETH-USDT"]
DEFAULT_BAR = "1m"

# Fallback member subscribed when market:active is empty, so the collector
# never spins completely idle and OKX WS stays exercised.
_FALLBACK_MEMBERS: frozenset[str] = frozenset({"BTC-USDT:1m"})

_OKX_FLAG = int(os.environ.get("OKX_FLAG", "0"))
_WS_PUBLIC_PROD = "wss://ws.okx.com:8443/ws/v5/public"
_WS_PUBLIC_DEMO = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"

_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
_REDIS_URL = f"redis://{_REDIS_HOST}:{_REDIS_PORT}/2"

_SYNC_INTERVAL = 3  # seconds between active-set polls


def _ws_url() -> str:
    return _WS_PUBLIC_DEMO if _OKX_FLAG == 1 else _WS_PUBLIC_PROD


# ---------------------------------------------------------------------------
# Pure functions — extracted for easy unit testing
# ---------------------------------------------------------------------------

def _compute_target_subs(
    active_members: set[str],
    extra_members: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Compute the target set of (channel, instId) subscriptions.

    Each member in *active_members* is a "<symbol>:<bar>" string registered
    by MarketConsumer in Redis DB2.

    For every member we want:
      - candle<bar> for that symbol
      - tickers    for that symbol (deduplicated: one per symbol regardless of
                   how many bars are active for it)

    If *active_members* is empty, _FALLBACK_MEMBERS is used instead so the
    collector is never completely idle.

    *extra_members* (from --symbols/--bar CLI flags) are merged in unconditionally.

    Returns a set of (channel_name, instId) tuples, e.g.:
        {("candle1m", "BTC-USDT"), ("tickers", "BTC-USDT"), ("candle5m", "ETH-USDT"), ...}
    """
    members = set(active_members)
    if extra_members:
        members |= extra_members
    if not members:
        members = set(_FALLBACK_MEMBERS)

    target: set[tuple[str, str]] = set()
    ticker_symbols: set[str] = set()
    for member in members:
        parts = member.split(":", 1)
        if len(parts) != 2:
            logger.warning("Skipping malformed active member: %r", member)
            continue
        symbol, bar = parts[0], parts[1]
        target.add((f"candle{bar}", symbol))
        ticker_symbols.add(symbol)

    for sym in ticker_symbols:
        target.add(("tickers", sym))

    return target


def _parse_candle_row(row: list) -> dict | None:
    """Parse a single OKX candle data row into a candle dict.

    Row format: [ts, open, high, low, close, vol, ...]
    Returns None if the row is too short.
    """
    if len(row) < 6:
        return None
    return {
        "ts": int(row[0]),
        "o": row[1],
        "h": row[2],
        "l": row[3],
        "c": row[4],
        "vol": row[5],
    }


def _parse_ticker_data(data: list) -> dict | None:
    """Parse OKX tickers push data into a ticker dict with just {last}.

    data is msg["data"], a list of ticker objects.  We use data[0].
    Returns None if data is empty or 'last' is missing.
    """
    if not data:
        return None
    first = data[0]
    last = first.get("last")
    if last is None:
        return None
    return {"last": last}


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def _run(extra_members: set[str]) -> None:
    """Main async loop: connect OKX WS, dynamically subscribe, broadcast."""
    import redis.asyncio as aioredis
    import websockets  # type: ignore[import]
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    url = _ws_url()

    retry_delay = 5
    while True:
        try:
            logger.info("Connecting to OKX WS: %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=30) as ws:
                retry_delay = 5  # reset on successful connect

                # Shared mutable state between the two coroutines
                subscribed: set[tuple[str, str]] = set()
                subscribed_lock = asyncio.Lock()

                # ── sub-coroutine 1: read loop ─────────────────────────────

                async def _read_loop():
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if "event" in msg:
                            logger.debug("OKX event: %s", msg)
                            continue

                        arg = msg.get("arg", {})
                        channel = arg.get("channel", "")
                        inst_id = arg.get("instId", "")
                        data_rows = msg.get("data", [])
                        group_name = f"market_{_sanitize_symbol(inst_id)}"

                        if channel.startswith("candle") and data_rows:
                            for row in data_rows:
                                candle = _parse_candle_row(row)
                                if candle is None:
                                    continue
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
                                    logger.warning(
                                        "channel_layer.group_send (candle) error: %s", exc
                                    )

                        elif channel == "tickers":
                            ticker = _parse_ticker_data(data_rows)
                            if ticker is not None:
                                try:
                                    await channel_layer.group_send(
                                        group_name,
                                        {
                                            "type": "market.update",
                                            "symbol": inst_id,
                                            "ticker": ticker,
                                        },
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        "channel_layer.group_send (ticker) error: %s", exc
                                    )

                # ── sub-coroutine 2: subscription sync loop ────────────────

                async def _sync_loop():
                    nonlocal subscribed
                    redis_client = None
                    try:
                        redis_client = aioredis.from_url(_REDIS_URL)
                    except Exception as exc:
                        logger.warning(
                            "Could not create Redis client for sync loop: %s", exc
                        )

                    while True:
                        await asyncio.sleep(_SYNC_INTERVAL)
                        try:
                            # Read active members from Redis DB2
                            active: set[str] = set()
                            if redis_client is not None:
                                try:
                                    raw_members = await redis_client.smembers(
                                        "market:active"
                                    )
                                    active = {
                                        m.decode() if isinstance(m, bytes) else m
                                        for m in raw_members
                                    }
                                except Exception as exc:
                                    logger.warning(
                                        "Redis smembers error (using fallback): %s", exc
                                    )

                            target = _compute_target_subs(active, extra_members)

                            async with subscribed_lock:
                                to_add = target - subscribed
                                to_remove = subscribed - target

                            if to_add:
                                sub_args = [
                                    {"channel": ch, "instId": inst}
                                    for ch, inst in to_add
                                ]
                                try:
                                    await ws.send(
                                        json.dumps(
                                            {"op": "subscribe", "args": sub_args}
                                        )
                                    )
                                    logger.info(
                                        "OKX subscribe: %s",
                                        [(a["channel"], a["instId"]) for a in sub_args],
                                    )
                                    async with subscribed_lock:
                                        subscribed |= to_add
                                except Exception as exc:
                                    logger.warning("OKX subscribe send error: %s", exc)

                            if to_remove:
                                unsub_args = [
                                    {"channel": ch, "instId": inst}
                                    for ch, inst in to_remove
                                ]
                                try:
                                    await ws.send(
                                        json.dumps(
                                            {"op": "unsubscribe", "args": unsub_args}
                                        )
                                    )
                                    logger.info(
                                        "OKX unsubscribe: %s",
                                        [
                                            (a["channel"], a["instId"])
                                            for a in unsub_args
                                        ],
                                    )
                                    async with subscribed_lock:
                                        subscribed -= to_remove
                                except Exception as exc:
                                    logger.warning("OKX unsubscribe send error: %s", exc)

                        except Exception as exc:
                            logger.warning("Sync loop iteration error: %s", exc)

                # ── bootstrap: subscribe to initial target immediately ──────

                initial_target = _compute_target_subs(set(), extra_members)
                if initial_target:
                    init_args = [
                        {"channel": ch, "instId": inst}
                        for ch, inst in initial_target
                    ]
                    await ws.send(
                        json.dumps({"op": "subscribe", "args": init_args})
                    )
                    logger.info(
                        "OKX initial subscribe: %s",
                        [(a["channel"], a["instId"]) for a in init_args],
                    )
                    subscribed |= initial_target

                # ── run both coroutines concurrently ──────────────────────
                await asyncio.gather(_read_loop(), _sync_loop())

        except Exception as exc:
            logger.error("OKX WS error: %s — retrying in %ss", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)


class Command(BaseCommand):
    help = (
        "Connect to OKX public WebSocket and broadcast candle/ticker updates "
        "via channel layer.  Dynamically subscribes based on Redis DB2 active viewer set."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols",
            default=",".join(DEFAULT_SYMBOLS),
            help="Comma-separated extra always-on instIds, e.g. BTC-USDT,ETH-USDT",
        )
        parser.add_argument(
            "--bar",
            default=DEFAULT_BAR,
            help="Bar size for extra always-on symbols, e.g. 1m, 5m, 1H",
        )

    def handle(self, *args, **options):
        symbols = [s.strip() for s in options["symbols"].split(",") if s.strip()]
        bar = options["bar"]
        # Build extra always-on members from CLI flags
        extra_members: set[str] = {f"{sym}:{bar}" for sym in symbols}
        self.stdout.write(
            f"Starting market collector: extra_always_on={sorted(extra_members)}"
        )
        try:
            asyncio.run(_run(extra_members))
        except KeyboardInterrupt:
            self.stdout.write("Market collector stopped.")
