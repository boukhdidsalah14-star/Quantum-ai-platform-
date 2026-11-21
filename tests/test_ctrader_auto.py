import pytest

from app.auth import create_customer, init_auth_db
from app.ctrader_permissions import (
    init_db as init_permissions_db, set_demo_permission,
    CTraderPermissionError,
)
from app import ctrader_auto


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "ctrader-auto.sqlite3"))
    init_auth_db()
    init_permissions_db()
    ctrader_auto.init_db()
    return create_customer("auto-forex@example.com", "strong-password")


def test_demo_strategy_requires_account_permission_and_persists(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    with pytest.raises(CTraderPermissionError):
        ctrader_auto.start_strategy(customer["id"], "12345", "demo", ["EURUSD"], "15m", 0.001)
    set_demo_permission(customer["id"], "12345", True, True)
    strategy = ctrader_auto.start_strategy(
        customer["id"], "12345", "demo", ["EURUSD", "GBPUSD"], "15m", 0.001
    )
    assert strategy["enabled"] is True
    assert strategy["symbols"] == ["EURUSD", "GBPUSD"]
    assert strategy["environment"] == "demo"
    assert ctrader_auto.list_active_strategies()[0]["customer_id"] == customer["id"]


def test_live_strategy_is_disabled_in_demo_first_release(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("QUANTUM_CTRADER_LIVE_SESSION_ENABLED", "true")
    monkeypatch.setenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", "true")
    with pytest.raises(ValueError, match="Only cTrader demo automation is available"):
        ctrader_auto.start_strategy(
            customer["id"], "54321", "live", ["EURUSD"], "15m", 0.001
        )


def test_strategy_rejects_unsafe_configuration(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_demo_permission(customer["id"], "12345", True, True)
    with pytest.raises(ValueError):
        ctrader_auto.start_strategy(customer["id"], "12345", "demo", ["EURUSD"], "1m", 0.001)
    with pytest.raises(ValueError):
        ctrader_auto.start_strategy(customer["id"], "12345", "demo", ["EURUSD"], "15m", 0.02)
    with pytest.raises(ValueError):
        ctrader_auto.start_strategy(customer["id"], "12345", "demo", [], "15m", 0.001)


def test_strategy_accepts_up_to_twenty_broker_symbols(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_demo_permission(customer["id"], "12345", True, True)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
               "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "XAUUSD",
               "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BCHUSD",
               "ADAUSD", "SOLUSD", "DOGEUSD", "DOTUSD", "LINKUSD"]
    strategy = ctrader_auto.start_strategy(
        customer["id"], "12345", "demo", symbols, "15m", 0.001
    )
    assert len(strategy["symbols"]) == 20


def test_strategy_stop_disables_new_entries(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_demo_permission(customer["id"], "12345", True, True)
    ctrader_auto.start_strategy(customer["id"], "12345", "demo", ["EURUSD"], "15m", 0.001)
    stopped = ctrader_auto.stop_strategy(customer["id"], "12345", "demo")
    assert stopped["enabled"] is False
    assert ctrader_auto.list_active_strategies() == []
