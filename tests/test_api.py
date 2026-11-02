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
    monkeypatch.delenv("DERIV_DEMO_TOKEN", raising=False)
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    response = client.get("/api/deriv/demo/status")
    assert response.status_code == 503
