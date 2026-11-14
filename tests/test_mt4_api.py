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
