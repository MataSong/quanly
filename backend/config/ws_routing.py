from django.urls import re_path
from core.market.consumers import MarketConsumer
from core.strategy.consumers import StrategyLogConsumer

websocket_urlpatterns = [
    re_path(r"^ws/market/(?P<symbol>[\w\-]+)/$", MarketConsumer.as_asgi()),
    re_path(r"^ws/strategy/(?P<run_id>\d+)/$", StrategyLogConsumer.as_asgi()),
]
