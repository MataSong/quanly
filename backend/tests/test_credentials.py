"""Tests for P1-A: OKX Credential management — encryption, CRUD, multi-tenant, permissions."""
import pytest
from django.contrib.auth.models import User
from cryptography.fernet import InvalidToken

from core.credentials.crypto import decrypt, encrypt
from core.credentials.models import Credential
from core.accounts.models import Role, UserRole


# ──────────────────────────────────────────────
# Crypto helpers
# ──────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    """encrypt → decrypt must return the original plaintext."""
    plain = "my-super-secret-api-key-1234"
    token = encrypt(plain)
    assert decrypt(token) == plain


def test_encrypt_returns_different_each_call():
    """Fernet tokens are nonce-based; same input yields different ciphertexts."""
    plain = "same-text"
    assert encrypt(plain) != encrypt(plain)


def test_decrypt_wrong_key_raises():
    """Decrypting a token with the wrong key should raise InvalidToken."""
    from cryptography.fernet import Fernet
    other_key = Fernet.generate_key()
    other_fernet = Fernet(other_key)
    token = other_fernet.encrypt(b"secret").decode()
    with pytest.raises(InvalidToken):
        decrypt(token)


# ──────────────────────────────────────────────
# Model + DB
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_create_credential_stores_ciphertext():
    """After creation, the DB row must NOT store plaintext in encrypted fields."""
    user = User.objects.create_user("cred_user", password="pw")
    api_key = "OKXAPIKEY1234567"
    secret = "supersecretvalue"
    passphrase = "mypassphrase"

    cred = Credential.objects.create(
        user=user,
        env=Credential.ENV_SIM,
        label="test-key",
        api_key_enc=encrypt(api_key),
        secret_enc=encrypt(secret),
        passphrase_enc=encrypt(passphrase),
    )

    # Reload from DB to make sure we're testing the stored value
    cred.refresh_from_db()
    assert cred.api_key_enc != api_key
    assert cred.secret_enc != secret
    assert cred.passphrase_enc != passphrase

    # But they must decrypt correctly
    assert decrypt(cred.api_key_enc) == api_key
    assert decrypt(cred.secret_enc) == secret
    assert decrypt(cred.passphrase_enc) == passphrase


@pytest.mark.django_db
def test_credential_str():
    user = User.objects.create_user("str_user", password="pw")
    cred = Credential.objects.create(
        user=user,
        env=Credential.ENV_LIVE,
        label="label1",
        api_key_enc=encrypt("k"),
        secret_enc=encrypt("s"),
        passphrase_enc=encrypt("p"),
    )
    assert "live" in str(cred)
    assert "label1" in str(cred)


# ──────────────────────────────────────────────
# Serializer: read fields + masking
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_read_serializer_masks_api_key_and_omits_secrets():
    from core.credentials.serializers import CredentialReadSerializer

    user = User.objects.create_user("read_user", password="pw")
    api_key = "ABCDEF1234"
    cred = Credential.objects.create(
        user=user,
        env=Credential.ENV_SIM,
        label="read-test",
        api_key_enc=encrypt(api_key),
        secret_enc=encrypt("secret-value"),
        passphrase_enc=encrypt("pass-value"),
    )

    data = CredentialReadSerializer(cred).data
    assert "secret" not in data
    assert "passphrase" not in data
    assert "secret_enc" not in data
    assert "passphrase_enc" not in data
    assert "api_key_enc" not in data

    # api_key_masked: ****<last4>
    assert "api_key_masked" in data
    masked = data["api_key_masked"]
    assert masked.startswith("****")
    assert masked.endswith(api_key[-4:])


@pytest.mark.django_db
def test_read_serializer_short_api_key_masked():
    """api_key shorter than 4 chars should still mask with **** prefix."""
    from core.credentials.serializers import CredentialReadSerializer

    user = User.objects.create_user("short_key_user", password="pw")
    cred = Credential.objects.create(
        user=user,
        env=Credential.ENV_SIM,
        label="short",
        api_key_enc=encrypt("AB"),
        secret_enc=encrypt("s"),
        passphrase_enc=encrypt("p"),
    )
    data = CredentialReadSerializer(cred).data
    assert data["api_key_masked"] == "****AB"


# ──────────────────────────────────────────────
# API endpoints — unauthenticated
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_unauthenticated_list_returns_401(api_client):
    resp = api_client.get("/api/credentials/")
    assert resp.status_code == 401


# ──────────────────────────────────────────────
# API endpoints — permission checks
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_get_without_view_perm_returns_403(api_client):
    """A user without credentials:view should get 403 on GET."""
    user = User.objects.create_user("noperm_get", password="pw")
    api_client.force_authenticate(user)
    resp = api_client.get("/api/credentials/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_post_without_manage_perm_returns_403(api_client):
    """A user without credentials:manage should get 403 on POST."""
    user = User.objects.create_user("noperm_post", password="pw")
    # Give view but NOT manage
    role = Role.objects.create(name="cred_viewer_np", permissions=["credentials:view"])
    UserRole.objects.create(user=user, role=role)
    api_client.force_authenticate(user)
    resp = api_client.post("/api/credentials/", {
        "env": "sim", "label": "l", "api_key": "k", "secret": "s", "passphrase": "p",
    }, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_delete_without_manage_perm_returns_403(api_client):
    """A user without credentials:manage should get 403 on DELETE."""
    owner = User.objects.create_user("owner_del_403", password="pw")
    cred = Credential.objects.create(
        user=owner, env=Credential.ENV_SIM, label="to-del",
        api_key_enc=encrypt("k"), secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    # Give only view
    role = Role.objects.create(name="cred_viewer_del", permissions=["credentials:view"])
    UserRole.objects.create(user=owner, role=role)
    api_client.force_authenticate(owner)
    resp = api_client.delete(f"/api/credentials/{cred.id}/")
    assert resp.status_code == 403


# ──────────────────────────────────────────────
# API endpoints — happy-path CRUD
# ──────────────────────────────────────────────

def _make_manager(username: str) -> User:
    """Helper: create a user with both credentials:view and credentials:manage."""
    user = User.objects.create_user(username, password="pw")
    role = Role.objects.create(
        name=f"cred_manager_{username}",
        permissions=["credentials:view", "credentials:manage"],
    )
    UserRole.objects.create(user=user, role=role)
    return user


@pytest.mark.django_db
def test_create_credential_returns_masked_data(api_client):
    """POST /api/credentials/ returns 201 with api_key_masked, no secret/passphrase."""
    user = _make_manager("create_ok")
    api_client.force_authenticate(user)
    resp = api_client.post("/api/credentials/", {
        "env": "sim",
        "label": "my-key",
        "api_key": "OKXKEYABCDEF1234",
        "secret": "some-secret",
        "passphrase": "my-phrase",
    }, format="json")
    assert resp.status_code == 201
    data = resp.data
    assert data["label"] == "my-key"
    assert data["env"] == "sim"
    assert "api_key_masked" in data
    assert data["api_key_masked"].startswith("****")
    assert data["api_key_masked"].endswith("1234")
    assert "secret" not in data
    assert "passphrase" not in data


@pytest.mark.django_db
def test_list_credentials_returns_only_own(api_client):
    """GET /api/credentials/ should only list the authenticated user's credentials."""
    user_a = _make_manager("list_user_a")
    user_b = _make_manager("list_user_b")

    # Create cred for A
    Credential.objects.create(
        user=user_a, env=Credential.ENV_SIM, label="a-key",
        api_key_enc=encrypt("AKEY1234"), secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    # Create cred for B
    Credential.objects.create(
        user=user_b, env=Credential.ENV_LIVE, label="b-key",
        api_key_enc=encrypt("BKEY5678"), secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )

    api_client.force_authenticate(user_a)
    resp = api_client.get("/api/credentials/")
    assert resp.status_code == 200
    labels = [c["label"] for c in resp.data]
    assert "a-key" in labels
    assert "b-key" not in labels


@pytest.mark.django_db
def test_delete_credential(api_client):
    """DELETE /api/credentials/{id}/ removes the credential."""
    user = _make_manager("delete_ok")
    cred = Credential.objects.create(
        user=user, env=Credential.ENV_SIM, label="del-key",
        api_key_enc=encrypt("DELKEY1234"), secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    api_client.force_authenticate(user)
    resp = api_client.delete(f"/api/credentials/{cred.id}/")
    assert resp.status_code == 204
    assert not Credential.objects.filter(id=cred.id).exists()


@pytest.mark.django_db
def test_cannot_delete_other_users_credential(api_client):
    """User A must not be able to delete User B's credential (multi-tenant isolation)."""
    user_a = _make_manager("del_tenant_a")
    user_b = _make_manager("del_tenant_b")
    cred_b = Credential.objects.create(
        user=user_b, env=Credential.ENV_SIM, label="b-private",
        api_key_enc=encrypt("BPRIVKEY1234"), secret_enc=encrypt("s"), passphrase_enc=encrypt("p"),
    )
    api_client.force_authenticate(user_a)
    resp = api_client.delete(f"/api/credentials/{cred_b.id}/")
    # queryset is scoped to user_a, so cred_b is not found
    assert resp.status_code == 404


# ──────────────────────────────────────────────
# env isolation
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_env_isolation_sim_and_live(api_client):
    """A user can have separate credentials for sim and live environments."""
    user = _make_manager("env_iso")
    api_client.force_authenticate(user)

    api_client.post("/api/credentials/", {
        "env": "sim", "label": "iso-key",
        "api_key": "SIMKEY12345678AB", "secret": "s", "passphrase": "p",
    }, format="json")
    api_client.post("/api/credentials/", {
        "env": "live", "label": "iso-key",
        "api_key": "LIVEKEY1234ABCD", "secret": "s", "passphrase": "p",
    }, format="json")

    resp = api_client.get("/api/credentials/")
    assert resp.status_code == 200
    envs = {c["env"] for c in resp.data}
    assert "sim" in envs
    assert "live" in envs


@pytest.mark.django_db
def test_unique_together_enforced(api_client):
    """(user, env, label) must be unique; duplicate should return 400."""
    user = _make_manager("unique_tog")
    api_client.force_authenticate(user)
    payload = {"env": "sim", "label": "dup-key", "api_key": "K1", "secret": "s", "passphrase": "p"}
    r1 = api_client.post("/api/credentials/", payload, format="json")
    assert r1.status_code == 201
    r2 = api_client.post("/api/credentials/", payload, format="json")
    assert r2.status_code == 400


# ──────────────────────────────────────────────
# Superuser
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_superuser_can_create_and_list(api_client):
    """Superuser bypasses permission checks and can CRUD credentials."""
    su = User.objects.create_superuser("su_cred", "su@x.com", "pw")
    api_client.force_authenticate(su)
    resp = api_client.post("/api/credentials/", {
        "env": "live", "label": "su-key",
        "api_key": "SUKEY12345678901", "secret": "sec", "passphrase": "pp",
    }, format="json")
    assert resp.status_code == 201
    list_resp = api_client.get("/api/credentials/")
    assert list_resp.status_code == 200
    assert len(list_resp.data) == 1
