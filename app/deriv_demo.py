"""Demo-only Deriv account status check using the current OTP/WebSocket flow.

This module is read-only: it requests balance and active symbols only.
It never sends proposal, buy, sell, or contract-management messages.
"""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import urlparse

import httpx
import websockets

DERIV_API = "https://api.derivws.com"
ACCOUNT_RE = re.compile(r"^VRTC[A-Z0-9]+$", re.IGNORECASE)


class DerivConfigError(RuntimeError):
    pass


class DerivConnectionError(RuntimeError):
    pass


def _settings() -> tuple[str, str, str]:
    token = os.getenv("DERIV_DEMO_TOKEN", "").strip()
    account_id = os.getenv("DERIV_DEMO_ACCOUNT_ID", "").strip().upper()
    app_id = os.getenv("DERIV_APP_ID", "").strip()
    if not token or not account_id or not app_id:
        raise DerivConfigError("Deriv demo credentials are not configured")
    if not ACCOUNT_RE.fullmatch(account_id):
        raise DerivConfigError("Only a Deriv virtual demo account ID (VRTC...) is accepted")
    return token, account_id, app_id


async def _get_demo_ws_url(token: str, account_id: str, app_id: str) -> str:
    url = f"{DERIV_API}/trading/v1/options/accounts/{account_id}/otp"
    headers = {"Authorization": f"Bearer {token}", "Deriv-App-ID": app_id}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
        response = await client.post(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    ws_url = payload.get("data", {}).get("url", "")
    parsed = urlparse(ws_url)
    if parsed.scheme != "wss" or parsed.hostname != "api.derivws.com" or not parsed.path.endswith("/demo"):
        raise DerivConnectionError("Deriv did not return a verified demo WebSocket URL")
    return ws_url


async def get_demo_status() -> dict:
    token, account_id, app_id = _settings()
    ws_url = await _get_demo_ws_url(token, account_id, app_id)
    try:
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=3, max_size=1_000_000) as ws:
            await ws.send('{"balance":1,"req_id":1}')
            await ws.send('{"active_symbols":"brief","req_id":2}')
            results = {}
            for _ in range(2):
                raw = await asyncio.wait_for(ws.recv(), timeout=12)
                import json
                message = json.loads(raw)
                if message.get("error"):
                    raise DerivConnectionError(message["error"].get("message", "Deriv request failed"))
                req_id = message.get("req_id")
                if req_id == 1 and "balance" in message:
                    b = message["balance"]
                    results["balance"] = {"amount": b.get("balance"), "currency": b.get("currency")}
                elif req_id == 2 and "active_symbols" in message:
                    results["active_symbols_count"] = len(message["active_symbols"])
            if "balance" not in results or "active_symbols_count" not in results:
                raise DerivConnectionError("Deriv demo account response was incomplete")
            return {
                "connected": True,
                "account_mode": "demo",
                "account_id": account_id,
                "balance": results["balance"],
                "active_symbols_count": results["active_symbols_count"],
                "read_only": True,
                "order_execution": False,
            }
    except (asyncio.TimeoutError, OSError) as exc:
        raise DerivConnectionError("Could not complete the Deriv demo status check") from exc
