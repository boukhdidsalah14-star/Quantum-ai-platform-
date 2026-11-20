from fastapi.testclient import TestClient
from cryptography.fernet import Fernet

import app.main as main


def _register_customer(client):
    response = client.post("/api/auth/register", json={
        "email": "mt4-bridge@example.com",
        "password": "a-strong-password",
    })
    assert response.status_code == 200
    return response


def _sync_payload():
    return {
        "account_login": "12345678",
        "account_server": "JustMarkets-Demo2",
        "company": "JustMarkets Ltd",
        "balance": 10000,
        "equity": 9990,
        "currency": "USD",
        "positions": [{
            "ticket": 9001, "symbol": "XAUUSD", "side": "BUY", "lots": 0.01,
            "open_price": 2000, "current_price": 2001, "stop_loss": 1990,
            "take_profit": 2020, "profit": 1, "swap": 0, "commission": 0,
            "open_time": 1700000000, "magic": 914110,
        }],
        "quotes": {"XAUUSD": {"bid": 2000.9, "ask": 2001.1}},
    }


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum-mt4.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_mt4_bridge_registration_requires_durable_storage(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(main.app) as client:
        _register_customer(client)
        response = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
        })
        assert response.status_code == 503
        assert "Durable storage" in response.json()["detail"]


def test_mt4_read_only_bridge_registration_and_snapshot(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with TestClient(main.app) as client:
        _register_customer(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
        })
        assert registered.status_code == 200
        data = registered.json()
        token = data["bridge_token"]
        assert data["token_shown_once"] is True
        assert data["execution_enabled"] is False
        assert data["api_base_url"] == "https://quantum-ai-platform-62cz.onrender.com"

        sync = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer " + token,
        }, json=_sync_payload())
        assert sync.status_code == 200
        status = client.get("/api/mt4/bridge/status")
        assert status.status_code == 200
        snapshot = status.json()
        assert snapshot["connected"] is True
        assert snapshot["balance"] == 10000
        assert snapshot["positions"][0]["ticket"] == "9001"
        assert snapshot["execution_enabled"] is False


def test_mt4_bridge_rejects_wrong_server_and_invalid_token(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with TestClient(main.app) as client:
        _register_customer(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
        })
        token = registered.json()["bridge_token"]
        wrong = _sync_payload()
        wrong["account_server"] = "OtherBroker-Demo"
        response = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer " + token,
        }, json=wrong)
        assert response.status_code == 401
        invalid = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer not-a-token",
        }, json=_sync_payload())
        assert invalid.status_code == 401


def test_mt4_bridge_candles_are_customer_scoped(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "test-encryption-key")
    with TestClient(main.app) as client:
        _register_customer(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
        })
        token = registered.json()["bridge_token"]
        candles = []
        for i in range(60):
            close = 2000 + i * 0.1
            candles.append({
                "time": 1700000000 + i * 900,
                "open": close - 0.05, "high": close + 0.1,
                "low": close - 0.1, "close": close, "volume": 100 + i,
            })
        sync = client.post("/api/mt4/bridge/candles", headers={
            "Authorization": "Bearer " + token,
        }, json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "symbol": "XAUUSD",
            "timeframe": "15m", "candles": candles,
        })
        assert sync.status_code == 200
        chart = client.get("/api/mt4/candles/XAUUSD?timeframe=15m")
        assert chart.status_code == 200
        assert chart.json()["source"] == "JustMarkets MT4 broker candles"
        assert len(chart.json()["candles"]) == 60


def test_mt4_status_and_positions_require_customer_login(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    with TestClient(main.app) as client:
        assert client.get("/api/mt4/bridge/status").status_code == 401
        assert client.get("/api/mt4/positions").status_code == 401
