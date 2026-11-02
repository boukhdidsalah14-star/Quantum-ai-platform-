from fastapi.testclient import TestClient
import pytest
import app.main as main

client = TestClient(main.app)


def test_health_reports_execution_disabled():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["trading_enabled"] is False
    assert body["order_execution"] is False
    assert body["customer_auth"] == "available"


def test_unknown_symbol_is_rejected():
    response = client.get("/api/candles/NOTREAL?interval=1h")
    assert response.status_code == 400


def test_unknown_interval_is_rejected():
    response = client.get("/api/candles/BTCUSDT?interval=1m")
    assert response.status_code == 400


def test_market_endpoint_returns_adapter_data(monkeypatch):
    async def fake_markets():
        return [{"symbol": "BTCUSDT", "price": "50000"}]
    monkeypatch.setattr(main, "get_market_overview", fake_markets)
    response = client.get("/api/markets")
    assert response.status_code == 200
    assert response.json()["markets"][0]["symbol"] == "BTCUSDT"


def test_deriv_demo_status_requires_credentials(monkeypatch):
    monkeypatch.setenv("QUANTUM_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.delenv("DERIV_DEMO_TOKEN", raising=False)
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    response = client.get("/api/deriv/demo/status", headers={"X-Admin-Key": "test-admin-key"})
    assert response.status_code == 503


def test_deriv_demo_status_rejects_missing_admin_key(monkeypatch):
    monkeypatch.setenv("QUANTUM_ADMIN_API_KEY", "test-admin-key")
    response = client.get("/api/deriv/demo/status")
    assert response.status_code == 403


def test_registration_is_closed_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_CUSTOMER_SIGNUP", raising=False)
    response = client.post("/api/auth/register", json={
        "email": "new@example.com", "password": "a-strong-password"
    })
    assert response.status_code == 403


def test_customer_register_login_me_and_logout(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "customers.sqlite3"))
    with TestClient(main.app) as test_client:
        registered = test_client.post("/api/auth/register", json={
            "email": "Trader@Example.com", "password": "a-strong-password"
        })
        assert registered.status_code == 200
        assert registered.json()["customer"]["email"] == "trader@example.com"
        assert "quantum_session" in test_client.cookies

        me = test_client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["customer"]["email"] == "trader@example.com"

        logged_out = test_client.post("/api/auth/logout")
        assert logged_out.status_code == 200
        assert test_client.get("/api/auth/me").status_code == 401

        login = test_client.post("/api/auth/login", json={
            "email": "TRADER@example.com", "password": "a-strong-password"
        })
        assert login.status_code == 200
        assert test_client.get("/api/auth/me").status_code == 200


def test_customer_password_and_duplicate_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "customers.sqlite3"))
    with TestClient(main.app) as test_client:
        weak = test_client.post("/api/auth/register", json={
            "email": "weak@example.com", "password": "short"
        })
        assert weak.status_code == 400
        good = {"email": "same@example.com", "password": "a-strong-password"}
        assert test_client.post("/api/auth/register", json=good).status_code == 200
        assert test_client.post("/api/auth/register", json=good).status_code == 400
        assert test_client.post("/api/auth/login", json={
            "email": "same@example.com", "password": "wrong-password"
        }).status_code == 401



def test_broker_registry_is_honest_and_execution_stays_disabled(monkeypatch):
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_DEMO_TOKEN", raising=False)
    response = client.get("/api/brokers")
    assert response.status_code == 200
    body = response.json()
    brokers = {item["id"]: item for item in body["brokers"]}
    assert set(brokers) == {"deriv", "iq_option", "mexc"}
    assert brokers["deriv"]["connection_verified"] is False
    assert brokers["iq_option"]["status"] == "compatibility_review"
    assert brokers["mexc"]["status"] == "public_market_data_connected"
    assert body["execution_enabled"] is False
    assert all(item["execution_enabled"] is False for item in body["brokers"])



def test_login_attempt_bucket_limits_and_resets(monkeypatch, tmp_path):
    from app.auth import clear_login_attempts, consume_login_attempt, init_auth_db
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "throttle.sqlite3"))
    init_auth_db()
    for _ in range(10):
        assert consume_login_attempt("person@example.com", "127.0.0.1", now=1000)
    assert consume_login_attempt("person@example.com", "127.0.0.1", now=1000) is False
    assert consume_login_attempt("person@example.com", "127.0.0.1", now=1900)
    clear_login_attempts("person@example.com", "127.0.0.1")
    assert consume_login_attempt("person@example.com", "127.0.0.1", now=1901)



def test_customer_session_endpoints_reject_cross_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "origin.sqlite3"))
    with TestClient(main.app) as test_client:
        headers = {"Origin": "https://attacker.example"}
        assert test_client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"}, headers=headers).status_code == 403
        assert test_client.post("/api/auth/logout", headers=headers).status_code == 403



def test_paper_trading_is_customer_isolated_and_risk_limited(monkeypatch, tmp_path):
    from app.auth import create_customer, init_auth_db
    from app.paper_trading import init_paper_db, open_paper_trade, list_paper_trades, close_paper_trade
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "paper.sqlite3"))
    init_auth_db()
    init_paper_db()
    first = create_customer("first@example.com", "a-strong-password")
    second = create_customer("second@example.com", "another-strong-password")
    trade = open_paper_trade(first["id"], "BTCUSDT", "long", 0.001, 50000, 49000, 52000, "request-1")
    assert trade["status"] == "open"
    assert len(list_paper_trades(first["id"])) == 1
    assert list_paper_trades(second["id"]) == []
    assert close_paper_trade(second["id"], trade["id"], 51000) is None
    closed = close_paper_trade(first["id"], trade["id"], 51000)
    assert closed["status"] == "closed"
    assert closed["realized_pnl"] == 1.0
    with pytest.raises(ValueError):
        open_paper_trade(first["id"], "BTCUSDT", "long", 1, 1000, None, None, "too-large")



def test_paper_trade_api_requires_login_and_uses_public_quote(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "paper-api.sqlite3"))

    async def fake_markets():
        return [{"symbol": "BTCUSDT", "price": "50000"}]

    monkeypatch.setattr(main, "get_market_overview", fake_markets)
    with TestClient(main.app) as test_client:
        assert test_client.get("/api/paper/trades").status_code == 401
        registered = test_client.post("/api/auth/register", json={
            "email": "paper@example.com", "password": "a-strong-password"
        })
        assert registered.status_code == 200
        opened = test_client.post("/api/paper/trades", headers={"Idempotency-Key": "paper-req-1"}, json={
            "symbol": "BTCUSDT", "side": "long", "quantity": 0.001,
            "stop_loss": 48000, "take_profit": 53000
        })
        assert opened.status_code == 200
        assert opened.json()["execution"] == "simulated_only"
        trade_id = opened.json()["trade"]["id"]
        listed = test_client.get("/api/paper/trades")
        assert listed.status_code == 200
        assert listed.json()["trades"][0]["unrealized_pnl"] == 0
        closed = test_client.post(f"/api/paper/trades/{trade_id}/close")
        assert closed.status_code == 200
        assert closed.json()["trade"]["realized_pnl"] == 0



def test_paper_trade_mutations_reject_cross_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "paper-origin.sqlite3"))
    with TestClient(main.app) as test_client:
        test_client.post("/api/auth/register", json={
            "email": "origin@example.com", "password": "a-strong-password"
        })
        headers = {"Origin": "https://attacker.example", "Idempotency-Key": "bad-origin"}
        response = test_client.post("/api/paper/trades", headers=headers, json={
            "symbol": "BTCUSDT", "side": "long", "quantity": 0.001
        })
        assert response.status_code == 403



def test_mexc_public_market_endpoint(monkeypatch):
    async def fake_mexc_markets():
        return [{"symbol": "BTCUSDT", "price": "51000"}]
    monkeypatch.setattr(main, "get_mexc_market_overview", fake_mexc_markets)
    response = client.get("/api/mexc/markets")
    assert response.status_code == 200
    assert response.json()["source"] == "MEXC public Spot API"
    assert response.json()["execution_enabled"] is False
    assert response.json()["markets"][0]["symbol"] == "BTCUSDT"


def test_mexc_candles_reject_unsupported_symbol():
    response = client.get("/api/mexc/candles/NOTREAL?interval=1h")
    assert response.status_code == 400

def test_mexc_market_percentage_is_not_multiplied(monkeypatch):
    from app import mexc_market_data

    async def fake_get_json(path, params=None):
        return [{
            "symbol": "BTCUSDT",
            "lastPrice": "65000",
            "priceChangePercent": "1.25",
            "highPrice": "66000",
            "lowPrice": "64000",
            "volume": "123",
        }]

    monkeypatch.setattr(mexc_market_data, "_get_json", fake_get_json)
    import anyio
    markets = anyio.run(mexc_market_data.get_market_overview)
    assert markets[0]["change_percent"] == "1.25"


def test_mexc_candles_are_normalized_and_limit_is_bounded(monkeypatch):
    from app import mexc_market_data

    seen = {}

    async def fake_get_json(path, params=None):
        seen.update(params or {})
        return [[
            "1700000000000", "10", "12", "9", "11", "100"
        ]]

    monkeypatch.setattr(mexc_market_data, "_get_json", fake_get_json)
    import anyio
    candles = anyio.run(mexc_market_data.get_candles, "btcusdt", "1h", 999)
    assert seen["limit"] == "200"
    assert candles == [{
        "time": 1700000000000,
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "volume": 100.0,
    }]

def test_dashboard_starts_when_telegram_initialization_fails(monkeypatch):
    from app import telegram_bot

    class BrokenTelegramBot:
        updater = None
        running = False
        shutdown_called = False

        async def initialize(self):
            raise RuntimeError("invalid token")

        async def shutdown(self):
            self.shutdown_called = True

    fake_bot = BrokenTelegramBot()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "invalid-test-token")
    monkeypatch.setattr(telegram_bot, "build_application", lambda token: fake_bot)

    with TestClient(main.app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    assert fake_bot.shutdown_called is True

def test_auth_config_reports_registration_closed_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_CUSTOMER_SIGNUP", raising=False)
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json() == {"registration_enabled": False}


def test_auth_config_reports_registration_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json() == {"registration_enabled": True}

