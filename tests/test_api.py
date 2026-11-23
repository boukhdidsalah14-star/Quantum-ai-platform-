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


def test_ads_config_never_exposes_invalid_or_partial_adsense_settings(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADSENSE_CLIENT_ID", "not-a-client")
    monkeypatch.setenv("GOOGLE_ADSENSE_BOTTOM_SLOT_ID", "12345")
    response = client.get("/api/ads/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "client_id": "", "slot_id": ""}


def test_ads_diagnostics_accepts_only_known_event_names():
    response = client.post("/api/ads/diagnostics", json={
        "event": "sdk_loaded",
        "sdk_loaded": True,
        "init_available": True,
        "custom_element_defined": True,
        "banner_height": 50,
    })
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_ads_diagnostics_rejects_arbitrary_events():
    response = client.post("/api/ads/diagnostics", json={"event": "dump_all_secrets"})
    assert response.status_code == 400


def test_registration_is_closed_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_CUSTOMER_SIGNUP", raising=False)
    response = client.post("/api/auth/register", json={
        "email": "new@example.com", "password": "a-strong-password"
    })
    assert response.status_code == 403


def test_customer_register_login_me_and_logout(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
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
    monkeypatch.setenv("ENVIRONMENT", "development")
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



def test_broker_registry_contains_only_selected_platforms():
    response = client.get("/api/brokers")
    assert response.status_code == 200
    body = response.json()
    brokers = {item["id"]: item for item in body["brokers"]}
    assert set(brokers) == {"iq_option", "ic_markets"}
    assert body["execution_enabled"] is False
    assert all(item["execution_enabled"] is False for item in body["brokers"])
    assert all(item["real_execution_enabled"] is False for item in body["brokers"])


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
    monkeypatch.setenv("ENVIRONMENT", "development")
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
    assert response.json()["registration_enabled"] is False
    assert response.json()["admin_email"] == "smartgoomaps@gmail.com"
    assert response.json()["admin_login_enabled"] is False


def test_auth_config_reports_registration_enabled(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json()["registration_enabled"] is True
    assert response.json()["admin_email"] == "smartgoomaps@gmail.com"



def test_independent_forex_markets_endpoint(monkeypatch):
    async def fake_markets():
        return [{"symbol": "frxEURUSD", "display_name": "EUR/USD", "price": 1.1, "is_suspended": False}]
    monkeypatch.setattr(main, "get_forex_market_overview", fake_markets)
    response = client.get("/api/market-data/forex/markets")
    assert response.status_code == 200
    assert response.json()["source"] == "Yahoo Finance public Forex data"
    assert response.json()["markets"][0]["symbol"] == "frxEURUSD"


def test_independent_forex_candles_endpoint(monkeypatch):
    async def fake_candles(symbol, granularity, count):
        assert (symbol, granularity, count) == ("frxEURUSD", 900, 40)
        return [{"time": i, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15} for i in range(40)]
    monkeypatch.setattr(main, "get_forex_candles", fake_candles)
    response = client.get("/api/market-data/forex/candles/frxEURUSD?granularity=900&count=40")
    assert response.status_code == 200
    assert response.json()["candles"][0]["close"] == 1.15
    assert response.json()["execution_enabled"] is False


def test_independent_forex_signal_endpoint_is_indicator_only(monkeypatch):
    async def fake_candles(symbol, granularity, count):
        return [{"open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15}] * 60
    monkeypatch.setattr(main, "get_forex_candles", fake_candles)
    response = client.get("/api/signals/forex/frxEURUSD?timeframe=15m")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "frxEURUSD"
    assert body["market_type"] == "forex"
    assert body["execution_enabled"] is False
    assert body["direction"] in {"CALL", "PUT", "WAIT"}


def test_independent_forex_signal_rejects_unknown_timeframe(monkeypatch):
    monkeypatch.setattr(main, "require_paid_customer", lambda request: {"id": "paid-customer"})
    response = client.get("/api/signals/forex/frxEURUSD?timeframe=2m")
    assert response.status_code == 400


def test_crypto_signal_endpoint_is_read_only(monkeypatch):
    async def fake_candles(symbol, interval, limit):
        assert (symbol, interval, limit) == ("BTCUSDT", "1h", 100)
        return [{"open": 100 + i * 0.02, "high": 100 + i * 0.02 + 0.15,
                 "low": 100 + i * 0.02 - 0.15, "close": 100 + i * 0.02}
                for i in range(60)]
    monkeypatch.setattr(main, "get_candles", fake_candles)
    response = client.get("/api/signals/crypto/BTCUSDT?timeframe=1h")
    assert response.status_code == 200
    assert response.json()["execution_enabled"] is False
    assert response.json()["category"] == "crypto"


def test_crypto_signal_rejects_binary_timeframe(monkeypatch):
    monkeypatch.setattr(main, "require_paid_customer", lambda request: {"id": "paid-customer"})
    response = client.get("/api/signals/crypto/BTCUSDT?timeframe=15m")
    assert response.status_code == 400


def test_crypto_backtest_endpoint_is_read_only(monkeypatch):
    async def fake_candles(symbol, interval, limit):
        assert (symbol, interval, limit) == ("SOLUSDT", "4h", 200)
        return [{"open": 100 + i * 0.02, "high": 100 + i * 0.02 + 0.15,
                 "low": 100 + i * 0.02 - 0.15, "close": 100 + i * 0.02}
                for i in range(100)]
    monkeypatch.setattr(main, "get_candles", fake_candles)
    response = client.get("/api/backtest/crypto/SOLUSDT?timeframe=4h")
    assert response.status_code == 200
    assert response.json()["execution_enabled"] is False
    assert response.json()["category"] == "crypto"


def test_risk_policy_is_demo_only_and_not_active():
    response = client.get("/api/risk/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["default_stake_usd"] == 1.0
    assert body["max_stake_usd"] == 2.0
    assert body["daily_loss_limit_usd"] == 25.0
    assert body["max_consecutive_losses"] == 3
    assert body["real_trading_enabled"] is False
    assert body["risk_monitoring_active"] is False
    assert body["execution_enabled"] is False


def test_production_registration_requires_durable_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_CUSTOMER_SIGNUP", "true")
    monkeypatch.delenv("QUANTUM_PERSISTENT_STORAGE", raising=False)
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "ephemeral.sqlite3"))
    with TestClient(main.app) as test_client:
        response = test_client.post("/api/auth/register", json={
            "email": "ephemeral@example.com", "password": "a-strong-password"
        })
        assert response.status_code == 403


def test_signal_endpoints_require_account_and_paid_membership(monkeypatch):
    monkeypatch.setattr(main, "init_auth_db", lambda: None)
    monkeypatch.setattr(main, "get_customer_for_session", lambda token: None)
    assert client.get("/api/signals/forex/frxEURUSD?timeframe=15m").status_code == 401
    assert client.get("/api/signals/crypto/BTCUSDT?timeframe=1h").status_code == 401
    monkeypatch.setattr(main, "get_customer_for_session", lambda token: {"id": "unpaid-customer", "role": "customer"})
    monkeypatch.setattr(main, "subscription_for_customer", lambda customer_id: {"active": False, "status": "inactive"})
    response = client.get("/api/signals/forex/frxEURUSD?timeframe=15m")
    assert response.status_code == 402
    assert "paid membership" in response.json()["detail"].lower()
