"""Read-only public MEXC USDT-margined perpetual futures market data.

Uses the current Futures API host (api.mexc.com), not the Spot API.
No account credentials or order endpoints are used here.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.mexc.com/api/v1/contract"
ALLOWED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
    "TRXUSDT", "DOGEUSDT", "ADAUSDT", "BCHUSDT", "LINKUSDT",
}
ALLOWED_INTERVALS = {"5m", "15m", "30m", "1h", "4h", "1d"}
_INTERVALS = {
    "5m": ("Min5", 300), "15m": ("Min15", 900),
    "30m": ("Min30", 1800), "1h": ("Min60", 3600),
    "4h": ("Hour4", 14400), "1d": ("Day1", 86400),
}
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 8.0


def _contract_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported crypto futures symbol")
    return normalized[:-4] + "_USDT"


async def _get_json(path: str, params: dict[str, str] | None = None) -> Any:
    key = path + repr(sorted((params or {}).items()))
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0),
        headers={"User-Agent": "QuantumAI/0.5"},
    ) as client:
        response = await client.get(f"{BASE_URL}/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("success") is not True:
        message = payload.get("message", "MEXC Futures returned an invalid response") if isinstance(payload, dict) else "MEXC Futures returned an invalid response"
        raise httpx.HTTPError(str(message))
    _CACHE[key] = (now, payload)
    return payload


async def get_market_overview() -> list[dict[str, Any]]:
    payload = await _get_json("ticker")
    rows = payload.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    result = []
    for row in rows:
        symbol = str(row.get("symbol", "")).replace("_", "")
        if symbol not in ALLOWED_SYMBOLS:
            continue
        result.append({
            "symbol": symbol,
            "price": str(row.get("lastPrice", "")),
            "change_percent": str(float(row.get("riseFallRate", 0)) * 100),
            "high": str(row.get("high24Price", "")),
            "low": str(row.get("lower24Price", "")),
            "volume": str(row.get("volume24", "")),
            "funding_rate": str(row.get("fundingRate", "")),
            "open_interest": str(row.get("holdVol", "")),
            "source": "MEXC USDT-margined perpetual futures",
        })
    return result


async def get_candles(symbol: str, interval: str, limit: int = 72) -> list[dict[str, Any]]:
    contract = _contract_symbol(symbol)
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("Unsupported crypto futures interval")
    bounded_limit = max(50, min(int(limit), 200))
    mexc_interval, seconds = _INTERVALS[interval]
    end = int(time.time())
    start = end - seconds * bounded_limit
    payload = await _get_json(
        f"kline/{contract}",
        {"interval": mexc_interval, "start": str(start), "end": str(end)},
    )
    data = payload.get("data") or {}
    times = data.get("time") or []
    fields = ("open", "high", "low", "close", "vol")
    arrays = {name: data.get(name) or [] for name in fields}
    rows = []
    for index, timestamp in enumerate(times):
        if any(index >= len(arrays[name]) for name in fields):
            continue
        rows.append({
            "time": int(timestamp) * 1000,
            "open": float(arrays["open"][index]),
            "high": float(arrays["high"][index]),
            "low": float(arrays["low"][index]),
            "close": float(arrays["close"][index]),
            "volume": float(arrays["vol"][index]),
        })
    if not rows:
        raise httpx.HTTPError("MEXC Futures returned no candle data")
    return rows[-bounded_limit:]
