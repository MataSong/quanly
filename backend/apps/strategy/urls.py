from django.urls import path
from rest_framework.routers import DefaultRouter

from . import runner_api, views

router = DefaultRouter()
router.register("strategies", views.StrategyViewSet, basename="strategy")

urlpatterns = [
    path("strategies/<int:pk>/run", views.run_strategy),
    path("strategy-runs", views.list_runs),
    path("strategy-runs/<int:pk>/stop", views.stop_strategy),
    path("strategy-runs/<int:pk>/logs", views.run_logs),
    # 策略容器专用 API(RUN_TOKEN 鉴权)
    path("strategy-api/market", runner_api.market),
    path("strategy-api/candles", runner_api.candles),
    path("strategy-api/positions", runner_api.positions),
    path("strategy-api/balances", runner_api.balances),
    path("strategy-api/order", runner_api.order),
    path("strategy-api/log", runner_api.log),
] + router.urls
