import pytest

from app.auth import create_customer, init_auth_db
from app.mt4_bridge import (
    BridgeAuthError,
    bridge_status,
    command_result,
    enqueue_demo_order,
    init_db,
    pending_commands,
    register_bridge,
    sync_snapshot,
    order_status,
    get_mt4_candles,
    sync_candles,
)


def setup_bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4.sqlite3"))
    init_auth_db()
    init_db()
    customer = create_customer("mt4@example.com", "a-strong-password")
    registered = register_bridge(customer["id"], "12345678", "JustMarkets-Demo2")
    return customer, registered["bridge_token"]


def payload():
    return {
        "account_login": "12345678",
        "account_server": "JustMarkets-Demo2",
        "company": "JustMarkets Ltd",
        "balance": 10000,
        "equity": 9980,
        "currency": "USD",
        "positions": [{
            "ticket": 12345, "symbol": "XAUUSD", "side": "BUY", "lots": 0.01,
            "open_price": 2000.0, "current_price": 2002.0,
            "stop_loss": 1985.0, "take_profit": 2030.0,
            "profit": 2.0, "swap": 0.0, "commission": 0.0,
            "open_time": 1700000000, "magic": 914110,
        }],
        "quotes": {"XAUUSD": {"bid": 2001.9, "ask": 2002.1}},
    }


def test_bridge_token_is_customer_bound_and_only_shown_on_registration(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    assert len(token) > 32
    assert bridge_status(customer["id"])["registered"] is True
    assert bridge_status(customer["id"])["connected"] is False


def test_mt4_sync_stores_positions_and_broker_quotes(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    result = sync_snapshot(token, payload())
    snapshot = bridge_status(customer["id"])
    assert result["connected"] is True
    assert result["positions_received"] == 1
    assert snapshot["connected"] is True
    assert snapshot["positions"][0]["ticket"] == "12345"
    assert snapshot["positions"][0]["symbol"] == "XAUUSD"
    assert snapshot["quotes"]["XAUUSD"]["ask"] == 2002.1


def test_mt4_token_rejects_wrong_server_and_non_justmarkets_company(monkeypatch, tmp_path):
    _, token = setup_bridge(monkeypatch, tmp_path)
    wrong_server = payload()
    wrong_server["account_server"] = "OtherBroker-Demo"
    with pytest.raises(BridgeAuthError, match="server"):
        sync_snapshot(token, wrong_server)
    wrong_company = payload()
    wrong_company["company"] = "Another Broker"
    with pytest.raises(BridgeAuthError, match="JustMarkets"):
        sync_snapshot(token, wrong_company)


def test_mt4_demo_order_queue_requires_durable_storage_and_explicit_switch(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    sync_snapshot(token, payload())
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "false")
    with pytest.raises(PermissionError, match="locked"):
        enqueue_demo_order(customer["id"], "XAUUSD", "BUY", 0.01, 1990, 2020)


def test_mt4_demo_order_is_queued_then_reconciled(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    sync_snapshot(token, payload())
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "true")
    created = enqueue_demo_order(customer["id"], "XAUUSD", "BUY", 0.01, 1990, 2020)
    commands = pending_commands(token, "12345678", "JustMarkets-Demo2", "JustMarkets Ltd")
    assert commands[0]["command_id"] == created["command_id"]
    result = command_result(token, "12345678", "JustMarkets-Demo2", "JustMarkets Ltd",
                            created["command_id"], "executed", 998877, "demo fill")
    assert result["status"] == "executed"
    assert order_status(customer["id"])[0]["broker_ticket"] == 998877


def test_mt4_demo_order_enforces_symbol_size_and_stop_direction(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    sync_snapshot(token, payload())
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "true")
    with pytest.raises(ValueError, match="Unsupported"):
        enqueue_demo_order(customer["id"], "BTCUSDT", "BUY", 0.01, 1900, 2100)
    with pytest.raises(ValueError, match="cannot exceed"):
        enqueue_demo_order(customer["id"], "XAUUSD", "BUY", 0.20, 1990, 2020)
    with pytest.raises(ValueError, match="BUY"):
        enqueue_demo_order(customer["id"], "XAUUSD", "BUY", 0.01, 2010, 2020)


def test_mt4_broker_candles_are_authenticated_and_retrievable(monkeypatch, tmp_path):
    customer, token = setup_bridge(monkeypatch, tmp_path)
    rows = []
    for i in range(60):
        close = 2000 + i * 0.1
        rows.append({
            "time": 1700000000 + i * 900,
            "open": close - 0.05, "high": close + 0.10,
            "low": close - 0.10, "close": close, "volume": 100 + i,
        })
    result = sync_candles(token, {
        "account_login": "12345678", "account_server": "JustMarkets-Demo2",
        "company": "JustMarkets Ltd", "symbol": "XAUUSD",
        "timeframe": "15m", "candles": rows,
    })
    saved = get_mt4_candles(customer["id"], "XAUUSD", "15m")
    assert result["candles_received"] == 60
    assert saved["source"] == "JustMarkets MT4 broker candles"
    assert saved["candles"][0]["time"] == rows[0]["time"]


def test_mt4_broker_candles_reject_unapproved_symbols_and_bad_ohlc(monkeypatch, tmp_path):
    _, token = setup_bridge(monkeypatch, tmp_path)
    rows = [{"time": 1700000000 + i * 900, "open": 1.1, "high": 1.2,
             "low": 1.0, "close": 1.15, "volume": 10} for i in range(60)]
    with pytest.raises(ValueError, match="symbol"):
        sync_candles(token, {
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "symbol": "BTCUSDT",
            "timeframe": "15m", "candles": rows,
        })
    rows[-1]["high"] = 0.5
    with pytest.raises(ValueError, match="high"):
        sync_candles(token, {
            "account_login": "12345678", "account_server": "JustMarkets-Demo2",
            "company": "JustMarkets Ltd", "symbol": "EURUSD",
            "timeframe": "15m", "candles": rows,
        })
