from rest_framework import serializers

from .models import Balance, Order, Position, Trade


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = (
            "id", "env", "inst_type", "symbol", "side", "pos_side", "ord_type",
            "px", "sz", "td_mode", "lever", "tp_px", "sl_px", "state",
            "filled_sz", "avg_px", "created_at",
        )
        read_only_fields = ("state", "filled_sz", "avg_px", "created_at")


class PlaceOrderSerializer(serializers.Serializer):
    env = serializers.ChoiceField(choices=["sim", "live"])
    inst_type = serializers.ChoiceField(
        choices=["SPOT", "MARGIN", "SWAP", "FUTURES", "OPTION", "ETF"]
    )
    symbol = serializers.CharField()
    side = serializers.ChoiceField(choices=["buy", "sell"])
    ord_type = serializers.ChoiceField(choices=["market", "limit"])
    sz = serializers.DecimalField(max_digits=24, decimal_places=8)
    px = serializers.DecimalField(max_digits=24, decimal_places=8, required=False, allow_null=True)
    td_mode = serializers.CharField(required=False, default="cash")
    lever = serializers.IntegerField(required=False, default=1)
    pos_side = serializers.ChoiceField(choices=["long", "short", "net"], required=False, default="net")
    strike = serializers.DecimalField(max_digits=24, decimal_places=8, required=False, allow_null=True)
    expiry = serializers.CharField(required=False, allow_blank=True, default="")
    opt_type = serializers.ChoiceField(choices=["call", "put", ""], required=False, default="")
    tp_px = serializers.DecimalField(max_digits=24, decimal_places=8, required=False, allow_null=True)
    sl_px = serializers.DecimalField(max_digits=24, decimal_places=8, required=False, allow_null=True)

    def validate(self, data):
        if data["ord_type"] == "limit" and data.get("px") in (None, ""):
            raise serializers.ValidationError({"px": "限价单必须提供价格"})
        # 杠杆二次校验(后端防护):对齐 OKX 官方该 instrument 的最大杠杆
        lever = int(data.get("lever") or 1)
        if lever > 1:
            max_lever = self._max_lever(data["symbol"])
            if lever > max_lever:
                raise serializers.ValidationError(
                    {"lever": f"杠杆 {lever}x 超出 {data['symbol']} 官方上限 {max_lever}x"}
                )
        return data

    @staticmethod
    def _max_lever(symbol):
        """从 market 缓存的 OKX instruments 元数据取该 instId 最大杠杆;缺失回落合理默认。"""
        try:
            from apps.market.views import _load_instruments

            it = (_load_instruments().get("flat") or {}).get(symbol)
            if it and it.get("lever"):
                return int(it["lever"])
        except Exception:  # noqa: BLE001
            pass
        return 125  # OKX 合约常见上限;取不到元数据时不误伤合法下单


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ("id", "env", "inst_type", "symbol", "pos_side", "qty", "avg_px", "lever", "margin", "liq_px")


class TradeSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="order.symbol", read_only=True)

    class Meta:
        model = Trade
        fields = ("id", "symbol", "price", "sz", "ts")


class BalanceSerializer(serializers.ModelSerializer):
    available = serializers.DecimalField(max_digits=24, decimal_places=8, read_only=True)

    class Meta:
        model = Balance
        fields = ("id", "env", "ccy", "total", "frozen", "available")
