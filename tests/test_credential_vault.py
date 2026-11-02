from cryptography.fernet import Fernet
import pytest

from app.auth import create_customer, init_auth_db
from app import credential_vault as vault


def setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "vault.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    init_auth_db()
    vault.init_vault_db()


def test_demo_credentials_are_encrypted_and_customer_scoped(monkeypatch, tmp_path):
    setup_db(monkeypatch, tmp_path)
    first = create_customer("vault1@example.com", "strong-password-one")
    second = create_customer("vault2@example.com", "strong-password-two")
    secret = "dummy-demo-token-never-real"
    saved = vault.save_demo(first["id"], "VRTC123456", secret)
    assert saved["connected"] is True
    assert vault.load_demo(first["id"]) == {"account_id": "VRTC123456", "token": secret}
    assert vault.load_demo(second["id"]) is None
    raw = (tmp_path / "vault.sqlite3").read_bytes()
    assert secret.encode() not in raw
    assert vault.metadata(second["id"])["connected"] is False
    assert vault.delete_demo(first["id"]) is True
    assert vault.load_demo(first["id"]) is None


def test_demo_vault_rejects_real_account_ids(monkeypatch, tmp_path):
    setup_db(monkeypatch, tmp_path)
    customer = create_customer("vault3@example.com", "strong-password-three")
    with pytest.raises(ValueError):
        vault.save_demo(customer["id"], "CR123456", "dummy-token")


def test_demo_vault_requires_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "no-key.sqlite3"))
    monkeypatch.delenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", raising=False)
    init_auth_db()
    vault.init_vault_db()
    customer = create_customer("vault4@example.com", "strong-password-four")
    with pytest.raises(vault.VaultError):
        vault.save_demo(customer["id"], "VRTC123456", "dummy-token")
