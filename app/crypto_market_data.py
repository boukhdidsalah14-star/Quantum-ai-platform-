"""Read-only public crypto market data sourced independently of trading venues."""
from __future__ import annotations

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
ALLOWED_SYMBOLS = set(ASSETS)
ALLOWED_INTERVALS = {"1h", "4h", "1d"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 25.0


async def _get(path: str, params: dict[str, str]) -> Any:
    key = path + repr(sorted(params.items()))
    cached = _CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=5.0),
        headers={"User-Agent": "QUANTUM-AI/1.0"},
    ) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        data = response.json()
    _CACHE[key] = (now, data)
    return data


async def get_market_overview() -> list[dict[str, Any]]:
    ids = ",".join(ASSETS.values())
    rows = await _get("coins/markets", {
        "vs_currency": "usd",
        "ids": ids,
        "price_change_percentage": "24h",
        "per_page": "100",
        "page": "1",
    })
    by_id = {row.get("id"): row for row in rows}
    result = []
    for symbol, coin_id in ASSETS.items():
        row = by_id.get(coin_id, {})
        result.append({
            "symbol": symbol,
            "price": row.get("current_price"),
            "change_percent": row.get("price_change_percentage_24h"),
            "high": row.get("high_24h"),
            "low": row.get("low_24h"),
            "volume": row.get("total_volume"),
            "name": row.get("name", symbol.removesuffix("USDT")),
        })
    return result


async def get_candles(symbol: str, interval: str = "1h", limit: int = 100) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    if symbol not in ASSETS:
        raise ValueError("Unsupported crypto asset")
    if interval not in {"1h", "4h", "1d"}:
        raise ValueError("Crypto interval must be 1h, 4h, or 1d")
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
    return candles[-max(20, min(int(limit), 200)):]
