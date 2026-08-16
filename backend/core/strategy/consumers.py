"""StrategyLogConsumer — real-time strategy log WebSocket endpoint.

Connection URL: /ws/strategy/<run_id>/?token=<jwt_access_token>

Authentication:
  - JWT token taken from query string param `token`
  - Validated via SimpleJWT; invalid/missing token → close(4001)
  - Verifies the run belongs to the authenticated user.

Group naming: strategy_run_<run_id>
The strategy runner API POSTs logs which broadcast to this group.
"""
import json
import logging
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("quanly.strategy")


class StrategyLogConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        # --- JWT auth from query string ---
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])
        if not token_list:
            logger.warning("StrategyLogConsumer: no token, closing 4001")
            await self.close(code=4001)
            return

        user = await self._authenticate(token_list[0])
        if user is None:
            logger.warning("StrategyLogConsumer: invalid token, closing 4001")
            await self.close(code=4001)
            return

        # --- Resolve run_id and verify ownership ---
        run_id_str = self.scope["url_route"]["kwargs"].get("run_id", "")
        try:
            run_id = int(run_id_str)
        except (ValueError, TypeError):
            await self.close(code=4001)
            return

        owned = await self._check_run_ownership(user, run_id)
        if not owned:
            logger.warning(
                "StrategyLogConsumer: run %s not owned by user %s, closing 4003",
                run_id,
                user.id,
            )
            await self.close(code=4003)
            return

        self.run_id = run_id
        self.group_name = f"strategy_run_{run_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(
            "StrategyLogConsumer connected: run_id=%s user=%s", run_id, user
        )

    async def disconnect(self, close_code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)
        logger.info(
            "StrategyLogConsumer disconnected: code=%s run_id=%s",
            close_code,
            getattr(self, "run_id", "?"),
        )

    async def receive(self, text_data=None, bytes_data=None):
        # Clients are receive-only; ignore incoming messages.
        pass

    async def strategy_log(self, event):
        """Handler for group_send events of type 'strategy.log'.

        The runner API sends:
            {"type": "strategy.log", "run_id": ..., "level": ..., "message": ..., "ts": ...}
        """
        await self.send(text_data=json.dumps({
            "type": "strategy_log",
            "run_id": event.get("run_id"),
            "level": event.get("level"),
            "message": event.get("message"),
            "ts": event.get("ts"),
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

    @staticmethod
    async def _check_run_ownership(user, run_id: int) -> bool:
        """Return True if the run belongs to the user."""
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _check(u, rid):
            from core.strategy.models import StrategyRun

            return StrategyRun.objects.filter(pk=rid, user=u).exists()

        return await _check(user, run_id)
