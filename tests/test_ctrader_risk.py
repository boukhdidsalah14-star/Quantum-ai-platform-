import pytest
from app.auth import create_customer, init_auth_db
from app import ctrader_risk

def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "risk.sqlite3"))
    init_auth_db()
    ctrader_risk.init_db()
    return create_customer("risk@example.com", "strong-password")

def test_defaults_and_settings_are_bounded(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    s=ctrader_risk.get_settings(c["id"])
    assert s["max_daily_loss_pct"] == 10.0 and s["max_lots"] == .01
    assert s["max_open_positions"] == 3 and not s["emergency_stop"]
    s=ctrader_risk.update_settings(c["id"],5,.005,2)
    assert s["max_daily_loss_pct"] == 5 and s["max_lots"] == .005
    with pytest.raises(ValueError): ctrader_risk.update_settings(c["id"],11,.005,2)
    with pytest.raises(ValueError): ctrader_risk.update_settings(c["id"],5,.02,2)

def test_daily_loss_limit_blocks_entries(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    ctrader_risk.record_account_sync(c["id"],"123",1000)
    ctrader_risk.record_account_sync(c["id"],"123",900)
    with pytest.raises(ctrader_risk.CTraderRiskBlocked,match="Daily loss limit"):
        ctrader_risk.reserve_entry(c["id"],"123",900,0,.01)

def test_emergency_stop_blocks_and_can_be_released(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    ctrader_risk.record_account_sync(c["id"],"123",1000)
    ctrader_risk.set_emergency_stop(c["id"],True)
    with pytest.raises(ctrader_risk.CTraderRiskBlocked,match="Emergency stop"):
        ctrader_risk.reserve_entry(c["id"],"123",1000,0,.01)
    ctrader_risk.set_emergency_stop(c["id"],False)
    token=ctrader_risk.reserve_entry(c["id"],"123",1000,0,.01)
    ctrader_risk.release_entry(token)

def test_max_positions_reservations_and_customer_isolation(monkeypatch,tmp_path):
    c=setup(monkeypatch,tmp_path)
    other=create_customer("other@example.com","strong-password")
    ctrader_risk.update_settings(c["id"],10,.01,1)
    ctrader_risk.record_account_sync(c["id"],"123",1000)
    token=ctrader_risk.reserve_entry(c["id"],"123",1000,0,.01)
    with pytest.raises(ctrader_risk.CTraderRiskBlocked,match="Maximum"):
        ctrader_risk.reserve_entry(c["id"],"123",1000,0,.01)
    ctrader_risk.release_entry(token)
    assert ctrader_risk.get_settings(other["id"])["max_daily_loss_pct"] == 10
