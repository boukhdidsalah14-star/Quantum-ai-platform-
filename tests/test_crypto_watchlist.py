from app.market_data import ALLOWED_SYMBOLS as BINANCE_SYMBOLS
from app.mexc_market_data import ALLOWED_SYMBOLS as MEXC_SYMBOLS


def test_supported_crypto_watchlist_is_available_on_both_public_feeds():
    expected = {
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
        "TRXUSDT", "DOGEUSDT", "ADAUSDT", "BCHUSDT", "LINKUSDT",
    }
    assert expected == BINANCE_SYMBOLS
    assert expected == MEXC_SYMBOLS
