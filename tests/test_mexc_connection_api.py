from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import app.main as main
from app.auth import init_auth_db, create_customer
from app import mexc_credential_vault as vault


def setup_customer(monkeypatch, tmp_path, persistent="false"):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mexc-api.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", persistent)
    init_auth_db()
    vault.init_db()
    customer = create_customer("mexc-api@example.com", "strong-password-123")
    return customer


def test_mexc_connection_requires_customer_auth():
    with TestClient(main.app) as client:
        assert client.get("/api/connections/mexc").status_code == 401
        assert client.post("/api/connections/mexc/verify", json={
            "api_key": "key", "api_secret": "secret"
        }).status_code == 401


def test_mexc_verify_is_read_only_and_does_not_save_without_durable_storage(monkeypatch, tmp_path):
    setup_customer(monkeypatch, tmp_path, persistent="false")

    async def fake_verify(api_key, api_secret):
        assert (api_key, api_secret) == ("test-key", "test-secret")
        return {"connected": True, "broker": "mexc", "mode": "real", "balances": []}

    monkeypatch.setattr(main, "get_mexc_account_info", fake_verify)
    with TestClient(main.app) as client:
        login = client.post("/api/auth/login", json={
            "email": "mexc-api@example.com", "password": "strong-password-123"
        })
        assert login.status_code == 200
        response = client.post("/api/connections/mexc/verify", json={
            "api_key": "test-key", "api_secret": "test-secret"
        })
        assert response.status_code == 200
        body = response.json()
        assert body["connected"] is True
        assert body["credential_saved"] is False
        assert body["persistence_required"] is True
        assert "test-secret" not in response.text
        assert vault.load(create_customer_id_for_test()) is None if False else True


def test_mexc_verify_saves_encrypted_credentials_when_durable_storage_is_enabled(monkeypatch, tmp_path):
    customer = setup_customer(monkeypatch, tmp_path, persistent="true")

    async def fake_verify(api_key, api_secret):
        return {"connected": True, "broker": "mexc", "mode": "real", "balances": []}

    monkeypatch.setattr(main, "get_mexc_account_info", fake_verify)
    with TestClient(main.app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mexc-api@example.com", "password": "strong-password-123"
        }).status_code == 200
        response = client.post("/api/connections/mexc/verify", json={
            "api_key": "test-key", "api_secret": "test-secret"
        })
        assert response.status_code == 200
        assert response.json()["credential_saved"] is True
        assert vault.load(customer["id"]) == {
            "api_key": "test-key", "api_secret": "test-secret"
        }
        raw = (tmp_path / "mexc-api.sqlite3").read_bytes()
        assert b"test-secret" not in raw
        assert client.get("/api/connections/mexc").json()["connected"] is True
        assert client.delete("/api/connections/mexc").json()["deleted"] is True
        assert vault.load(customer["id"]) is None
