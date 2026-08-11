from django.apps import AppConfig


class ExchangesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exchanges"

    def ready(self):
        from .factory import register_adapter
        from .okx.adapter import OKXAdapter

        register_adapter("okx", OKXAdapter)
