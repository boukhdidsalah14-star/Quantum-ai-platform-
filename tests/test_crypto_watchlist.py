from app.crypto_market_data import ALLOWED_SYMBOLS
from app.market_universe import CRYPTO_ASSETS


def test_crypto_watchlist_matches_independent_market_feed():
    expected = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "DOGEUSDT", "ADAUSDT", "BCHUSDT", "LINKUSDT"}
    assert set(CRYPTO_ASSETS) == expected
    assert ALLOWED_SYMBOLS == expected
