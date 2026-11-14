import pytest

from app.advanced_signals import analyze_market


def candles(count=100, step=0.2, volatility=0.08):
    rows = []
    price = 100.0
    for i in range(count):
        nxt = price + step
        rows.append({
            "open": price,
            "high": max(price, nxt) + volatility,
            "low": min(price, nxt) - volatility,
            "close": nxt,
            "volume": 1000 + i,
        })
        price = nxt
    return rows


def test_advanced_engine_reports_confluence_not_win_probability():
    result = analyze_market(candles(), "15m", asset="BTCUSDT")
    assert result["asset"] == "BTCUSDT"
    assert result["direction"] in {"CALL", "PUT", "WAIT"}
    assert 0 <= result["confluence_score"] <= 100
    assert result["confidence_is_probability"] is False
    assert result["execution_enabled"] is False
    assert result["market_regime"] in {"TRENDING", "HIGH_VOLATILITY", "RANGING_OR_WEAK_TREND"}


def test_advanced_engine_requires_sufficient_completed_candles():
    with pytest.raises(ValueError, match="30 completed candles"):
        analyze_market(candles(29), "5m")


def test_higher_timeframe_conflict_is_reported():
    rising = candles()
    falling = candles(step=-0.2)
    result = analyze_market(rising, "5m", higher_timeframes={"1h": falling})
    assert result["higher_timeframe_bias"]["1h"] == "BEARISH"
    assert result["direction"] in {"WAIT", "PUT"}


def test_invalid_ohlc_is_rejected():
    bad = candles()
    bad[-1]["high"] = 1
    with pytest.raises(ValueError, match="high is inconsistent"):
        analyze_market(bad, "1m")
