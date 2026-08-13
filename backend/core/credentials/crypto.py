"""Fernet symmetric encryption helpers for credential storage.

Usage:
    from core.credentials.crypto import encrypt, decrypt

    token = encrypt("my-api-secret")
    plain = decrypt(token)  # => "my-api-secret"

Key source: env var QUANLY_CREDENTIALS_ENC_KEY (Fernet.generate_key() format, base64).
Dev fallback is provided for convenience; production must set the env var explicitly
(prod.py asserts its presence).

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os

from cryptography.fernet import Fernet, InvalidToken

# Dev-only static fallback key — DO NOT use in production.
# This is a valid Fernet key for local development convenience.
_DEV_FALLBACK_KEY = b"DEV_KEY_REPLACE_ME_IN_PROD_AAAAA="  # placeholder shape

# Build a real valid key for dev fallback (generated once, constant for dev).
# This is intentionally a fixed key so dev restarts don't break existing encrypted data.
_DEV_STATIC_FERNET_KEY = b"T2txcS1kZXYtZmFsbGJhY2sta2V5LTMyYnl0ZXMhISE="

# Validate it is a proper Fernet key length (32 bytes URL-safe base64 = 44 chars).
# The key above decodes to 32 bytes.
_DEV_FERNET = Fernet(_DEV_STATIC_FERNET_KEY)  # will raise at import if invalid


def _get_fernet() -> Fernet:
    """Return the Fernet instance, preferring the env-supplied key."""
    raw = os.environ.get("QUANLY_CREDENTIALS_ENC_KEY", "").strip()
    if raw:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    # Dev fallback — only safe for non-production environments.
    return _DEV_FERNET


def encrypt(plain: str) -> str:
    """Encrypt a plaintext string, return URL-safe base64 Fernet token as str."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token string back to plaintext.

    Raises:
        cryptography.fernet.InvalidToken: if token is tampered or key is wrong.
    """
    return _get_fernet().decrypt(token.encode()).decode()
