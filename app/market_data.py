"""Read-only Binance USD-M futures public market data adapter."""
from __future__ import annotations
import time
from typing import Any
import httpx

BASE_URL = "https://fapi.binance.com/fapi/v1"
# Read-only public USD-M futures endpoints; no authenticated order endpoints are used.
BASE_URLS = (BASE_URL,)
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "DOGEUSDT", "ADAUSDT", "BCHUSDT", "LINKUSDT"}
ALLOWED_INTERVALS = {"5m", "15m", "30m", "1h", "4h", "1d"}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 8.0

async def _get_json(path: str, params: dict[str, str] | None = None) -> Any:
    key = path + repr(sorted((params or {}).items()))
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    last_error: httpx.HTTPError | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0), headers={"User-Agent": "QuantumAI/0.5"}) as client:
        for base_url in BASE_URLS:
            try:
                response = await client.get(f"{base_url}/{path}", params=params)
                response.raise_for_status()
                payload = response.json()
                _CACHE[key] = (time.monotonic(), payload)
                return payload
            except httpx.HTTPError as exc:
                last_error = exc
    if last_error is not None:
        raise last_error
    raise httpx.HTTPError("No Binance market-data endpoint is available")

async def get_market_overview() -> list[dict[str, Any]]:
    rows = await _get_json("ticker/24hr")
    return [{"symbol": r["symbol"], "price": r["lastPrice"], "change_percent": r["priceChangePercent"], "high": r["highPrice"], "low": r["lowPrice"], "volume": r["volume"]} for r in rows if r.get("symbol") in ALLOWED_SYMBOLS]

async def get_candles(symbol: str, interval: str, limit: int = 72) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported market symbol")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("Unsupported candle interval")
    bounded_limit = max(50, min(int(limit), 200))
    rows = await _get_json("klines", {"symbol": symbol, "interval": interval, "limit": str(bounded_limit)})
    return [{"time": int(r[0]), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]


async def get_order_book(symbol: str, limit: int = 10) -> dict[str, Any]:
    """Return read-only public Binance USD-M futures order-book depth."""
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported market symbol")
    bounded_limit = max(5, min(int(limit), 20))
    payload = await _get_json("depth", {"symbol": symbol, "limit": str(bounded_limit)})
    bids = [[float(price), float(quantity)] for price, quantity in payload.get("bids", [])]
    asks = [[float(price), float(quantity)] for price, quantity in payload.get("asks", [])]
    if not bids or not asks:
        raise httpx.HTTPError("Binance Futures returned an empty order book")
    return {"symbol": symbol, "bids": bids, "asks": asks,
            "last_update_id": payload.get("lastUpdateId"),
            "spread": asks[0][0] - bids[0][0]}
