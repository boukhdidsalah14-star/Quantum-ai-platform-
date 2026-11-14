import pytest

from app.crypto_futures_paper import build_paper_trade_plan


def sample(**overrides):
    data = {
        "trade_bias": "LONG",
        "signal_strength": "high",
        "last_close": 100.0,
        "atr_14": 2.0,
    }
    data.update(overrides)
    return data


def test_long_plan_has_atr_stop_two_to_one_target_and_one_x_cap():
    plan = build_paper_trade_plan(sample(), account_balance=1000)
    assert plan["side"] == "long"
    assert plan["stop_loss"] == 97.0
    assert plan["take_profit"] == 106.0
    assert plan["risk_reward_ratio"] == 2.0
    assert plan["leverage"] == 1
    assert plan["margin_required_usdt"] == pytest.approx(plan["notional_usdt"])
    assert plan["execution"] == "simulated_only"
    assert plan["broker_order_sent"] is False
    assert plan["notional_usdt"] <= 500.0


def test_short_plan_reverses_stop_and_target():
    plan = build_paper_trade_plan(sample(trade_bias="SHORT"), account_balance=1000)
    assert plan["side"] == "short"
    assert plan["stop_loss"] > plan["entry_price"]
    assert plan["take_profit"] < plan["entry_price"]


def test_wait_or_non_high_quality_signal_does_not_create_plan():
    assert build_paper_trade_plan(sample(trade_bias="WAIT"), account_balance=1000) is None
    assert build_paper_trade_plan(sample(signal_strength="moderate"), account_balance=1000) is None


@pytest.mark.parametrize("risk", [0, -0.1, 1.01, float("nan"), float("inf")])
def test_risk_percent_is_bounded(risk):
    with pytest.raises(ValueError):
        build_paper_trade_plan(sample(), account_balance=1000, risk_percent=risk)


def test_bad_prices_and_atr_are_rejected():
    with pytest.raises(ValueError):
        build_paper_trade_plan(sample(last_close=0), account_balance=1000)
    with pytest.raises(ValueError):
        build_paper_trade_plan(sample(atr_14=-1), account_balance=1000)


@pytest.mark.parametrize("leverage", [1, 2, 5, 10, 20])
def test_client_leverage_changes_margin_not_stop_risk(leverage):
    plan = build_paper_trade_plan(sample(), account_balance=1000, leverage=leverage)
    assert plan["leverage"] == leverage
    assert plan["margin_required_usdt"] == pytest.approx(plan["notional_usdt"] / leverage)
    assert plan["risk_budget_usdt"] == pytest.approx(5.0)
    assert plan["stop_loss"] == 97.0
    assert plan["notional_usdt"] <= 500.0


@pytest.mark.parametrize("leverage", [0, -1, 21, 1.5, float("inf")])
def test_leverage_outside_whole_number_one_to_twenty_is_rejected(leverage):
    with pytest.raises(ValueError):
        build_paper_trade_plan(sample(), account_balance=1000, leverage=leverage)
