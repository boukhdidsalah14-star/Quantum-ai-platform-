"""MEXC Spot live adapter. Disabled by default; never used by paper-trading routes.

MEXC Spot has no sandbox. Callers must obtain an explicit per-customer live
authorization before invoking place_market_order. This module does not store
API keys and never logs signed URLs, headers, or secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx

BASE_URL = "https://api.mexc.com"
MAX_ORDER_QUOTE_USDT = Decimal("10.00")
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}


class MexcExecutionError(RuntimeError):
    pass


def _enabled() -> bool:
    return os.getenv("QUANTUM_MEXC_LIVE_TRADING_ENABLED", "").strip().lower() == "true"


def _amount(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid order amount")
    if not result.is_finite() or result <= 0:
        raise ValueError("Order amount must be a positive finite number")
    return result


def _signed_params(params: list[tuple[str, str]], secret: str) -> str:
    query = urlencode(params)
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + "&signature=" + signature


async def get_account_info(api_key: str, api_secret: str) -> dict:
    """Verify a customer's MEXC API key with a signed read-only account request."""
    if not api_key or not api_secret:
        raise ValueError("MEXC API key and secret are required")
    params = [("timestamp", str(int(time.time() * 1000))), ("recvWindow", "5000")]
    query = _signed_params(params, api_secret)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4)) as client:
            response = await client.get(
                BASE_URL + "/api/v3/account?" + query,
                headers={"X-MEXC-APIKEY": api_key},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MexcExecutionError("MEXC account verification failed") from exc
    balances = []
    for item in payload.get("balances", []):
        free = _amount(item.get("free", "0")) if Decimal(str(item.get("free", "0"))) > 0 else Decimal("0")
        locked = _amount(item.get("locked", "0")) if Decimal(str(item.get("locked", "0"))) > 0 else Decimal("0")
        if free or locked:
            balances.append({"asset": str(item.get("asset", "")), "free": str(free), "locked": str(locked)})
    return {"connected": True, "broker": "mexc", "mode": "real", "balances": balances}


async def place_market_order(
    api_key: str,
    api_secret: str,
    *,
    symbol: str,
    side: str,
    quote_amount_usdt: object,
    customer_live_consent: bool,
    idempotency_key: str,
) -> dict:
    """Place a capped USDT market order only after two independent live gates.

    This is a real-money endpoint, not a sandbox. The caller must persist and
    reserve idempotency_key before calling; uncertain network outcomes must be
    reconciled via the exchange order-query endpoint before retrying.
    """
    if not _enabled() or not customer_live_consent:
        raise MexcExecutionError("MEXC live execution is locked; explicit customer consent and the server kill switch are required")
    if not api_key or not api_secret:
        raise ValueError("MEXC API credentials are required")
    symbol = str(symbol).upper().strip()
    side = str(side).upper().strip()
    if symbol not in ALLOWED_SYMBOLS or side not in {"BUY", "SELL"}:
        raise ValueError("Unsupported MEXC symbol or side")
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValueError("A persisted idempotency key is required")
    quote_amount = _amount(quote_amount_usdt)
    if quote_amount > MAX_ORDER_QUOTE_USDT:
        raise ValueError("MEXC live order exceeds the initial $10 USDT safety cap")
    # MEXC market orders support quoteOrderQty for quote-denominated sizing.
    params = [
        ("symbol", symbol),
        ("side", side),
        ("type", "MARKET"),
        ("quoteOrderQty", format(quote_amount, "f")),
        ("recvWindow", "5000"),
        ("timestamp", str(int(time.time() * 1000))),
    ]
    query = _signed_params(params, api_secret)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4)) as client:
            response = await client.post(
                BASE_URL + "/api/v3/order?" + query,
                headers={"X-MEXC-APIKEY": api_key},
            )
            response.raise_for_status()
            result = response.json()
    except httpx.TimeoutException as exc:
        raise MexcExecutionError("MEXC order outcome is unknown; reconcile by exchange order history before retrying") from exc
    except httpx.HTTPError as exc:
        raise MexcExecutionError("MEXC rejected or could not confirm the order") from exc
    return {
        "broker": "mexc",
        "mode": "real",
        "symbol": symbol,
        "side": side,
        "order_id": str(result.get("orderId", "")),
        "status": str(result.get("status", "UNKNOWN")),
        "executed_qty": str(result.get("executedQty", "0")),
        "quote_order_qty": str(result.get("cummulativeQuoteQty", "0")),
    }
