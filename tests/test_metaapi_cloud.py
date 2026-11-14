import pytest
from app.auth import create_customer, init_auth_db
from app import metaapi_cloud


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "metaapi.sqlite3"))
    init_auth_db()
    metaapi_cloud.init_db()
    customer = create_customer("metaapi@example.com", "a-strong-password")
    return customer


def test_platform_validation_and_server_required(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("METAAPI_TOKEN", "test-token")
    import asyncio
    with pytest.raises(ValueError, match="MT4 or MT5"):
        asyncio.run(metaapi_cloud.connect_customer_account(customer["id"], "mt6", "JustMarkets", "server"))
    with pytest.raises(ValueError, match="exact trading server"):
        asyncio.run(metaapi_cloud.connect_customer_account(customer["id"], "mt5", "JustMarkets", ""))


def test_missing_provider_token_is_reported(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    monkeypatch.delenv("METAAPI_TOKEN", raising=False)
    with pytest.raises(metaapi_cloud.MetaApiError, match="not configured"):
        import asyncio
        asyncio.run(metaapi_cloud.connect_customer_account(customer["id"], "mt4", "JustMarkets", "JM-Demo"))


def test_account_metadata_is_customer_isolated(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    with metaapi_cloud._db() as db:
        db.execute(
            "INSERT INTO metaapi_customer_accounts "
            "(customer_id, platform, account_id, broker, server) VALUES (?, ?, ?, ?, ?)",
            (customer["id"], "mt5", "metaapi-account-1", "JustMarkets", "JM-Demo"),
        )
    rows = metaapi_cloud.metadata(customer["id"])
    assert len(rows) == 1
    assert rows[0]["platform"] == "mt5"
    assert rows[0]["account_id"] == "metaapi-account-1"
    assert metaapi_cloud.metadata("another-customer") == []
