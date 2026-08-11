import re

from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def validate_password(self, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise serializers.ValidationError(
                "密码需至少 8 位,且同时包含字母和数字。"
            )
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "locale", "theme")
