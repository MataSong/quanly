"""MarketConsumer — real-time market data WebSocket endpoint.

Connection URL: /ws/market/<symbol>/?token=<jwt_access_token>&bar=<bar>

Authentication:
  - JWT token taken from query string param `token`
  - Validated via SimpleJWT; invalid/missing token → close(4001)

Group naming: market_<symbol>  (e.g. market_BTC-USDT)
The run_market_collector management command broadcasts to these groups.

Redis DB2 active subscription registry:
  - key  market:refcount:<symbol>:<bar>  (integer, INCR on connect, DECR on disconnect)
  - key  market:active                   (SADD/SREM member "<symbol>:<bar>")
  Redis errors are non-fatal: connection still proceeds, just without registering.
"""
import json
import logging
import os
import re
from urllib.parse import parse_qs

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("quanly.market")

_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
_REDIS_URL = f"redis://{_REDIS_HOST}:{_REDIS_PORT}/2"


def _sanitize_symbol(symbol: str) -> str:
    """Keep only safe chars for channel-layer group names."""
    return re.sub(r"[^A-Za-z0-9_\-]", "", symbol)[:50]


class MarketConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        # --- JWT auth from query string ---
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])
        if not token_list:
            logger.warning("MarketConsumer: no token in query string, closing 4001")
            await self.close(code=4001)
            return

        token = token_list[0]
        user = await self._authenticate(token)
        if user is None:
            logger.warning("MarketConsumer: invalid token, closing 4001")
            await self.close(code=4001)
            return

        # --- Resolve symbol and bar ---
        raw_symbol = self.scope["url_route"]["kwargs"].get("symbol", "BTC-USDT")
        self.symbol = _sanitize_symbol(raw_symbol)
        self.bar = params.get("bar", ["1m"])[0]
        self.group_name = f"market_{self.symbol}"
        self._active_member = f"{self.symbol}:{self.bar}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(
            "MarketConsumer connected: symbol=%s bar=%s user=%s",
            self.symbol, self.bar, user,
        )

        # --- Register active subscription in Redis DB2 ---
        await self._redis_register()

    async def disconnect(self, close_code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

        await self._redis_deregister()
        logger.info(
            "MarketConsumer disconnected: code=%s symbol=%s bar=%s",
            close_code,
            getattr(self, "symbol", "?"),
            getattr(self, "bar", "?"),
        )

    async def receive(self, text_data=None, bytes_data=None):
        # Clients are receive-only; ignore any incoming messages
        pass

    async def market_update(self, event):
        """Handler for group_send events of type 'market.update'.

        Supports both candle and ticker payloads:
            {"type": "market.update", "symbol": "...", "candle": {...}}
            {"type": "market.update", "symbol": "...", "ticker": {"last": "..."}}
        """
        payload = {"type": "market_update", "symbol": event.get("symbol")}
        if event.get("candle") is not None:
            payload["candle"] = event["candle"]
        if event.get("ticker") is not None:
            payload["ticker"] = event["ticker"]
        await self.send(text_data=json.dumps(payload))

    # ------------------------------------------------------------------ helpers

    async def _redis_register(self):
        """Increment refcount and add to active set. Non-fatal on Redis error."""
        member = getattr(self, "_active_member", None)
        if not member:
            return
        try:
            async with aioredis.from_url(_REDIS_URL) as r:
                await r.incr(f"market:refcount:{member}")
                await r.sadd("market:active", member)
        except Exception as exc:
            logger.warning("MarketConsumer: Redis register failed (degraded): %s", exc)

    async def _redis_deregister(self):
        """Decrement refcount; if <=0 remove from active set. Non-fatal on Redis error."""
        member = getattr(self, "_active_member", None)
        if not member:
            return
        try:
            async with aioredis.from_url(_REDIS_URL) as r:
                count = await r.decr(f"market:refcount:{member}")
                if count <= 0:
                    await r.srem("market:active", member)
                    await r.delete(f"market:refcount:{member}")
        except Exception as exc:
            logger.warning("MarketConsumer: Redis deregister failed (degraded): %s", exc)

    @staticmethod
    async def _authenticate(token: str):
        """Validate JWT token and return User or None."""
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _validate(tok: str):
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from django.contrib.auth.models import User
                access = AccessToken(tok)
                user_id = access["user_id"]
                return User.objects.get(id=user_id, is_active=True)
            except Exception:
                return None

        return await _validate(token)
