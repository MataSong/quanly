"""Management command to seed the built-in strategies.

Usage:
    python manage.py seed_builtin_strategies

Idempotent: safe to run multiple times — will not create duplicates.
Seeds: dual_ma, rsi, macd.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed built-in strategies (dual_ma, rsi, macd)."

    def handle(self, *args, **options):
        from core.strategy.models import Strategy

        # 内置策略元数据:owner=None,直接上架(approved+public),is_builtin=True。
        builtins = [
            {
                "code_ref": "dual_ma",
                "name": "Dual Moving Average",
                "default_params": {"fast_period": 5, "slow_period": 20, "sz": "0.001"},
                "description": "经典双均线金叉/死叉策略:快线上穿慢线买入,下穿卖出。",
            },
            {
                "code_ref": "rsi",
                "name": "RSI (Relative Strength Index)",
                "default_params": {"period": 14, "oversold": 30, "overbought": 70, "sz": "0.001"},
                "description": "RSI 超买超卖策略:RSI 低于超卖阈值买入,高于超买阈值卖出。",
            },
            {
                "code_ref": "macd",
                "name": "MACD",
                "default_params": {"fast": 12, "slow": 26, "signal_period": 9, "sz": "0.001"},
                "description": "MACD 金叉/死叉策略:MACD 线上穿信号线买入,下穿卖出。",
            },
        ]

        for spec in builtins:
            defaults = {
                "name": spec["name"],
                "source_type": Strategy.SOURCE_BUILTIN,
                "is_builtin": True,
                "default_params": spec["default_params"],
                "owner": None,
                "status": Strategy.STATUS_APPROVED,
                "visibility": Strategy.VISIBILITY_PUBLIC,
                "description": spec["description"],
            }

            obj, created = Strategy.objects.update_or_create(
                code_ref=spec["code_ref"],
                source_type=Strategy.SOURCE_BUILTIN,
                defaults=defaults,
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created built-in strategy: {obj.name} (id={obj.pk})")
                )
            else:
                self.stdout.write(f"Updated built-in strategy: {obj.name} (id={obj.pk})")
