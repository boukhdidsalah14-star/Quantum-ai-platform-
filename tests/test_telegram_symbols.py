import pytest

from app.telegram_bot import _category, _forex_symbol


def test_market_category_is_limited_to_forex_and_crypto():
    assert _category("BTCUSDT") == "crypto"
    assert _category("EURUSD") == "forex"


def test_forex_symbol_normalization():
    assert _forex_symbol("EURUSD") == "frxEURUSD"
    assert _forex_symbol("frxGBPUSD") == "frxGBPUSD"


def test_unsupported_forex_symbol_is_rejected():
    with pytest.raises(ValueError):
        _forex_symbol("R_100")
