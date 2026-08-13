import os

from .base import *  # noqa: F401, F403

DEBUG = False

# 生产环境强制要求显式设置密钥,避免静默使用 base.py 的 dev fallback 签发 JWT。
assert os.environ.get("QUANLY_SECRET_KEY"), (
    "QUANLY_SECRET_KEY 必须在生产环境设置(否则会用不安全的 dev fallback 签发 JWT)"
)
