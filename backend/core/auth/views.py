import logging

from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.accounts.models import Role, UserProfile, UserRole
from .password_rules import validate_password_strength
from .serializers import UserSerializer

log = logging.getLogger("quanly.core.auth")

User = get_user_model()


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            inactive = User.objects.filter(username=username, is_active=False).first()
            if inactive and inactive.check_password(password):
                return Response(
                    {"code": "account_inactive", "message": "account is inactive"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"code": "auth_failed", "message": "invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception as e:
                log.warning("logout blacklist failed: %s", e)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RegisterView(APIView):
    """公开注册 API — 无需认证。注册即登录,返回 JWT + user。"""

    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        email = (request.data.get("email") or "").strip()

        # 1. username 非空
        if not username:
            return Response(
                {"code": "bad_request", "message": "username is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. username 唯一
        if User.objects.filter(username=username).exists():
            return Response(
                {"code": "user_exists", "message": "username already taken"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. 密码强度
        ok, msg = validate_password_strength(password)
        if not ok:
            return Response(
                {"code": "weak_password", "message": msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. 创建用户 + profile
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
        )
        UserProfile.objects.get_or_create(
            user=user,
            defaults={"auth_source": "local"},
        )

        # 5. 赋内置 user 角色(兜底 get_or_create,防止没跑 seed)
        user_role, _ = Role.objects.get_or_create(
            name="user",
            defaults={
                "description": "普通用户",
                "permissions": ["page:dashboard"],
                "is_system": True,
            },
        )
        UserRole.objects.get_or_create(user=user, role=user_role)

        # 6. 注册即登录:签发 token
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )
