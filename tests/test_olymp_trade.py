import pytest

from app.olymp_trade import analyze_signal, capabilities


def test_olymp_trade_capabilities_never_claim_live_connection_or_execution():
    result = capabilities()
    assert result["signal_analysis"] is True
    assert result["paper_execution"] is True
    assert result["market_data_connected"] is False
    assert result["account_connected"] is False
    assert result["demo_order_execution"] is False
    assert result["real_order_execution"] is False
    assert result["official_order_api_verified"] is False


def test_olymp_trade_signal_requires_supported_timeframe():
    with pytest.raises(ValueError, match="timeframe"):
        analyze_signal([], "3m")


def test_olymp_trade_signal_marks_execution_disabled():
    candles = []
    price = 100.0
    for i in range(40):
        close = price + i * 0.2
        candles.append({
            "time": i,
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
        })
    result = analyze_signal(candles, "5m")
    assert result["broker"] == "olymp_trade"
    assert result["execution_mode"] == "signal_only"
    assert result["execution_enabled"] is False
    assert result["broker_connection"] == "not_connected"
