"""Read-only cTrader Open API account discovery and demo-account reconciliation.

This adapter intentionally supports demo account discovery and read-only
account snapshots only. It does not submit, amend, or close orders.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import websockets

from app.database import sqlite3
from app.ctrader_oauth import CTraderOAuthError, refresh_access_token

DEMO_WS_URL = "wss://demo.ctraderapi.com:5036"
APP_AUTH_REQ = 2100
APP_AUTH_RES = 2101
ACCOUNT_AUTH_REQ = 2102
ACCOUNT_AUTH_RES = 2103
TRADER_REQ = 2121
TRADER_RES = 2122
RECONCILE_REQ = 2124
RECONCILE_RES = 2125
GET_ACCOUNTS_REQ = 2149
GET_ACCOUNTS_RES = 2150
ERROR_RES = 2142


class CTraderOpenAPIError(RuntimeError):
    pass


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS ctrader_account_snapshots (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL,
          broker_title TEXT NOT NULL,
          trader_login TEXT,
          snapshot_json TEXT NOT NULL,
          synced_at INTEGER NOT NULL
        )""")


def _broker_is_ic_markets(name: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", str(name or "").lower())
    return "icmarkets" in normalized


async def _request(ws, payload_type: int, payload: dict[str, Any],
                   expected_type: int, timeout: float = 12.0) -> dict:
    message_id = uuid.uuid4().hex
    await ws.send(json.dumps({
        "clientMsgId": message_id,
        "payloadType": payload_type,
        "payload": payload,
    }, separators=(",", ":")))
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise CTraderOpenAPIError("cTrader did not respond in time")
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            message = json.loads(raw)
        except asyncio.TimeoutError as exc:
            raise CTraderOpenAPIError("cTrader did not respond in time") from exc
        except (ValueError, TypeError) as exc:
            raise CTraderOpenAPIError("cTrader returned an unreadable response") from exc
        if not isinstance(message, dict):
            continue
        response_type = message.get("payloadType")
        response_payload = message.get("payload") or {}
        if response_type == ERROR_RES or response_type == 50:
            code = str(response_payload.get("errorCode") or "OPEN_API_ERROR")
            raise CTraderOpenAPIError("cTrader rejected the account request (" + code + ")")
        if message.get("clientMsgId") != message_id:
            # Heartbeats and asynchronous account events are not request replies.
            continue
        if response_type != expected_type:
            raise CTraderOpenAPIError("cTrader returned an unexpected response")
        if not isinstance(response_payload, dict):
            raise CTraderOpenAPIError("cTrader returned an invalid response payload")
        return response_payload


async def _open_demo_session(access_token: str):
    try:
        ws = await websockets.connect(
            DEMO_WS_URL,
            open_timeout=10,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=2_000_000,
        )
    except Exception as exc:
        raise CTraderOpenAPIError("Could not connect to the cTrader demo gateway") from exc
    try:
        await _request(ws, APP_AUTH_REQ, {
            "clientId": os.getenv("CTRADER_CLIENT_ID", "").strip(),
            "clientSecret": os.getenv("CTRADER_CLIENT_SECRET", "").strip(),
        }, APP_AUTH_RES)
        accounts = await _request(ws, GET_ACCOUNTS_REQ, {
            "accessToken": access_token,
        }, GET_ACCOUNTS_RES)
        permission = accounts.get("permissionScope")
        if permission not in (1, "1", "SCOPE_TRADE"):
            raise CTraderOpenAPIError("The cTrader authorization does not include trading permission")
        return ws, accounts
    except Exception:
        await ws.close()
        raise


def _account_rows(payload: dict) -> list[dict]:
    rows = payload.get("ctidTraderAccount") or payload.get("ctidTraderAccounts") or []
    if not isinstance(rows, list):
        raise CTraderOpenAPIError("cTrader returned an invalid account list")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_id = row.get("ctidTraderAccountId")
        if account_id is None:
            continue
        result.append({
            "account_id": str(account_id),
            "trader_login": str(row.get("traderLogin") or ""),
            "broker": str(row.get("brokerTitleShort") or ""),
            "is_live": bool(row.get("isLive", False)),
            "environment": "live" if bool(row.get("isLive", False)) else "demo",
        })
    return result


async def discover_demo_accounts(customer_id: str) -> list[dict]:
    tokens = await refresh_access_token(customer_id)
    if not tokens.get("access_token"):
        raise CTraderOpenAPIError("No valid cTrader access token is available")
    ws, payload = await _open_demo_session(tokens["access_token"])
    try:
        accounts = [a for a in _account_rows(payload) if not a["is_live"]]
        # Do not expose account IDs belonging to a different broker as eligible choices.
        return [a for a in accounts if _broker_is_ic_markets(a["broker"])]
    finally:
        await ws.close()


def _scaled(value: Any, digits: Any) -> float | None:
    if value is None:
        return None
    try:
        return int(value) / (10 ** max(0, min(12, int(digits or 0))))
    except (TypeError, ValueError, OverflowError):
        return None


def _position_summary(position: dict) -> dict:
    trade = position.get("tradeData") or {}
    return {
        "position_id": str(position.get("positionId") or ""),
        "symbol_id": str(trade.get("symbolId") or ""),
        "side": "BUY" if trade.get("tradeSide") in (1, "1", "BUY") else "SELL",
        "volume_units": _scaled(trade.get("volume"), 2),
        "stop_loss": position.get("stopLoss"),
        "take_profit": position.get("takeProfit"),
    }


async def sync_demo_account(customer_id: str, account_id: str) -> dict:
    if not str(account_id).isdigit():
        raise ValueError("Choose a valid cTrader account")
    tokens = await refresh_access_token(customer_id)
    ws, payload = await _open_demo_session(tokens["access_token"])
    try:
        accounts = _account_rows(payload)
        selected = next((a for a in accounts if a["account_id"] == str(account_id)), None)
        if not selected:
            raise CTraderOpenAPIError("That account is not available under this cTrader authorization")
        if selected["is_live"]:
            raise CTraderOpenAPIError("Live accounts are locked. Select an IC Markets demo account for testing.")
        if not _broker_is_ic_markets(selected["broker"]):
            raise CTraderOpenAPIError("The selected cTrader account is not identified as IC Markets")
        await _request(ws, ACCOUNT_AUTH_REQ, {
            "ctidTraderAccountId": int(account_id),
            "accessToken": tokens["access_token"],
        }, ACCOUNT_AUTH_RES)
        trader_response = await _request(ws, TRADER_REQ, {
            "ctidTraderAccountId": int(account_id),
        }, TRADER_RES)
        reconcile = await _request(ws, RECONCILE_REQ, {
            "ctidTraderAccountId": int(account_id),
            "returnProtectionOrders": False,
        }, RECONCILE_RES)
        trader = trader_response.get("trader") or {}
        money_digits = trader.get("moneyDigits", 2)
        positions = reconcile.get("position") or []
        orders = reconcile.get("order") or []
        snapshot = {
            "account_id": str(account_id),
            "broker": selected["broker"],
            "trader_login": selected["trader_login"],
            "environment": "demo",
            "balance": _scaled(trader.get("balance"), money_digits),
            "money_digits": int(money_digits or 0),
            "deposit_asset_id": str(trader.get("depositAssetId") or ""),
            "leverage": trader.get("leverageInCents"),
            "open_positions": [_position_summary(p) for p in positions if isinstance(p, dict)],
            "pending_orders_count": len(orders) if isinstance(orders, list) else 0,
            "trading_permission": "trade",
            "trading_enabled": False,
            "source": "cTrader Open API",
        }
        import time
        synced_at = int(time.time())
        with _db() as db:
            db.execute("""
            INSERT INTO ctrader_account_snapshots
              (customer_id, account_id, broker_title, trader_login, snapshot_json, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
              account_id=excluded.account_id,
              broker_title=excluded.broker_title,
              trader_login=excluded.trader_login,
              snapshot_json=excluded.snapshot_json,
              synced_at=excluded.synced_at
            """, (customer_id, str(account_id), selected["broker"],
                  selected["trader_login"], json.dumps(snapshot, separators=(",", ":")), synced_at))
        return {**snapshot, "synced_at": synced_at, "connected": True}
    finally:
        await ws.close()


def saved_snapshot(customer_id: str) -> dict | None:
    with _db() as db:
        row = db.execute(
            "SELECT snapshot_json, synced_at FROM ctrader_account_snapshots WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return None
    try:
        snapshot = json.loads(row["snapshot_json"])
    except (ValueError, TypeError):
        return None
    return {**snapshot, "synced_at": int(row["synced_at"]), "connected": True}


def clear_snapshot(customer_id: str) -> None:
    with _db() as db:
        db.execute("DELETE FROM ctrader_account_snapshots WHERE customer_id=?", (customer_id,))
