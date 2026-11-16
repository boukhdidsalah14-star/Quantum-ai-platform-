import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.auth import create_customer, init_auth_db
from app.ctrader_oauth import (
    CTraderOAuthError,
    complete_authorization,
    create_authorization,
    delete_authorization,
    init_db,
    load_tokens,
    status,
)


def setup_ctrader(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "ctrader.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("CTRADER_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "CTRADER_REDIRECT_URI",
        "https://quantum-ai.example/api/connections/ctrader/callback",
    )
    init_auth_db()
    init_db()
    return create_customer("ctrader@example.com", "a-strong-password")


def test_create_authorization_uses_mobile_web_redirect_and_short_lived_state(monkeypatch, tmp_path):
    customer = setup_ctrader(monkeypatch, tmp_path)
    state, url = create_authorization(customer["id"])
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "id.ctrader.com"
    assert params["client_id"] == ["test-client-id"]
    assert params["redirect_uri"] == [
        "https://quantum-ai.example/api/connections/ctrader/callback"
    ]
    assert params["scope"] == ["trading"]
    assert params["product"] == ["web"]
    assert len(state) >= 32


def test_authorization_code_is_exchanged_and_tokens_are_encrypted(monkeypatch, tmp_path):
    customer = setup_ctrader(monkeypatch, tmp_path)
    state, _ = create_authorization(customer["id"])

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "accessToken": "access-token-test",
                "refreshToken": "refresh-token-test",
                "expiresIn": 3600,
                "tokenType": "bearer",
                "errorCode": None,
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *, params, headers):
            assert url.endswith("/apps/token")
            assert params["grant_type"] == "authorization_code"
            assert params["code"] == "temporary-code"
            assert params["client_secret"] == "test-client-secret"
            return FakeResponse()

    monkeypatch.setattr("app.ctrader_oauth.httpx.AsyncClient", FakeClient)
    saved_customer = asyncio.run(complete_authorization("temporary-code", state))

    assert saved_customer == customer["id"]
    tokens = load_tokens(customer["id"])
    assert tokens["access_token"] == "access-token-test"
    assert tokens["refresh_token"] == "refresh-token-test"
    snapshot = status(customer["id"])
    assert snapshot["authorized"] is True
    assert snapshot["connected"] is False
    assert snapshot["trading_enabled"] is False
    assert snapshot["state"] == "AUTHORISED_ACCOUNT_SYNC_PENDING"


def test_authorization_state_cannot_be_reused(monkeypatch, tmp_path):
    customer = setup_ctrader(monkeypatch, tmp_path)
    state, _ = create_authorization(customer["id"])

    class RejectedResponse:
        status_code = 400

    class RejectedClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return RejectedResponse()

    monkeypatch.setattr("app.ctrader_oauth.httpx.AsyncClient", RejectedClient)
    with pytest.raises(CTraderOAuthError, match="rejected"):
        asyncio.run(complete_authorization("temporary-code", state))

    monkeypatch.setattr(
        "app.ctrader_oauth.httpx.AsyncClient",
        lambda *args, **kwargs: pytest.fail("A reused state must be rejected before token exchange"),
    )
    with pytest.raises(CTraderOAuthError, match="expired"):
        asyncio.run(complete_authorization("temporary-code", state))


def test_disconnect_deletes_authorization(monkeypatch, tmp_path):
    customer = setup_ctrader(monkeypatch, tmp_path)
    state, _ = create_authorization(customer["id"])
    from app.ctrader_oauth import _db, _cipher
    import json
    import time

    encrypted = _cipher().encrypt(json.dumps({
        "access_token": "a", "refresh_token": "r", "expires_at": int(time.time()) + 3600
    }).encode())
    with _db() as db:
        db.execute(
            "INSERT INTO ctrader_customer_tokens VALUES (?, ?, ?, ?)",
            (customer["id"], encrypted, int(time.time()), int(time.time())),
        )
    assert delete_authorization(customer["id"]) is True
    assert load_tokens(customer["id"]) is None
    assert status(customer["id"])["authorized"] is False
