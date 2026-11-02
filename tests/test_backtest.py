import pytest

from app.backtest import backtest_candles


def rising_candles(count=100):
    return [
        {"open": 100 + i * 0.02, "high": 100 + i * 0.02 + 0.15,
         "low": 100 + i * 0.02 - 0.15, "close": 100 + i * 0.02}
        for i in range(count)
    ]


def test_backtest_returns_directional_metrics_without_execution():
    result = backtest_candles(rising_candles(), "15m", 1)
    assert result["candles_tested"] == 100
    assert result["signals_tested"] >= 0
    assert result["execution_enabled"] is False
    assert result["directional_accuracy_percent"] is None or 0 <= result["directional_accuracy_percent"] <= 100


def test_backtest_rejects_too_few_candles():
    with pytest.raises(ValueError, match="At least 40"):
        backtest_candles(rising_candles(30), "5m", 1)


@pytest.mark.parametrize("lookahead", [0, 5, -1])
def test_backtest_rejects_invalid_lookahead(lookahead):
    with pytest.raises(ValueError, match="between 1 and 4"):
        backtest_candles(rising_candles(), "15m", lookahead)
