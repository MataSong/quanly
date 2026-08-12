from rest_framework import serializers

from .models import Strategy, StrategyRun


class StrategySerializer(serializers.ModelSerializer):
    source = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Strategy
        fields = ("id", "name", "language", "source", "kind", "mode",
                  "visual_config", "description", "created_at")
        read_only_fields = ("kind", "created_at")


class StrategyRunSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)

    class Meta:
        model = StrategyRun
        fields = (
            "id", "strategy", "strategy_name", "env", "credential", "symbol",
            "interval_sec", "status", "started_at", "stopped_at",
            "batch_id", "last_heartbeat",
        )
        read_only_fields = ("status", "started_at", "stopped_at", "last_heartbeat")
