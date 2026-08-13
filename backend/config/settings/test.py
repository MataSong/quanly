import os

from .base import *  # noqa: F401, F403

DEBUG = True

# Use a separate test database to avoid touching the dev/prod DB.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "NAME": os.environ.get("POSTGRES_TEST_DB", "quanly_test"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}
