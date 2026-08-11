from cryptography.fernet import Fernet

from apps.credentials.crypto import decrypt, encrypt


def test_encrypt_roundtrip(settings):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    c = encrypt("secret-abc")
    assert c != "secret-abc"
    assert decrypt(c) == "secret-abc"
