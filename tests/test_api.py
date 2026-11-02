from fastapi.testclient import TestClient
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
    assert brokers["mexc"]["status"] == "integration_pending"
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
