from fastapi.testclient import TestClient

from app.main import app


def test_meta_trader_and_mt4_api_routes_are_removed():
    client = TestClient(app)
    assert client.get("/api/connections/metatrader").status_code == 404
    assert client.get("/api/connections/metatrader/mt4").status_code == 404
    assert client.post("/api/connections/metatrader").status_code == 404
    assert client.get("/api/mt4/bridge/status").status_code == 404
    assert client.get("/api/mt4/orders").status_code == 404
    assert client.get("/api/mt4/auto").status_code == 404
