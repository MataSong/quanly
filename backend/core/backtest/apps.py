"""AppConfig for core.backtest."""
from django.apps import AppConfig


class BacktestConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core.backtest"
    label = "core_backtest"
    verbose_name = "Backtest"
