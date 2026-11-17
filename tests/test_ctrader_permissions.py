import pytest
from app.auth import create_customer, init_auth_db
from app import ctrader_permissions as permissions

def setup(monkeypatch,tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH",str(tmp_path/"permissions.sqlite3"))
    init_auth_db()
    permissions.init_db()
    return create_customer("permission@example.com","strong-password")

def test_demo_permission_requires_explicit_acknowledgement(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match="acknowledge"):
        permissions.set_demo_permission(c["id"],"12345",True,False)
    state=permissions.set_demo_permission(c["id"],"12345",True,True)
    assert state["demo_trading_authorized"] is True
    permissions.require_demo_permission(c["id"],"12345")

def test_demo_permission_is_customer_and_account_isolated(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    other=create_customer("other-permission@example.com","strong-password")
    permissions.set_demo_permission(c["id"],"12345",True,True)
    with pytest.raises(permissions.CTraderPermissionError):
        permissions.require_demo_permission(other["id"],"12345")
    with pytest.raises(permissions.CTraderPermissionError):
        permissions.require_demo_permission(c["id"],"99999")
    assert permissions.get_permission(c["id"],"12345")["live_trading_available"] is False

def test_demo_permission_can_be_revoked(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    permissions.set_demo_permission(c["id"],"12345",True,True)
    permissions.set_demo_permission(c["id"],"12345",False,False)
    with pytest.raises(permissions.CTraderPermissionError):
        permissions.require_demo_permission(c["id"],"12345")
