"""Public Yahoo Finance candle adapter for Forex analysis only.

This module supplies read-only market data. It does not connect to or place orders
with any broker.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

SYMBOLS = {
    "frxEURUSD": "EURUSD=X",
    "frxGBPUSD": "GBPUSD=X",
    "frxUSDJPY": "JPY=X",
    "frxAUDUSD": "AUDUSD=X",
    "frxUSDCAD": "CAD=X",
    "frxUSDCHF": "CHF=X",
    "frxNZDUSD": "NZDUSD=X",
    "frxEURJPY": "EURJPY=X",
    "frxGBPJPY": "GBPJPY=X",
    "frxXAUUSD": "XAUUSD=X",
}
LABELS = {
    "frxEURUSD": "EUR/USD", "frxGBPUSD": "GBP/USD",
    "frxUSDJPY": "USD/JPY", "frxAUDUSD": "AUD/USD",
    "frxUSDCAD": "USD/CAD", "frxUSDCHF": "USD/CHF",
    "frxNZDUSD": "NZD/USD", "frxEURJPY": "EUR/JPY",
    "frxGBPJPY": "GBP/JPY", "frxXAUUSD": "XAU/USD",
}
GRANULARITY = {60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h", 14400: "1h", 86400: "1d"}
RANGES = {"1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo", "1h": "3mo", "1d": "1y"}


async def _fetch(symbol: str, interval: str, range_: str) -> list[dict[str, Any]]:
    ticker = SYMBOLS.get(symbol)
    if not ticker:
        raise ValueError("Unsupported Forex symbol")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
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
        raise httpx.HTTPError(f"No public candles returned for {symbol}")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    candles = []
    for i, stamp in enumerate(timestamps):
        values = {key: (quote.get(key) or [None] * len(timestamps))[i] for key in ("open", "high", "low", "close", "volume")}
        if any(values[k] is None for k in ("open", "high", "low", "close")):
            continue
        candles.append({
            "time": int(stamp) * 1000,
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": float(values["volume"] or 0),
        })
    return candles


async def get_candles(symbol: str, granularity: int = 900, count: int = 100) -> list[dict[str, Any]]:
    if granularity not in GRANULARITY:
        raise ValueError("Unsupported Forex candle interval")
    interval = GRANULARITY[granularity]
    candles = await _fetch(symbol, interval, RANGES[interval])
    if granularity == 14400:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for candle in candles:
            bucket = (candle["time"] // 1000 // 14400) * 14400
            grouped.setdefault(bucket, []).append(candle)
        candles = [{
            "time": bucket * 1000,
            "open": rows[0]["open"],
            "high": max(row["high"] for row in rows),
            "low": min(row["low"] for row in rows),
            "close": rows[-1]["close"],
            "volume": sum(row["volume"] for row in rows),
        } for bucket, rows in sorted(grouped.items())]
    return candles[-max(20, min(int(count), 200)):]


async def get_market_overview() -> list[dict[str, Any]]:
    async def one(symbol: str) -> dict[str, Any]:
        try:
            candles = await get_candles(symbol, 900, 2)
            last = candles[-1] if candles else {}
            return {
                "symbol": symbol,
                "display_name": LABELS[symbol],
                "price": last.get("close"),
                "is_suspended": not bool(last),
            }
        except (ValueError, httpx.HTTPError):
            return {
                "symbol": symbol,
                "display_name": LABELS[symbol],
                "price": None,
                "is_suspended": True,
            }
    return await asyncio.gather(*(one(symbol) for symbol in SYMBOLS))
