from cryptography.fernet import Fernet
import pytest

from app.auth import create_customer, init_auth_db
from app import mexc_credential_vault as vault


def setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mexc-vault.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    init_auth_db()
    vault.init_db()


def test_mexc_credentials_are_encrypted_and_customer_scoped(monkeypatch, tmp_path):
    setup_db(monkeypatch, tmp_path)
    first = create_customer("mexc-first@example.com", "strong-password-one")
    second = create_customer("mexc-second@example.com", "strong-password-two")
    api_key, api_secret = "dummy-api-key", "dummy-api-secret-never-real"

    saved = vault.save(first["id"], api_key, api_secret)
    assert saved["connected"] is True
    assert vault.load(first["id"]) == {"api_key": api_key, "api_secret": api_secret}
    assert vault.load(second["id"]) is None
    raw = (tmp_path / "mexc-vault.sqlite3").read_bytes()
    assert api_key.encode() not in raw
    assert api_secret.encode() not in raw
    assert vault.metadata(second["id"])["connected"] is False
    assert vault.delete(first["id"]) is True
    assert vault.load(first["id"]) is None


def test_mexc_vault_rejects_empty_or_oversized_credentials(monkeypatch, tmp_path):
    setup_db(monkeypatch, tmp_path)
    customer = create_customer("mexc-invalid@example.com", "strong-password-three")
    with pytest.raises(ValueError):
        vault.save(customer["id"], "", "secret")
    with pytest.raises(ValueError):
        vault.save(customer["id"], "key", "x" * 513)


def test_mexc_vault_requires_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mexc-no-key.sqlite3"))
    monkeypatch.delenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", raising=False)
    init_auth_db()
    vault.init_db()
    customer = create_customer("mexc-no-key@example.com", "strong-password-four")
    with pytest.raises(vault.MexcVaultError):
        vault.save(customer["id"], "key", "secret")
