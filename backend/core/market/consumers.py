"""MarketConsumer — real-time market data WebSocket endpoint.

Connection URL: /ws/market/<symbol>/?token=<jwt_access_token>

Authentication:
  - JWT token taken from query string param `token`
  - Validated via SimpleJWT; invalid/missing token → close(4001)

Group naming: market_<symbol>  (e.g. market_BTC-USDT)
The run_market_collector management command broadcasts to these groups.
"""
import json
import logging
import re
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("quanly.market")


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

        # --- Resolve symbol and join group ---
        raw_symbol = self.scope["url_route"]["kwargs"].get("symbol", "BTC-USDT")
        self.symbol = _sanitize_symbol(raw_symbol)
        self.group_name = f"market_{self.symbol}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("MarketConsumer connected: symbol=%s user=%s", self.symbol, user)

    async def disconnect(self, close_code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)
        logger.info("MarketConsumer disconnected: code=%s symbol=%s", close_code, getattr(self, "symbol", "?"))

    async def receive(self, text_data=None, bytes_data=None):
        # Clients are receive-only; ignore any incoming messages
        pass

    async def market_update(self, event):
        """Handler for group_send events of type 'market.update'.

        The collector sends:
            {"type": "market.update", "symbol": "...", "candle": {...}}
        """
        await self.send(text_data=json.dumps({
            "type": "market_update",
            "symbol": event.get("symbol"),
            "candle": event.get("candle"),
        }))

    # ------------------------------------------------------------------ helpers

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
