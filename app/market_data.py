"""Read-only public crypto market data adapter."""
from __future__ import annotations
import time
from typing import Any
import httpx

BASE_URL = "https://api.binance.com/api/v3"
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
ALLOWED_INTERVALS = {"1h", "4h", "1d"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 8.0

async def _get_json(path: str, params: dict[str, str] | None = None) -> Any:
    key = path + repr(sorted((params or {}).items()))
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0), headers={"User-Agent": "QuantumAI/0.2"}) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    _CACHE[key] = (now, payload)
    return payload

async def get_market_overview() -> list[dict[str, Any]]:
    rows = await _get_json("ticker/24hr")
    return [{"symbol": r["symbol"], "price": r["lastPrice"], "change_percent": r["priceChangePercent"], "high": r["highPrice"], "low": r["lowPrice"], "volume": r["volume"]} for r in rows if r.get("symbol") in ALLOWED_SYMBOLS]

async def get_candles(symbol: str, interval: str, limit: int = 72) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported market symbol")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("Unsupported candle interval")
    bounded_limit = max(20, min(int(limit), 200))
    rows = await _get_json("klines", {"symbol": symbol, "interval": interval, "limit": str(bounded_limit)})
    return [{"time": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]
