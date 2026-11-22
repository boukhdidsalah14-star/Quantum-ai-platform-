from app.crypto_market_data import ALLOWED_INTERVALS, ALLOWED_SYMBOLS
from app.market_universe import BINARY_PAIRS, CRYPTO_ASSETS, FOREX_PAIRS


def test_forex_universe_contains_ten_requested_markets():
    assert len(FOREX_PAIRS) == 10
    assert "frxXAUUSD" in {item["symbol"] for item in FOREX_PAIRS}
    assert "frxGBPJPY" in {item["symbol"] for item in FOREX_PAIRS}


def test_binary_universe_contains_eight_selected_pairs():
    assert len(BINARY_PAIRS) == 8
    assert "frxGBPJPY" in {item["symbol"] for item in BINARY_PAIRS}
    assert "frxNZDUSD" not in {item["symbol"] for item in BINARY_PAIRS}


def test_crypto_asset_universe_excludes_stablecoin_base_assets():
    assert len(CRYPTO_ASSETS) == 10
    assert set(CRYPTO_ASSETS) == ALLOWED_SYMBOLS
    assert all(symbol.endswith("USDT") for symbol in CRYPTO_ASSETS)
    assert not any(symbol in {"USDTUSDT", "USDCUSDT", "BUSDUSDT", "DAIUSDT"} for symbol in CRYPTO_ASSETS)


def test_crypto_asset_timeframes_cover_chart_and_analysis():
    assert {"1h", "4h", "1d"} == ALLOWED_INTERVALS
