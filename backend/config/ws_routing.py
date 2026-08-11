from django.urls import re_path

from apps.market.consumers import MarketConsumer
from apps.strategy.consumers import StrategyLogConsumer
from apps.trading.consumers import TradeConsumer

websocket_urlpatterns = [
    re_path(r"^ws/market/(?P<symbol>[\w-]+)$", MarketConsumer.as_asgi()),
    re_path(
        r"^ws/trade/(?P<user_id>\d+)/(?P<env>\w+)$",
        TradeConsumer.as_asgi(),
    ),
    re_path(r"^ws/strategy/(?P<run_id>\d+)$", StrategyLogConsumer.as_asgi()),
]
