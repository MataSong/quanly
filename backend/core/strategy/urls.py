from django.urls import path

from core.strategy.views import (
    RunnerCandlesView,
    RunnerLogView,
    RunnerOrderView,
    StrategyListView,
    StrategyRunDetailView,
    StrategyRunListCreateView,
    StrategyRunLogsView,
    StrategyRunStartView,
    StrategyRunStopView,
)

urlpatterns = [
    # Management API (JWT)
    path("strategies", StrategyListView.as_view(), name="strategy-list"),
    path("runs", StrategyRunListCreateView.as_view(), name="strategy-run-list-create"),
    path("runs/<int:pk>", StrategyRunDetailView.as_view(), name="strategy-run-detail"),
    path("runs/<int:pk>/start", StrategyRunStartView.as_view(), name="strategy-run-start"),
    path("runs/<int:pk>/stop", StrategyRunStopView.as_view(), name="strategy-run-stop"),
    path("runs/<int:pk>/logs", StrategyRunLogsView.as_view(), name="strategy-run-logs"),
    # Runner API (X-Run-Token)
    path("runner/candles", RunnerCandlesView.as_view(), name="runner-candles"),
    path("runner/order", RunnerOrderView.as_view(), name="runner-order"),
    path("runner/log", RunnerLogView.as_view(), name="runner-log"),
]
