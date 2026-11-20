from app.forex_market_data import completed_candles


def test_completed_candles_excludes_newest_potentially_forming_bar():
    candles = [{"time": i, "close": 100 + i} for i in range(3)]
    assert completed_candles(candles) == candles[:-1]
    assert len(candles) == 3


def test_completed_candles_requires_at_least_two_bars():
    assert completed_candles([]) == []
    assert completed_candles([{"time": 1}]) == []
