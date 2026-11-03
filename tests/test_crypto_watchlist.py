from app.market_data import ALLOWED_SYMBOLS as BINANCE_SYMBOLS
from app.mexc_market_data import ALLOWED_SYMBOLS as MEXC_SYMBOLS


def test_supported_crypto_watchlist_is_available_on_both_public_feeds():
    expected = {
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
        "DOTUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "NEARUSDT",
        "UNIUSDT", "ETCUSDT", "FILUSDT", "APTUSDT", "ARBUSDT",
    }
    assert expected <= BINANCE_SYMBOLS
    assert expected <= MEXC_SYMBOLS
