from app.market_data import ALLOWED_SYMBOLS as BINANCE_SYMBOLS
from app.market_universe import CRYPTO_FUTURES
from app.mexc_market_data import ALLOWED_SYMBOLS as MEXC_SYMBOLS


def test_binance_futures_watchlist_has_ten_non_stablecoin_base_assets():
    expected = set(CRYPTO_FUTURES)
    assert len(expected) == 10
    assert BINANCE_SYMBOLS == expected
    stablecoin_bases = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"}
    assert all(symbol.removesuffix("USDT") not in stablecoin_bases for symbol in BINANCE_SYMBOLS)


def test_mexc_spot_adapter_remains_separate_and_explicitly_spot_only():
    assert {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"} <= MEXC_SYMBOLS
