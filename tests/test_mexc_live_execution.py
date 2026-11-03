import pytest

from app.mexc_live_execution import (
    MexcExecutionError,
    _amount,
    _enabled,
    place_market_order,
)


def test_mexc_live_gate_is_off_by_default(monkeypatch):
    monkeypatch.delenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", raising=False)
    assert _enabled() is False


def test_mexc_order_requires_server_gate_and_customer_consent(monkeypatch):
    monkeypatch.delenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", raising=False)
    with pytest.raises(MexcExecutionError, match="locked"):
        import asyncio
        asyncio.run(place_market_order(
            "key", "secret", symbol="BTCUSDT", side="BUY",
            quote_amount_usdt="1", customer_live_consent=True,
            idempotency_key="test-order-1",
        ))


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_mexc_amount_rejects_non_positive_or_non_finite(value):
    with pytest.raises(ValueError):
        _amount(value)


def test_mexc_amount_accepts_decimal_string():
    assert _amount("1.25") == 1.25
