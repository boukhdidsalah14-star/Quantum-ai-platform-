"""Read-only public Deriv market data for Forex and binary-option underlyings.

Uses Deriv's unauthenticated public WebSocket. This module never sends trade requests.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import websockets

from app.risk import validate_demo_quote

PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
ALLOWED_GRANULARITIES = {60, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400}
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9_]{2,30}$")


class DerivMarketDataError(RuntimeError):
    """Public Deriv market-data request failed."""


async def _request(payload: dict[str, Any], expected_type: str) -> dict[str, Any]:
    try:
        async with websockets.connect(
            PUBLIC_WS, open_timeout=7, close_timeout=2, ping_interval=20,
            ping_timeout=10, max_size=2_000_000,
        ) as ws:
            await ws.send(json.dumps(payload))
            for _ in range(4):
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                message = json.loads(raw)
                if message.get("error"):
                    error = message["error"]
                    raise DerivMarketDataError(error.get("message", "Deriv market data error"))
                if message.get("msg_type") == expected_type:
                    return message
            raise DerivMarketDataError("Deriv did not return the expected market-data response")
    except (DerivMarketDataError, asyncio.TimeoutError):
        raise
    except Exception as exc:
        raise DerivMarketDataError("Could not connect to Deriv public market data") from exc


async def get_active_markets(category: str = "all") -> list[dict[str, Any]]:
    if category not in {"all", "forex", "synthetic"}:
        raise ValueError("Unsupported Deriv market category")
    response = await _request({"active_symbols": "brief"}, "active_symbols")
    rows = response.get("active_symbols", [])
    result = []
    for row in rows:
        # Deriv New API renamed symbol/display fields; retain legacy fallbacks.
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or "")
        market = str(row.get("market", "")).lower()
        market_name = str(row.get("market_display_name") or row.get("market") or "").lower()
        submarket = str(row.get("submarket", "")).lower()
        is_forex = market == "forex" or "forex" in market_name or symbol.startswith("frx")
        is_synthetic = "synthetic" in market or "synthetic" in market_name or "synthetic" in submarket
        if not symbol or not (is_forex or is_synthetic):
            continue
        if category == "forex" and not is_forex:
            continue
        if category == "synthetic" and not is_synthetic:
            continue
        if category == "all" and not (is_forex or is_synthetic):
            continue
        result.append({
            "symbol": symbol,
            "name": row.get("underlying_symbol_name") or row.get("display_name") or symbol,
            "market": "forex" if is_forex else "synthetic",
            "market_display_name": row.get("market_display_name") or row.get("market", ""),
            "submarket_display_name": row.get("submarket_display_name") or row.get("submarket", ""),
            "is_open": None if row.get("exchange_is_open") is None else row.get("exchange_is_open") in (1, True, "1"),
            "is_suspended": row.get("is_trading_suspended", 0) == 1,
        })
    return result


async def get_tick_quotes(symbols: list[str]) -> dict[str, float]:
    """Fetch current public quotes for a bounded batch of active Deriv symbols."""
    requested = list(dict.fromkeys(str(symbol).strip() for symbol in symbols))
    if not requested or len(requested) > 25:
        raise ValueError("Request between 1 and 25 symbols")
    if any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in requested):
        raise ValueError("Invalid Deriv market symbol")
    active = await get_active_markets("all")
    active_symbols = {row["symbol"] for row in active}
    if any(symbol not in active_symbols for symbol in requested):
        raise ValueError("One or more symbols are not active on Deriv")
    quotes: dict[str, float] = {}
    try:
        async with websockets.connect(
            PUBLIC_WS, open_timeout=7, close_timeout=2, ping_interval=20,
            ping_timeout=10, max_size=2_000_000,
        ) as ws:
            await ws.send(json.dumps({"ticks": requested}))
            for _ in range(len(requested) + 3):
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                message = json.loads(raw)
                if message.get("error"):
                    error = message["error"]
                    raise DerivMarketDataError(error.get("message", "Deriv tick request failed"))
                tick = message.get("tick", {})
                symbol = tick.get("symbol")
                quote = tick.get("quote")
                if symbol in requested and quote is not None:
                    quotes[symbol] = float(quote)
                if len(quotes) == len(requested):
                    break
    except (DerivMarketDataError, asyncio.TimeoutError):
        raise
    except Exception as exc:
        raise DerivMarketDataError("Could not retrieve Deriv public tick quotes") from exc
    return quotes


async def get_candles(symbol: str, granularity: int = 900, count: int = 100) -> list[dict[str, Any]]:
    symbol = symbol.strip()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Invalid Deriv market symbol")
    if granularity not in ALLOWED_GRANULARITIES:
        raise ValueError("Unsupported candle interval")
    bounded_count = max(20, min(int(count), 200))
    active = await get_active_markets("all")
    if not any(row["symbol"] == symbol for row in active):
        raise ValueError("Unsupported Deriv market symbol")
    response = await _request({
        "ticks_history": symbol,
        "count": bounded_count,
        "end": "latest",
        "style": "candles",
        "granularity": granularity,
    }, "candles")
    rows = response.get("candles", [])
    return [{
        "time": int(row["epoch"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    } for row in rows]


async def get_available_contracts(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Invalid Deriv market symbol")
    active = await get_active_markets("all")
    if not any(row["symbol"] == symbol for row in active):
        raise ValueError("Unsupported Deriv market symbol")
    response = await _request({"contracts_for": symbol}, "contracts_for")
    payload = response.get("contracts_for", {})
    contracts = payload.get("available", []) if isinstance(payload, dict) else []
    return {
        "symbol": symbol,
        "contracts": [{
            "contract_type": row.get("contract_type"),
            "contract_display": row.get("contract_display"),
            "contract_category": row.get("contract_category"),
            "contract_category_display": row.get("contract_category_display"),
            "min_contract_duration": row.get("min_contract_duration"),
            "max_contract_duration": row.get("max_contract_duration"),
            "min_contract_duration_units": row.get("min_contract_duration_units"),
            "max_contract_duration_units": row.get("max_contract_duration_units"),
        } for row in contracts],
    }


async def get_contract_proposal(
    symbol: str,
    contract_type: str,
    amount: float = 1.0,
    duration: int = 5,
    duration_unit: str = "m",
    currency: str = "USD",
) -> dict[str, Any]:
    """Get a public CALL/PUT price quote only; this never buys a contract."""
    symbol = symbol.strip()
    contract_type = contract_type.upper().strip()
    currency = currency.upper().strip()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Invalid Deriv market symbol")
    if contract_type not in {"CALL", "PUT"}:
        raise ValueError("Only CALL and PUT contract quotes are supported")
    amount, duration = validate_demo_quote(amount, duration)
    if duration_unit != "m":
        raise ValueError("Only minute-based binary contract quotes are supported")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Invalid account currency")
    active = await get_active_markets("all")
    if not any(row["symbol"] == symbol and not row["is_suspended"] for row in active):
        raise ValueError("Symbol is not currently available for trading")
    available = await get_available_contracts(symbol)
    if not any(row.get("contract_type") == contract_type for row in available["contracts"]):
        raise ValueError("This CALL/PUT contract is not available for the selected symbol")
    response = await _request({
        "proposal": 1,
        "amount": float(amount),
        "basis": "stake",
        "contract_type": contract_type,
        "currency": currency,
        "duration": int(duration),
        "duration_unit": duration_unit,
        "underlying_symbol": symbol,
    }, "proposal")
    proposal = response.get("proposal", {})
    if not proposal.get("id") or proposal.get("ask_price") is None:
        raise DerivMarketDataError("Deriv returned an incomplete price proposal")
    return {
        "symbol": symbol,
        "contract_type": contract_type,
        "stake": float(proposal["ask_price"]),
        "payout": float(proposal.get("payout", 0)),
        "proposal_id": proposal["id"],
        "longcode": proposal.get("longcode", ""),
        "spot": proposal.get("spot"),
        "currency": currency,
        "duration": int(duration),
        "duration_unit": duration_unit,
        "quote_only": True,
        "execution_enabled": False,
    }
