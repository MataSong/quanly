from rest_framework import serializers

from .connectivity import check_okx
from .crypto import encrypt
from .models import ExchangeCredential


class CredentialWriteSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True)
    passphrase = serializers.CharField(write_only=True)

    class Meta:
        model = ExchangeCredential
        fields = ("id", "exchange", "env", "label", "api_key", "secret", "passphrase")

    def validate(self, attrs):
        # 保存前连通性校验:凭证无效则拒绝,附带 OKX 返回原因
        ok, msg = check_okx(
            attrs.get("env"),
            attrs.get("api_key"),
            attrs.get("secret"),
            attrs.get("passphrase"),
        )
        if not ok:
            raise serializers.ValidationError(
                {"detail": f"API 密钥连通性校验失败:{msg}"}
            )
        return attrs

    def create(self, validated_data):
        validated_data["secret_enc"] = encrypt(validated_data.pop("secret"))
        validated_data["passphrase_enc"] = encrypt(validated_data.pop("passphrase"))
        validated_data["user"] = self.context["request"].user
        return ExchangeCredential.objects.create(**validated_data)


class CredentialReadSerializer(serializers.ModelSerializer):
    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeCredential
        fields = ("id", "exchange", "env", "label", "api_key_masked", "created_at")

    def get_api_key_masked(self, obj):
        return "****" + obj.api_key[-4:]
