import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_credential_hides_secret(settings):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    u = get_user_model().objects.create_user("u1", password="pass12345")
    c = APIClient()
    c.force_authenticate(u)

    r = c.post(
        "/api/credentials/",
        {
            "env": "sim",
            "label": "d",
            "api_key": "AK1234567890",
            "secret": "S",
            "passphrase": "P",
        },
        format="json",
    )
    assert r.status_code == 201

    r = c.get("/api/credentials/")
    body = str(r.data)
    assert "secret" not in body.lower()
    assert "7890" in body


@pytest.mark.django_db
def test_credential_scoped_to_user(settings):
    settings.SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    User = get_user_model()
    u1 = User.objects.create_user("u1", password="pass12345")
    u2 = User.objects.create_user("u2", password="pass12345")
    c = APIClient()
    c.force_authenticate(u1)
    c.post(
        "/api/credentials/",
        {"env": "sim", "label": "d", "api_key": "AK1", "secret": "S", "passphrase": "P"},
        format="json",
    )
    c.force_authenticate(u2)
    r = c.get("/api/credentials/")
    assert len(r.data) == 0
