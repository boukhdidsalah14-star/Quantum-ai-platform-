"""Read-only MEXC USD-M futures account verification.

Uses MEXC's futures contract API, not the Spot API. This module does not place
orders. Futures API access is subject to MEXC account eligibility and API-key
permissions; there is no official futures sandbox.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx

BASE_URL = "https://api.mexc.com"


class MexcFuturesError(RuntimeError):
    pass


def _signature(api_key: str, api_secret: str, timestamp: str, request_param: str = "") -> str:
    target = api_key + timestamp + request_param
    return hmac.new(api_secret.encode(), target.encode(), hashlib.sha256).hexdigest()


def _headers(api_key: str, api_secret: str, timestamp: str | None = None) -> dict[str, str]:
    request_time = timestamp or str(int(time.time() * 1000))
    return {
        "ApiKey": api_key,
        "Request-Time": request_time,
        "Signature": _signature(api_key, api_secret, request_time),
        "Content-Type": "application/json",
        "Recv-Window": "5000",
    }


def _parse_assets(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("success") is not True or payload.get("code") not in (0, "0"):
        raise MexcFuturesError("MEXC Futures rejected the account verification request")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MexcFuturesError("MEXC Futures returned an unexpected account response")
    assets = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        currency = str(row.get("currency") or "").upper()
        if not currency:
            continue
        assets.append({
            "currency": currency,
            "available_balance": str(row.get("availableBalance", "0")),
            "equity": str(row.get("equity", "0")),
            "position_margin": str(row.get("positionMargin", "0")),
            "unrealized_pnl": str(row.get("unrealized", "0")),
        })
    return {"connected": True, "broker": "mexc", "market": "usdt_margined_perpetual_futures",
            "mode": "real", "assets": assets}


async def get_futures_account_info(api_key: str, api_secret: str) -> dict:
    """Verify read-only access to the customer's MEXC Futures account."""
    if not api_key or len(api_key) > 256 or not api_secret or len(api_secret) > 512:
        raise ValueError("MEXC Futures API key and secret are required")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=4)) as client:
            response = await client.get(
                BASE_URL + "/api/v1/private/account/assets",
                headers=_headers(api_key, api_secret),
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MexcFuturesError("MEXC Futures account verification failed") from exc
    return _parse_assets(payload)
