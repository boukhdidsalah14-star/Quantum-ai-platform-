import asyncio

import pytest

from app.auth import create_customer, init_auth_db
from app.ctrader_permissions import (
    init_db as init_permissions_db,
    set_demo_permission,
    set_live_permission,
    get_permission,
    require_live_permission,
    CTraderPermissionError,
)
from app import ctrader_open_api as api


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "ctrader-live.sqlite3"))
    init_auth_db()
    init_permissions_db()
    return create_customer("live-forex@example.com", "strong-password")


def test_live_permission_is_separate_from_demo_permission(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_demo_permission(customer["id"], "12345", True, True)
    state = get_permission(customer["id"], "12345")
    assert state["demo_trading_authorized"] is True
    assert state["live_trading_authorized"] is False

    set_live_permission(customer["id"], "12345", True, True)
    state = get_permission(customer["id"], "12345")
    assert state["demo_trading_authorized"] is True
    assert state["live_trading_authorized"] is True
    require_live_permission(customer["id"], "12345")


def test_live_permission_requires_explicit_acknowledgement(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="acknowledge"):
        set_live_permission(customer["id"], "12345", True, False)
    with pytest.raises(CTraderPermissionError, match="not authorized"):
        require_live_permission(customer["id"], "12345")


def test_live_permission_can_be_revoked_without_revoking_demo(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_demo_permission(customer["id"], "12345", True, True)
    set_live_permission(customer["id"], "12345", True, True)
    set_live_permission(customer["id"], "12345", False, False)
    state = get_permission(customer["id"], "12345")
    assert state["demo_trading_authorized"] is True
    assert state["live_trading_authorized"] is False


def test_live_account_discovery_is_locked_without_server_approval(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.delenv("QUANTUM_CTRADER_LIVE_SESSION_ENABLED", raising=False)
    with pytest.raises(api.CTraderOpenAPIError, match="awaiting Spotware approval"):
        asyncio.run(api.discover_live_accounts("customer-id"))


def test_live_orders_are_locked_without_server_enablement(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.delenv("QUANTUM_CTRADER_LIVE_TRADING_ENABLED", raising=False)
    with pytest.raises(api.CTraderOpenAPIError, match="locked pending Spotware approval"):
        asyncio.run(api.open_live_trade("customer-id", "EURUSD", "BUY", 0.001, 1.0, 2.0))
