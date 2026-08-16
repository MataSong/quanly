"""Management command to seed the built-in dual_ma Strategy.

Usage:
    python manage.py seed_builtin_strategies

Idempotent: safe to run multiple times — will not create duplicates.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed built-in strategies (dual_ma)."

    def handle(self, *args, **options):
        from core.strategy.models import Strategy

        defaults = {
            "name": "Dual Moving Average",
            "source_type": Strategy.SOURCE_BUILTIN,
            "is_builtin": True,
            "default_params": {
                "fast_period": 5,
                "slow_period": 20,
                "sz": "0.001",
            },
        }

        obj, created = Strategy.objects.get_or_create(
            code_ref="dual_ma",
            defaults=defaults,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created built-in strategy: {obj.name} (id={obj.pk})")
            )
        else:
            self.stdout.write(f"Built-in strategy already exists: {obj.name} (id={obj.pk})")
