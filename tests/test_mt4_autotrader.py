import pytest

from app.auth import create_customer, init_auth_db
from app.mt4_bridge import init_db as init_bridge_db, register_bridge, sync_snapshot
from app.mt4_autotrader import (
    get_settings,
    init_db,
    process_active_auto_traders,
    start_auto_trader,
    stop_auto_trader,
)


def setup_auto(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "mt4-auto.sqlite3"))
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "true")
    init_auth_db()
    init_bridge_db()
    init_db()
    customer = create_customer("auto@example.com", "a-strong-password")
    registration = register_bridge(customer["id"], "12345678", "JustMarkets-Demo2")
    sync_snapshot(registration["bridge_token"], {
        "account_login": "12345678",
        "account_server": "JustMarkets-Demo2",
        "company": "JustMarkets Ltd",
        "balance": 10000,
        "equity": 10000,
        "currency": "USD",
        "positions": [],
        "quotes": {"XAUUSD": {"bid": 2000.0, "ask": 2000.2}},
    })
    return customer


def test_auto_trader_requires_demo_execution_switch(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    monkeypatch.setenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "false")
    with pytest.raises(PermissionError, match="locked"):
        start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01)


def test_auto_trader_validates_lots_and_drawdown(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="lot size"):
        start_auto_trader(customer["id"], "XAUUSD", "15m", 0.20)
    with pytest.raises(ValueError, match="drawdown"):
        start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01, max_drawdown_pct=15)


def test_auto_trader_queues_one_demo_order_per_completed_candle(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01)
    candles = [
        {"time": 1700000000 + i * 900, "open": 2000.0, "high": 2001.0,
         "low": 1999.0, "close": 2000.5, "volume": 100}
        for i in range(60)
    ]
    monkeypatch.setattr("app.mt4_autotrader.get_mt4_candles",
                        lambda *args: {"candles": candles})
    monkeypatch.setattr("app.signals.analyze_candles", lambda *args: {
        "direction": "CALL", "signal_strength": "moderate", "atr_14": 1.0
    })
    queued = []
    monkeypatch.setattr("app.mt4_autotrader.enqueue_demo_order",
                        lambda *args, **kwargs: queued.append(kwargs["command_id"]) or {
                            "command_id": kwargs["command_id"], "status": "pending"
                        })

    process_active_auto_traders()
    process_active_auto_traders()

    assert len(queued) == 1
    status = get_settings(customer["id"])
    assert status["active"] is True
    assert status["last_signal"] == "CALL"
    assert status["last_command_id"] == queued[0]
    assert len("QAI:" + queued[0]) <= 31  # MT4 order comments are limited to 31 characters.
    assert status["last_candle_time"] == candles[-1]["time"]


def test_auto_trader_stops_at_customer_drawdown_limit(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01, max_drawdown_pct=5)
    from app.mt4_bridge import bridge_status
    # Update the persisted MT4 account snapshot to reflect a 6% equity drawdown.
    from app.mt4_bridge import _connect, _now
    with _connect() as db:
        db.execute("UPDATE mt4_bridge_accounts SET equity=9400, updated_at=? WHERE customer_id=?",
                   (_now(), customer["id"]))
    monkeypatch.setattr("app.mt4_autotrader.get_mt4_candles",
                        lambda *args: {"candles": [{"time": 1700000000 + i * 900,
                         "open": 2000, "high": 2001, "low": 1999, "close": 2000}
                         for i in range(60)]})
    process_active_auto_traders()
    status = get_settings(customer["id"])
    assert status["active"] is False
    assert status["last_signal"] == "STOP"
    assert "drawdown limit" in status["last_message"].lower()


def test_auto_trader_can_be_stopped_by_customer(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01)
    stopped = stop_auto_trader(customer["id"])
    assert stopped["active"] is False
    assert "stopped" in stopped["last_message"].lower()


def test_stop_cancels_pending_auto_commands_but_preserves_manual_commands(monkeypatch, tmp_path):
    customer = setup_auto(monkeypatch, tmp_path)
    start_auto_trader(customer["id"], "XAUUSD", "15m", 0.01)
    from app.mt4_bridge import _connect, _now
    with _connect() as db:
        for command_id in ("qai_a_pending1", "qai_manual1"):
            db.execute("""
                INSERT INTO mt4_bridge_commands
                    (command_id, customer_id, symbol, side, lots, stop_loss,
                     take_profit, status, created_at, updated_at)
                VALUES (?, ?, 'XAUUSD', 'BUY', 0.01, 1998, 2004, 'pending', ?, ?)
            """, (command_id, customer["id"], _now(), _now()))
    stop_auto_trader(customer["id"])
    with _connect() as db:
        auto = db.execute("SELECT status FROM mt4_bridge_commands WHERE command_id='qai_a_pending1'").fetchone()
        manual = db.execute("SELECT status FROM mt4_bridge_commands WHERE command_id='qai_manual1'").fetchone()
    assert auto["status"] == "cancelled"
    assert manual["status"] == "pending"
