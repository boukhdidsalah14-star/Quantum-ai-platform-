import pytest

from app.signals import analyze_candles


def make_candles(values, volume=100):
    return [
        {"open": value - 0.1, "high": value + 0.2, "low": value - 0.2,
         "close": value, "volume": volume}
        for value in values
    ]


def test_signal_requires_at_least_50_candles():
    with pytest.raises(ValueError, match="50 completed candles"):
        analyze_candles(make_candles([100 + i for i in range(40)]), "15m")


def test_signal_returns_multifactor_metrics_and_never_executes():
    values = [100 + i * 0.05 + (0.08 if i % 2 else -0.02) for i in range(80)]
    result = analyze_candles(make_candles(values), "15m")
    assert result["direction"] in {"CALL", "PUT", "WAIT"}
    assert result["trend"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert result["execution_enabled"] is False
    assert result["candle_count"] == 80
    assert "adx_14" in result and "atr_14" in result
    assert "macd" in result and "bollinger_upper" in result
    assert isinstance(result["reasons"], list)


def test_overbought_market_does_not_issue_unconditional_call():
    result = analyze_candles(make_candles([100 + i * 2 for i in range(80)]), "1h")
    assert result["direction"] != "CALL"


def test_flat_market_is_filtered_to_wait():
    result = analyze_candles(make_candles([100 for _ in range(80)]), "5m")
    assert result["direction"] == "WAIT"
    assert result["trend"] == "NEUTRAL"


def test_invalid_ohlc_is_rejected():
    candles = make_candles([100 + i * 0.1 for i in range(60)])
    candles[-1]["high"] = 1
    with pytest.raises(ValueError, match="Invalid candle high"):
        analyze_candles(candles, "15m")
