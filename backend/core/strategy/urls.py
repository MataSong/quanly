from django.urls import path

from core.strategy.views import (
    AdminPendingView,
    AdminReviewView,
    MarketplaceListView,
    MyStrategiesListView,
    RunnerCandlesView,
    RunnerLogView,
    RunnerOrderView,
    StrategyCreateView,
    StrategyDetailView,
    StrategyListView,
    StrategyRunDetailView,
    StrategyRunListCreateView,
    StrategyRunLogsView,
    StrategyRunStartView,
    StrategyRunStopView,
    StrategySubmitView,
)

urlpatterns = [
    # Management API (JWT)
    path("strategies", StrategyListView.as_view(), name="strategy-list"),
    path("marketplace", MarketplaceListView.as_view(), name="strategy-marketplace"),
    path("mine", MyStrategiesListView.as_view(), name="strategy-mine"),

    # Strategy CRUD — POST uses StrategyCreateView; GET/PUT/DELETE on detail use StrategyDetailView
    path("strategies/create", StrategyCreateView.as_view(), name="strategy-create"),
    path("strategies/<int:pk>", StrategyDetailView.as_view(), name="strategy-detail"),
    path("strategies/<int:pk>/submit", StrategySubmitView.as_view(), name="strategy-submit"),

    # Admin review
    path("admin/pending", AdminPendingView.as_view(), name="strategy-admin-pending"),
    path("admin/strategies/<int:pk>/review", AdminReviewView.as_view(), name="strategy-admin-review"),

    # Runs
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
