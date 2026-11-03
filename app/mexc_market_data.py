"""Read-only public MEXC Spot market data adapter; no account or order APIs."""
from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.mexc.com/api/v3"
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "NEARUSDT", "UNIUSDT", "ETCUSDT", "FILUSDT", "APTUSDT", "ARBUSDT"}
ALLOWED_INTERVALS = {"1h", "4h", "1d"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 8.0


async def _get_json(path: str, params: dict[str, str] | None = None) -> Any:
    key = path + repr(sorted((params or {}).items()))
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0),
                                 headers={"User-Agent": "QuantumAI/0.5"}) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    _CACHE[key] = (now, payload)
    return payload


async def get_market_overview() -> list[dict[str, Any]]:
    rows = await _get_json("ticker/24hr")
    return [{
        "symbol": row["symbol"],
        "price": row["lastPrice"],
        "change_percent": str(float(row.get("priceChangePercent", 0))),
        "high": row["highPrice"],
        "low": row["lowPrice"],
        "volume": row["volume"],
    } for row in rows if row.get("symbol") in ALLOWED_SYMBOLS]


async def get_candles(symbol: str, interval: str, limit: int = 72) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported MEXC market symbol")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("Unsupported MEXC candle interval")
    bounded_limit = max(20, min(int(limit), 200))
    rows = await _get_json("klines", {
        "symbol": symbol, "interval": interval, "limit": str(bounded_limit)
    })
    return [{
        "time": int(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
    } for row in rows]
