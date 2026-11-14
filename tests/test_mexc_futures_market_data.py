import asyncio

import pytest

from app import mexc_futures_market_data as market


def test_market_overview_maps_only_allowed_perpetual_symbols(monkeypatch):
    async def fake_get_json(path, params=None):
        assert path == "ticker"
        return {"success": True, "data": [
            {"symbol": "BTC_USDT", "lastPrice": 65000, "riseFallRate": 0.012,
             "high24Price": 66000, "lower24Price": 64000, "volume24": 123,
             "fundingRate": 0.0001, "holdVol": 456},
            {"symbol": "USDC_USDT", "lastPrice": 1},
        ]}

    monkeypatch.setattr(market, "_get_json", fake_get_json)
    rows = asyncio.run(market.get_market_overview())
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["change_percent"] == "1.2"
    assert rows[0]["funding_rate"] == "0.0001"


def test_candles_convert_mexc_contract_ohlcv(monkeypatch):
    async def fake_get_json(path, params=None):
        assert path == "kline/BTC_USDT"
        assert params["interval"] == "Min60"
        return {"success": True, "data": {
            "time": [1700000000, 1700003600],
            "open": [10, 11], "high": [12, 13], "low": [9, 10],
            "close": [11, 12], "vol": [100, 200],
        }}

    monkeypatch.setattr(market, "_get_json", fake_get_json)
    rows = asyncio.run(market.get_candles("BTCUSDT", "1h", 50))
    assert len(rows) == 2
    assert rows[0] == {
        "time": 1700000000000, "open": 10.0, "high": 12.0,
        "low": 9.0, "close": 11.0, "volume": 100.0,
    }


def test_rejects_symbols_and_intervals_outside_futures_watchlist():
    with pytest.raises(ValueError, match="Unsupported crypto futures symbol"):
        asyncio.run(market.get_candles("USDCUSDT", "1h"))
    with pytest.raises(ValueError, match="Unsupported crypto futures interval"):
        asyncio.run(market.get_candles("BTCUSDT", "2m"))
