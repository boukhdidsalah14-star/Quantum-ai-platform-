from fastapi.testclient import TestClient

import app.main as main


def register_member(client):
    response = client.post("/api/auth/register", json={
        "email": "mt4-api@example.com", "password": "a-strong-password"
    })
    assert response.status_code == 200
    return response


def test_mt4_bridge_registration_and_position_sync(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-api.sqlite3"))
    with TestClient(main.app) as client:
        register_member(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2"
        })
        assert registered.status_code == 200
        token = registered.json()["bridge_token"]
        assert registered.json()["token_shown_once"] is True
        assert registered.json()["execution_enabled"] is False

        sync = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer " + token
        }, json={
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
                "open_time": 1700000000, "magic": 914110
            }],
            "quotes": {"XAUUSD": {"bid": 2000.9, "ask": 2001.1}}
        })
        assert sync.status_code == 200
        positions = client.get("/api/mt4/positions")
        assert positions.status_code == 200
        assert positions.json()["connected"] is True
        assert positions.json()["positions"][0]["ticket"] == "9001"


def test_mt4_bridge_rejects_missing_or_invalid_ea_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-auth.sqlite3"))
    with TestClient(main.app) as client:
        register_member(client)
        response = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer not-a-valid-token"
        }, json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "balance": 1, "equity": 1,
            "currency": "USD", "positions": [], "quotes": {}
        })
        assert response.status_code == 401


def test_mt4_command_polling_is_empty_until_server_switch_is_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-poll.sqlite3"))
    with TestClient(main.app) as client:
        register_member(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2"
        })
        token = registered.json()["bridge_token"]
        response = client.get("/api/mt4/bridge/commands", headers={
            "Authorization": "Bearer " + token
        }, params={
            "account_login": "12345678",
            "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd"
        })
        assert response.status_code == 200
        assert response.text == ""


def test_mt4_candle_endpoint_returns_broker_candles_for_signed_in_customer(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-candles.sqlite3"))
    with TestClient(main.app) as client:
        register_member(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2"
        })
        token = registered.json()["bridge_token"]
        rows = [{
            "time": 1700000000 + i * 900, "open": 2000 + i * 0.1,
            "high": 2000.2 + i * 0.1, "low": 1999.9 + i * 0.1,
            "close": 2000.1 + i * 0.1, "volume": 100 + i,
        } for i in range(60)]
        sync = client.post("/api/mt4/bridge/candles", headers={
            "Authorization": "Bearer " + token
        }, json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "symbol": "XAUUSD",
            "timeframe": "15m", "candles": rows,
        })
        assert sync.status_code == 200
        chart = client.get("/api/mt4/candles/XAUUSD?timeframe=15m")
        assert chart.status_code == 200
        assert chart.json()["source"] == "JustMarkets MT4 broker candles"
        assert len(chart.json()["candles"]) == 60


def test_mt4_auto_trader_api_requires_subscription_and_starts_stops_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-auto-api.sqlite3"))
    monkeypatch.setattr(main, "subscription_for_customer", lambda customer_id: {"active": True})
    with TestClient(main.app) as client:
        register_member(client)
        registered = client.post("/api/mt4/bridge/register", json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2"
        })
        token = registered.json()["bridge_token"]
        sync = client.post("/api/mt4/bridge/sync", headers={
            "Authorization": "Bearer " + token
        }, json={
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "balance": 10000, "equity": 10000,
            "currency": "USD", "positions": [],
            "quotes": {"XAUUSD": {"bid": 2000, "ask": 2000.2}},
        })
        assert sync.status_code == 200

        started = client.post("/api/mt4/auto/start", json={
            "symbol": "XAUUSD", "timeframe": "15m", "lots": 0.01,
            "stop_atr": 1.5, "target_atr": 2.0, "max_drawdown_pct": 10,
        })
        assert started.status_code == 200
        assert started.json()["active"] is True
        assert started.json()["execution_mode"] == "demo_only"

        status = client.get("/api/mt4/auto")
        assert status.status_code == 200
        assert status.json()["active"] is True
        assert status.json()["server_execution_enabled"] is True

        stopped = client.post("/api/mt4/auto/stop")
        assert stopped.status_code == 200
        assert stopped.json()["active"] is False


def test_mt4_auto_trader_api_rejects_when_server_demo_switch_is_off(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "false")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-auto-locked.sqlite3"))
    with TestClient(main.app) as client:
        register_member(client)
        response = client.post("/api/mt4/auto/start", json={
            "symbol": "XAUUSD", "timeframe": "15m", "lots": 0.01,
        })
        assert response.status_code == 403
