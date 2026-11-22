"""Read-only public crypto market data with resilient Yahoo/CoinGecko providers."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

BASE_URL = "https://api.coingecko.com/api/v3"
ASSETS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "SOLUSDT": "solana",
    "TRXUSDT": "tron",
    "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano",
    "BCHUSDT": "bitcoin-cash",
    "LINKUSDT": "chainlink",
}
YAHOO_TICKERS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "BNBUSDT": "BNB-USD",
    "XRPUSDT": "XRP-USD",
    "SOLUSDT": "SOL-USD",
    "TRXUSDT": "TRX-USD",
    "DOGEUSDT": "DOGE-USD",
    "ADAUSDT": "ADA-USD",
    "BCHUSDT": "BCH-USD",
    "LINKUSDT": "LINK-USD",
}
ALLOWED_SYMBOLS = set(ASSETS)
ALLOWED_INTERVALS = {"1h", "4h", "1d"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 30.0


def _cached(key: str) -> Any | None:
    item = _CACHE.get(key)
    if item and time.monotonic() - item[0] < _CACHE_TTL:
        return item[1]
    return None


def _store(key: str, value: Any) -> Any:
    _CACHE[key] = (time.monotonic(), value)
    return value


async def _get(path: str, params: dict[str, str]) -> Any:
    key = "coingecko:" + path + repr(sorted(params.items()))
    cached = _cached(key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=3.0),
        headers={"User-Agent": "QUANTUM-AI/1.0"},
    ) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        data = response.json()
    return _store(key, data)


async def _yahoo_candles(symbol: str, interval: str, range_: str) -> list[dict[str, Any]]:
    ticker = YAHOO_TICKERS[symbol]
    key = f"yahoo:{ticker}:{interval}:{range_}"
    cached = _cached(key)
    if cached is not None:
        return cached
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=3.0),
        headers={"User-Agent": "Mozilla/5.0 QUANTUM-AI/1.0"},
    ) as client:
        response = await client.get(url, params={"interval": interval, "range": range_})
        response.raise_for_status()
        payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise httpx.HTTPError(str(chart["error"]))
    results = chart.get("result") or []
    if not results:
        raise httpx.HTTPError(f"No Yahoo Finance candles returned for {symbol}")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    candles = []
    for i, stamp in enumerate(timestamps):
        values = {
            name: (quote.get(name) or [None] * len(timestamps))[i]
            for name in ("open", "high", "low", "close", "volume")
        }
        if any(values[name] is None for name in ("open", "high", "low", "close")):
            continue
        candles.append({
            "time": int(stamp) * 1000,
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": float(values["volume"] or 0),
        })
    if not candles:
        raise httpx.HTTPError(f"No usable Yahoo Finance candles returned for {symbol}")
    return _store(key, candles)


def _aggregate(candles: list[dict[str, Any]], seconds: int) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for candle in candles:
        bucket = (int(candle["time"]) // 1000 // seconds) * seconds
        grouped.setdefault(bucket, []).append(candle)
    return [{
        "time": bucket * 1000,
        "open": rows[0]["open"],
        "high": max(row["high"] for row in rows),
        "low": min(row["low"] for row in rows),
        "close": rows[-1]["close"],
        "volume": sum(row["volume"] for row in rows),
    } for bucket, rows in sorted(grouped.items())]


async def get_market_overview() -> list[dict[str, Any]]:
    ids = ",".join(ASSETS.values())
    try:
        rows = await _get("coins/markets", {
            "vs_currency": "usd",
            "ids": ids,
            "price_change_percentage": "24h",
            "per_page": "100",
            "page": "1",
        })
        by_id = {row.get("id"): row for row in rows}
        return [{
            "symbol": symbol,
            "price": by_id.get(coin_id, {}).get("current_price"),
            "change_percent": by_id.get(coin_id, {}).get("price_change_percentage_24h"),
            "high": by_id.get(coin_id, {}).get("high_24h"),
            "low": by_id.get(coin_id, {}).get("low_24h"),
            "volume": by_id.get(coin_id, {}).get("total_volume"),
            "name": by_id.get(coin_id, {}).get("name", symbol.removesuffix("USDT")),
        } for symbol, coin_id in ASSETS.items()]
    except httpx.HTTPError:
        async def one(symbol: str) -> dict[str, Any]:
            try:
                candles = await _yahoo_candles(symbol, "1d", "5d")
                last = candles[-1]
                previous = candles[-2] if len(candles) > 1 else last
                change = ((last["close"] - previous["close"]) / previous["close"] * 100) if previous["close"] else None
                return {
                    "symbol": symbol,
                    "price": last["close"],
                    "change_percent": change,
                    "high": last["high"],
                    "low": last["low"],
                    "volume": last["volume"],
                    "name": symbol.removesuffix("USDT"),
                }
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                return {
                    "symbol": symbol, "price": None, "change_percent": None,
                    "high": None, "low": None, "volume": None,
                    "name": symbol.removesuffix("USDT"),
                }
        result = await asyncio.gather(*(one(symbol) for symbol in ASSETS))
        if not any(item["price"] is not None for item in result):
            raise httpx.HTTPError("Both public crypto market-data providers are unavailable")
        return result


async def get_candles(symbol: str, interval: str = "1h", limit: int = 100) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    if symbol not in ASSETS:
        raise ValueError("Unsupported crypto asset")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("Crypto interval must be 1h, 4h, or 1d")
    try:
        days = {"1h": "1", "4h": "7", "1d": "30"}[interval]
        rows = await _get(f"coins/{ASSETS[symbol]}/ohlc", {
            "vs_currency": "usd",
            "days": days,
        })
        candles = [{
            "time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": 0.0,
        } for row in rows if len(row) >= 5]
        if not candles:
            raise httpx.HTTPError(f"No CoinGecko candles returned for {symbol}")
    except httpx.HTTPError:
        if interval == "1d":
            candles = await _yahoo_candles(symbol, "1d", "3mo")
        else:
            hourly = await _yahoo_candles(symbol, "1h", "1mo" if interval == "1h" else "3mo")
            candles = hourly if interval == "1h" else _aggregate(hourly, 4 * 60 * 60)
    return candles[-max(20, min(int(limit), 200)):]
