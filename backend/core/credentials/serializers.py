from rest_framework import serializers

from core.credentials.crypto import decrypt, encrypt
from core.credentials.models import Credential


class CredentialWriteSerializer(serializers.Serializer):
    """Accepts plaintext fields and encrypts them before storing."""

    env = serializers.ChoiceField(choices=Credential.ENV_CHOICES)
    label = serializers.CharField(max_length=64)
    api_key = serializers.CharField(max_length=512)
    secret = serializers.CharField(max_length=512)
    passphrase = serializers.CharField(max_length=512)

    def validate(self, attrs):
        user = self.context["request"].user
        if Credential.objects.filter(
            user=user, env=attrs["env"], label=attrs["label"]
        ).exists():
            raise serializers.ValidationError(
                {"label": "A credential with this label already exists in this environment."}
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return Credential.objects.create(
            user=user,
            env=validated_data["env"],
            label=validated_data["label"],
            api_key_enc=encrypt(validated_data["api_key"]),
            secret_enc=encrypt(validated_data["secret"]),
            passphrase_enc=encrypt(validated_data["passphrase"]),
        )


class CredentialReadSerializer(serializers.ModelSerializer):
    """Returns safe fields only — never returns secret/passphrase plaintext or ciphertext."""

    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = Credential
        fields = ["id", "env", "label", "api_key_masked", "created_at"]

    def get_api_key_masked(self, obj) -> str:
        """Decrypt api_key and mask all but the last 4 chars (e.g. '****abcd')."""
        try:
            plain = decrypt(obj.api_key_enc)
            suffix = plain[-4:] if len(plain) >= 4 else plain
            return f"****{suffix}"
        except Exception:
            return "****"
