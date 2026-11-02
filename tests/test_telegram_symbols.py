from app.telegram_bot import _infer_market_category, _normalise_deriv_symbol


def test_telegram_accepts_short_forex_pair_names():
    assert _infer_market_category("EURUSD") == "forex"
    assert _normalise_deriv_symbol("EURUSD", "forex") == "frxEURUSD"
    assert _normalise_deriv_symbol("FRXeurusd", "forex") == "frxEURUSD"


def test_telegram_infers_crypto_and_synthetic_symbols():
    assert _infer_market_category("BTCUSDT") == "crypto"
    assert _infer_market_category("R_100") == "synthetic"
    assert _normalise_deriv_symbol("r_100", "synthetic") == "R_100"
