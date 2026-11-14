from app.market_data import ALLOWED_INTERVALS, ALLOWED_SYMBOLS
from app.market_universe import BINARY_PAIRS, CRYPTO_FUTURES, FOREX_PAIRS


def test_forex_universe_contains_ten_requested_markets():
    assert len(FOREX_PAIRS) == 10
    assert "frxXAUUSD" in {item["symbol"] for item in FOREX_PAIRS}
    assert "frxGBPJPY" in {item["symbol"] for item in FOREX_PAIRS}


def test_binary_universe_contains_eight_selected_pairs():
    assert len(BINARY_PAIRS) == 8
    assert "frxGBPJPY" in {item["symbol"] for item in BINARY_PAIRS}
    assert "frxNZDUSD" not in {item["symbol"] for item in BINARY_PAIRS}


def test_crypto_futures_universe_excludes_stablecoin_base_assets():
    assert len(CRYPTO_FUTURES) == 10
    assert set(CRYPTO_FUTURES) == ALLOWED_SYMBOLS
    assert all(symbol.endswith("USDT") for symbol in CRYPTO_FUTURES)
    assert not any(symbol in {"USDTUSDT", "USDCUSDT", "BUSDUSDT", "DAIUSDT"} for symbol in CRYPTO_FUTURES)


def test_crypto_futures_timeframes_cover_chart_and_analysis():
    assert {"5m", "15m", "30m", "1h", "4h", "1d"} <= ALLOWED_INTERVALS
