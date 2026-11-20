import pytest

from app.auth import create_customer, init_auth_db
from app.mexc_live_permissions import (
    init_db, get_live_authorization, set_live_authorization,
    activate_emergency_stop, require_live_authorization,
)


def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "live-permissions.sqlite3"))
    init_auth_db()
    init_db()
    return create_customer("mexc-live@example.com", "strong-password")


def test_mexc_live_trading_requires_explicit_consent(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    state = get_live_authorization(customer["id"], "fingerprint-v1")
    assert state["authorized"] is False
    with pytest.raises(PermissionError):
        require_live_authorization(customer["id"], "fingerprint-v1")


def test_mexc_live_consent_is_bound_to_credential_version(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    state = set_live_authorization(customer["id"], "fingerprint-v1", True, True, 2.0)
    assert state["authorized"] is True
    require_live_authorization(customer["id"], "fingerprint-v1")
    assert get_live_authorization(customer["id"], "fingerprint-v2")["authorized"] is False


def test_mexc_live_consent_requires_risk_acknowledgement(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="acknowledgement"):
        set_live_authorization(customer["id"], "fingerprint-v1", True, False, 2.0)


@pytest.mark.parametrize("limit", [0, 10.01, float("nan"), float("inf")])
def test_mexc_live_daily_loss_limit_is_bounded(monkeypatch, tmp_path, limit):
    customer = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="between 1% and 10%"):
        set_live_authorization(customer["id"], "fingerprint-v1", True, True, limit)


def test_mexc_emergency_stop_revokes_live_authorization(monkeypatch, tmp_path):
    customer = setup(monkeypatch, tmp_path)
    set_live_authorization(customer["id"], "fingerprint-v1", True, True, 2.0)
    state = activate_emergency_stop(customer["id"])
    assert state["authorized"] is False
    assert state["emergency_stop"] is True
    with pytest.raises(PermissionError):
        require_live_authorization(customer["id"], "fingerprint-v1")
