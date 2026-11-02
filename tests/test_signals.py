import pytest

from app.signals import analyze_candles


def make_candles(values):
    return [
        {"open": value - 0.1, "high": value + 0.2, "low": value - 0.2, "close": value}
        for value in values
    ]


def test_signal_waits_when_there_are_too_few_candles():
    with pytest.raises(ValueError, match="30 completed candles"):
        analyze_candles(make_candles([100 + i for i in range(20)]), "15m")


def test_signal_engine_returns_documented_fields_for_rising_market():
    result = analyze_candles(make_candles([100 + i * 0.5 for i in range(60)]), "15m")
    assert result["direction"] in {"CALL", "PUT", "WAIT"}
    assert result["trend"] == "BULLISH"
    assert result["execution_enabled"] is False
    assert result["signal_strength"] in {"low", "moderate"}
    assert result["suggested_expiry_minutes"] == 15
    assert result["candle_count"] == 60
    assert isinstance(result["reasons"], list)


def test_signal_engine_does_not_issue_unconditional_call_on_overbought_market():
    result = analyze_candles(make_candles([100 + i * 2 for i in range(60)]), "1h")
    assert result["direction"] != "CALL"


def test_signal_engine_handles_flat_market_as_wait():
    result = analyze_candles(make_candles([100 for _ in range(60)]), "5m")
    assert result["direction"] == "WAIT"
    assert result["trend"] == "NEUTRAL"
