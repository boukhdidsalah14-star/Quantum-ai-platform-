import pytest

from app.risk import evaluate_demo_risk, validate_demo_quote


def test_demo_quote_risk_policy_accepts_user_stake_and_expiries():
    assert validate_demo_quote(1, 5) == (1.0, 5)
    assert validate_demo_quote(2, 10) == (2.0, 10)


@pytest.mark.parametrize("stake", [0, -1, 2.01, float("nan"), float("inf")])
def test_demo_quote_risk_policy_rejects_unsafe_stakes(stake):
    with pytest.raises(ValueError):
        validate_demo_quote(stake, 5)


def test_demo_quote_risk_policy_rejects_unapproved_expiry():
    with pytest.raises(ValueError):
        validate_demo_quote(1, 7)


def test_demo_risk_pauses_at_loss_streak_or_open_position():
    state = evaluate_demo_risk(25, 3, 1)
    assert state["trading_paused"] is True
    assert len(state["pause_reasons"]) == 3
    assert state["real_trading_enabled"] is False


def test_demo_risk_allows_when_below_limits():
    state = evaluate_demo_risk(2, 1, 0)
    assert state["trading_paused"] is False
    assert state["default_stake_usd"] == 1.0
    assert state["max_stake_usd"] == 2.0
