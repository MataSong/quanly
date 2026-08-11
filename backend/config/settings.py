import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "corsheaders",
    "apps.users",
    "apps.credentials",
    "apps.exchanges",
    "apps.market",
    "apps.trading",
    "apps.assets",
    "apps.strategy",
    "apps.backtest",
    "apps.finance",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "users.User"

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "600/min",
        "trade": "120/min",
    },
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

SECRET_ENCRYPTION_KEY = os.environ.get("SECRET_ENCRYPTION_KEY", "")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "quanly")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "market")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# OKX WebSocket 端点(实盘/虚拟盘)
OKX_PRIVATE_WS_LIVE = os.environ.get(
    "OKX_PRIVATE_WS_LIVE", "wss://ws.okx.com:8443/ws/v5/private"
)
OKX_PRIVATE_WS_SIM = os.environ.get(
    "OKX_PRIVATE_WS_SIM", "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
)
OKX_PUBLIC_WS_LIVE = os.environ.get(
    "OKX_PUBLIC_WS_LIVE", "wss://ws.okx.com:8443/ws/v5/public"
)
OKX_PUBLIC_WS_SIM = os.environ.get(
    "OKX_PUBLIC_WS_SIM", "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
)
# OKX REST 定时全量校正间隔(秒)
OKX_SYNC_INTERVAL = int(os.environ.get("OKX_SYNC_INTERVAL", "20"))

# Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
# 定时用 OKX REST 全量校正本地余额/持仓(兜底 WS 遗漏),间隔由 OKX_SYNC_INTERVAL 控制
CELERY_BEAT_SCHEDULE = {
    "periodic-okx-sync": {
        "task": "apps.trading.tasks.periodic_okx_sync",
        "schedule": float(OKX_SYNC_INTERVAL),
    },
}
# 策略容器运行所需
BACKEND_INTERNAL_URL = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")
STRATEGY_RUNNER_IMAGE = os.environ.get("STRATEGY_RUNNER_IMAGE", "quanly-strategy-runner")
STRATEGY_DOCKER_NETWORK = os.environ.get("STRATEGY_DOCKER_NETWORK", "quanly_default")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
