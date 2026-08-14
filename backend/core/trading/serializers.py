from rest_framework import serializers

from .models import Order


class PlaceOrderSerializer(serializers.Serializer):
    """Validates the body of POST /api/trading/order."""
    credential_id = serializers.IntegerField()
    inst_type = serializers.ChoiceField(choices=["SPOT", "SWAP"])
    inst_id = serializers.CharField(max_length=32)
    side = serializers.ChoiceField(choices=["buy", "sell"])
    ord_type = serializers.ChoiceField(choices=["market", "limit"])
    sz = serializers.CharField(max_length=32)
    px = serializers.CharField(max_length=32, required=False, allow_blank=True, default=None)
    pos_side = serializers.ChoiceField(
        choices=["long", "short", "net"], required=False, allow_null=True, default=None
    )
    td_mode = serializers.CharField(max_length=16, required=False, allow_blank=True, default=None)
    reduce_only = serializers.BooleanField(required=False, default=False)


class CancelOrderSerializer(serializers.Serializer):
    """Validates the body of POST /api/trading/cancel."""
    credential_id = serializers.IntegerField()
    inst_id = serializers.CharField(max_length=32)
    ord_id = serializers.CharField(max_length=64)


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model (read-only response)."""

    class Meta:
        model = Order
        fields = [
            "id",
            "env",
            "inst_type",
            "inst_id",
            "side",
            "ord_type",
            "pos_side",
            "sz",
            "px",
            "td_mode",
            "reduce_only",
            "okx_ord_id",
            "cl_ord_id",
            "state",
            "created_at",
        ]
        read_only_fields = fields
