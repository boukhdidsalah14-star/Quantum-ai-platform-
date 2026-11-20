"""cTrader Open API account discovery, demo reconciliation, and demo execution.

Live sessions and live order execution remain locked pending Spotware approval
and later customer-level risk authorization.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import websockets

from app.database import sqlite3
from app.ctrader_oauth import CTraderOAuthError, refresh_access_token
from app.ctrader_risk import (
    init_db as init_risk_db, record_account_sync, reserve_entry as reserve_risk_entry,
    release_entry as release_risk_entry, sync_open_positions as sync_risk_positions,
    record_open_position as record_risk_open_position,
)
from app.ctrader_permissions import require_demo_permission


# Spotware JSON protocol WebSocket endpoints (port 5036).
# Environment is resolved from broker account metadata, never a client URL.
DEMO_WS_URL = "wss://demo.ctraderapi.com:5036"
LIVE_WS_URL = "wss://live.ctraderapi.com:5036"
APP_AUTH_REQ = 2100
APP_AUTH_RES = 2101
ACCOUNT_AUTH_REQ = 2102
ACCOUNT_AUTH_RES = 2103
TRADER_REQ = 2121
TRADER_RES = 2122
RECONCILE_REQ = 2124
RECONCILE_RES = 2125
EXECUTION_EVENT = 2126
NEW_ORDER_REQ = 2106
AMEND_POSITION_SLTP_REQ = 2110
CLOSE_POSITION_REQ = 2111
ORDER_ERROR_EVENT = 2132
GET_ACCOUNTS_REQ = 2149
GET_ACCOUNTS_RES = 2150
SYMBOLS_LIST_REQ = 2114
SYMBOLS_LIST_RES = 2115
GET_TRENDBARS_REQ = 2137
GET_TRENDBARS_RES = 2138
DEAL_LIST_REQ = 2133
DEAL_LIST_RES = 2134
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
        db.execute("""
        CREATE TABLE IF NOT EXISTS ctrader_live_account_snapshots (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL,
          broker_title TEXT NOT NULL,
          trader_login TEXT,
          snapshot_json TEXT NOT NULL,
          synced_at INTEGER NOT NULL
        )""")
    init_risk_db()


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
        if response_type in (ERROR_RES, ORDER_ERROR_EVENT, 50):
            code = str(response_payload.get("errorCode") or "OPEN_API_ERROR")
            description = str(response_payload.get("description") or response_payload.get("message") or "")
            detail = re.sub(r"[^A-Za-z0-9 _.-]", "", description)[:120]
            suffix = f": {detail}" if detail else ""
            raise CTraderOpenAPIError("cTrader rejected the account request (" + code + ")" + suffix)
        if message.get("clientMsgId") != message_id:
            # Heartbeats and asynchronous account events are not request replies.
            continue
        if response_type != expected_type:
            raise CTraderOpenAPIError("cTrader returned an unexpected response")
        if not isinstance(response_payload, dict):
            raise CTraderOpenAPIError("cTrader returned an invalid response payload")
        return response_payload


def _ctrader_ws_url(environment: str) -> str:
    """Resolve a cTrader gateway from a verified environment label."""
    normalized = str(environment or "").strip().lower()
    if normalized == "demo":
        return DEMO_WS_URL
    if normalized == "live":
        return LIVE_WS_URL
    raise ValueError("cTrader environment must be demo or live")


async def _open_ctrader_session(access_token: str, environment: str = "demo"):
    """Open and app-authenticate the official Spotware JSON WebSocket session.

    Transport/session infrastructure only: this function does not submit
    orders. Live sessions remain locked until the later authorization step.
    """
    if not access_token:
        raise CTraderOpenAPIError("No valid cTrader access token is available")
    normalized = str(environment or "").strip().lower()
    if normalized == "live" and os.getenv(
        "QUANTUM_CTRADER_LIVE_SESSION_ENABLED", ""
    ).strip().lower() != "true":
        raise CTraderOpenAPIError(
            "Live cTrader sessions are locked until customer live authorization is enabled"
        )
    ws_url = _ctrader_ws_url(normalized)
    try:
        ws = await websockets.connect(
            ws_url,
            open_timeout=10,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=2_000_000,
        )
    except Exception as exc:
        raise CTraderOpenAPIError(
            "Could not connect to the cTrader " + normalized + " gateway"
        ) from exc
    try:
        await _request(ws, APP_AUTH_REQ, {
            "clientId": os.getenv("CTRADER_CLIENT_ID", "").strip(),
            "clientSecret": os.getenv("CTRADER_CLIENT_SECRET", "").strip(),
        }, APP_AUTH_RES)
        accounts = await _request(ws, GET_ACCOUNTS_REQ, {
            "accessToken": access_token,
        }, GET_ACCOUNTS_RES)
        # GET_ACCOUNTS_RES contains account identity/environment metadata.
        # Trading scope is requested in OAuth and enforced by account/order auth.
        return ws, accounts
    except Exception:
        await ws.close()
        raise


async def _open_demo_session(access_token: str):
    """Backward-compatible demo-only session wrapper."""
    return await _open_ctrader_session(access_token, "demo")

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
            "trading_permission": "oauth_trading_scope_requested",
            "trading_enabled": False,
            "source": "cTrader Open API",
        }
        import time
        synced_at = int(time.time())
        record_account_sync(customer_id, str(account_id), snapshot["balance"] or 0)
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



# Step 2 demo execution. Keep the initial demo order cap deliberately small;
# server-side account/customer risk policy is expanded in Step 3.
MAX_DEMO_LOTS = 0.01
VOLUME_CENTS_PER_LOT = 10_000_000


def _valid_positive_price(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a valid positive price") from exc
    if not (number > 0 and number < 1_000_000_000):
        raise ValueError(f"{field} must be a valid positive price")
    return number


async def _ensure_demo_trade_access(ws, account_id: str, allow_close_only: bool = False) -> dict:
    response = await _request(ws, TRADER_REQ, {
        "ctidTraderAccountId": int(account_id),
    }, TRADER_RES)
    trader = response.get("trader") or {}
    # ProtoOAAccessRights: FULL_ACCESS=0, CLOSE_ONLY=1, NO_TRADING=2, NO_LOGIN=3.
    rights = int(trader.get("accessRights", 0))
    if rights != 0 and not (allow_close_only and rights == 1):
        raise CTraderOpenAPIError("This demo account does not have permission for that trading action")
    return trader


async def _demo_symbol_id(ws, account_id: str, symbol: str) -> tuple[int, str]:
    response = await _request(ws, SYMBOLS_LIST_REQ, {
        "ctidTraderAccountId": int(account_id),
        "includeArchivedSymbols": False,
    }, SYMBOLS_LIST_RES)
    rows = response.get("symbol") or []
    wanted = _normalize_symbol(symbol)
    match = next((item for item in rows if isinstance(item, dict)
                  and _normalize_symbol(item.get("symbolName", "")) == wanted
                  and bool(item.get("enabled", True))), None)
    if not match:
        raise ValueError("This symbol is not available on the selected IC Markets demo account")
    return int(match["symbolId"]), str(match.get("symbolName") or symbol)


async def open_demo_trade(customer_id: str, symbol: str, side: str, lots: float,
                          stop_loss: float, take_profit: float) -> dict:
    normalized_side = str(side or "").strip().upper()
    if normalized_side not in ("BUY", "SELL"):
        raise ValueError("Trade side must be BUY or SELL")
    try:
        lot_size = float(lots)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Trade size must be valid") from exc
    if not (0 < lot_size <= MAX_DEMO_LOTS):
        raise ValueError(f"Demo trade size must be greater than zero and no more than {MAX_DEMO_LOTS} lots")
    sl = _valid_positive_price(stop_loss, "Stop-loss")
    tp = _valid_positive_price(take_profit, "Take-profit")
    if sl == tp:
        raise ValueError("Stop-loss and take-profit must be different prices")
    ws, selected = await _open_selected_demo(customer_id)
    reservation_id = None
    try:
        account_id = selected["account_id"]
        require_demo_permission(customer_id, account_id)
        trader = await _ensure_demo_trade_access(ws, account_id)
        balance = _scaled(trader.get("balance"), trader.get("moneyDigits", 2))
        reconcile = await _request(ws, RECONCILE_REQ, {
            "ctidTraderAccountId": int(account_id),
            "returnProtectionOrders": False,
        }, RECONCILE_RES)
        positions = reconcile.get("position") or []
        open_positions = [item for item in positions if isinstance(item, dict)]
        open_count = len(open_positions)
        sync_risk_positions(customer_id, account_id, [
            item.get("positionId") for item in open_positions if item.get("positionId") is not None
        ])
        symbol_id, symbol_name = await _demo_symbol_id(ws, account_id, symbol)
        reservation_id = reserve_risk_entry(customer_id, account_id, balance or 0, open_count, lot_size)
        client_order_id = uuid.uuid4().hex[:32]
        event = await _request(ws, NEW_ORDER_REQ, {
            "ctidTraderAccountId": int(account_id),
            "symbolId": symbol_id,
            "orderType": 1,
            "tradeSide": 1 if normalized_side == "BUY" else 2,
            "volume": int(round(lot_size * VOLUME_CENTS_PER_LOT)),
            "stopLoss": sl,
            "takeProfit": tp,
            "clientOrderId": client_order_id,
            "label": "QUANTUM_AI_DEMO",
        }, EXECUTION_EVENT, timeout=25.0)
        execution_type = int(event.get("executionType", 0))
        if execution_type == 7:
            raise CTraderOpenAPIError("The cTrader demo broker rejected the order")
        position = event.get("position") or {}
        order = event.get("order") or {}
        if position.get("positionId") is not None:
            record_risk_open_position(customer_id, account_id, position.get("positionId"))
        return {
            "accepted": execution_type in (2, 3, 11),
            "execution_type": execution_type,
            "account_id": account_id,
            "environment": "demo",
            "symbol": symbol_name,
            "side": normalized_side,
            "lots": lot_size,
            "stop_loss": sl,
            "take_profit": tp,
            "position_id": str(position.get("positionId") or ""),
            "order_id": str(order.get("orderId") or ""),
            "client_order_id": client_order_id,
            "broker_confirmed": True,
            "risk_controls": "passed",
        }
    finally:
        release_risk_entry(reservation_id)
        await ws.close()


async def _find_demo_position(ws, account_id: str, position_id: str) -> dict:
    if not str(position_id).isdigit():
        raise ValueError("Choose a valid position")
    response = await _request(ws, RECONCILE_REQ, {
        "ctidTraderAccountId": int(account_id),
        "returnProtectionOrders": False,
    }, RECONCILE_RES)
    positions = response.get("position") or []
    match = next((item for item in positions if isinstance(item, dict)
                  and str(item.get("positionId")) == str(position_id)), None)
    if not match:
        raise CTraderOpenAPIError("That position is not open on your selected demo account")
    return match


async def amend_demo_position(customer_id: str, position_id: str,
                              stop_loss: float, take_profit: float) -> dict:
    sl = _valid_positive_price(stop_loss, "Stop-loss")
    tp = _valid_positive_price(take_profit, "Take-profit")
    if sl == tp:
        raise ValueError("Stop-loss and take-profit must be different prices")
    ws, selected = await _open_selected_demo(customer_id)
    try:
        account_id = selected["account_id"]
        await _ensure_demo_trade_access(ws, account_id)
        await _find_demo_position(ws, account_id, position_id)
        event = await _request(ws, AMEND_POSITION_SLTP_REQ, {
            "ctidTraderAccountId": int(account_id),
            "positionId": int(position_id),
            "stopLoss": sl,
            "takeProfit": tp,
        }, EXECUTION_EVENT, timeout=25.0)
        execution_type = int(event.get("executionType", 0))
        if execution_type not in (2, 3, 4, 13, 14):
            raise CTraderOpenAPIError("cTrader did not confirm the protection update")
        return {
            "updated": True, "broker_confirmed": True,
            "account_id": account_id, "environment": "demo",
            "position_id": str(position_id), "stop_loss": sl, "take_profit": tp,
            "execution_type": execution_type,
        }
    finally:
        await ws.close()


async def close_demo_position(customer_id: str, position_id: str) -> dict:
    ws, selected = await _open_selected_demo(customer_id)
    try:
        account_id = selected["account_id"]
        await _ensure_demo_trade_access(ws, account_id, allow_close_only=True)
        position = await _find_demo_position(ws, account_id, position_id)
        trade = position.get("tradeData") or {}
        volume = int(trade.get("volume") or 0)
        if volume <= 0:
            raise CTraderOpenAPIError("cTrader returned an invalid position volume")
        event = await _request(ws, CLOSE_POSITION_REQ, {
            "ctidTraderAccountId": int(account_id),
            "positionId": int(position_id),
            "volume": volume,
        }, EXECUTION_EVENT, timeout=25.0)
        execution_type = int(event.get("executionType", 0))
        if execution_type not in (2, 3, 11):
            raise CTraderOpenAPIError("cTrader did not confirm the position close")
        return {
            "closed_or_closing": True, "broker_confirmed": True,
            "account_id": account_id, "environment": "demo",
            "position_id": str(position_id), "execution_type": execution_type,
        }
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

TIMEFRAMES = {
    "1m": (1, 60),
    "5m": (5, 300),
    "15m": (7, 900),
    "30m": (8, 1800),
    "1h": (9, 3600),
    "4h": (10, 14400),
    "1d": (12, 86400),
}


async def _open_selected_demo(customer_id: str):
    snapshot = saved_snapshot(customer_id)
    if not snapshot or snapshot.get("environment") != "demo":
        raise CTraderOpenAPIError("Connect and sync an IC Markets demo account first")
    tokens = await refresh_access_token(customer_id)
    ws, payload = await _open_demo_session(tokens["access_token"])
    try:
        selected = next((a for a in _account_rows(payload)
                         if a["account_id"] == str(snapshot["account_id"])), None)
        if not selected or selected["is_live"] or not _broker_is_ic_markets(selected["broker"]):
            raise CTraderOpenAPIError("The saved IC Markets demo account is no longer available")
        await _request(ws, ACCOUNT_AUTH_REQ, {
            "ctidTraderAccountId": int(selected["account_id"]),
            "accessToken": tokens["access_token"],
        }, ACCOUNT_AUTH_RES)
        return ws, selected
    except Exception:
        await ws.close()
        raise


def _normalize_symbol(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    # QUANTUM uses Deriv-style frxEURUSD IDs; cTrader lists EURUSD.
    if normalized.startswith("FRX") and len(normalized) == 9:
        normalized = normalized[3:]
    return normalized


async def discover_demo_symbols(customer_id: str) -> list[dict]:
    ws, selected = await _open_selected_demo(customer_id)
    try:
        response = await _request(ws, SYMBOLS_LIST_REQ, {
            "ctidTraderAccountId": int(selected["account_id"]),
            "includeArchivedSymbols": False,
        }, SYMBOLS_LIST_RES)
        symbols = response.get("symbol") or []
        if not isinstance(symbols, list):
            raise CTraderOpenAPIError("cTrader returned an invalid symbol list")
        return sorted([{
            "symbol_id": str(item.get("symbolId")),
            "symbol": str(item.get("symbolName") or ""),
            "enabled": bool(item.get("enabled", True)),
        } for item in symbols if isinstance(item, dict)
          and item.get("symbolId") is not None
          and item.get("symbolName")
          and bool(item.get("enabled", True))],
          key=lambda item: item["symbol"])
    finally:
        await ws.close()


async def get_demo_candles(customer_id: str, symbol: str,
                           timeframe: str = "15m", count: int = 80) -> dict:
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported cTrader chart timeframe")
    if not 20 <= int(count) <= 200:
        raise ValueError("Candle count must be between 20 and 200")
    ws, selected = await _open_selected_demo(customer_id)
    try:
        symbols_response = await _request(ws, SYMBOLS_LIST_REQ, {
            "ctidTraderAccountId": int(selected["account_id"]),
            "includeArchivedSymbols": False,
        }, SYMBOLS_LIST_RES)
        symbols = symbols_response.get("symbol") or []
        wanted = _normalize_symbol(symbol)
        match = next((item for item in symbols if isinstance(item, dict)
                      and _normalize_symbol(item.get("symbolName", "")) == wanted
                      and bool(item.get("enabled", True))), None)
        if not match:
            raise ValueError("This symbol is not available on the selected IC Markets demo account")
        period, seconds = TIMEFRAMES[timeframe]
        to_ms = int(time.time() * 1000)
        from_ms = to_ms - (seconds * int(count) * 1000)
        response = await _request(ws, GET_TRENDBARS_REQ, {
            "ctidTraderAccountId": int(selected["account_id"]),
            "fromTimestamp": from_ms,
            "toTimestamp": to_ms,
            "period": period,
            "symbolId": int(match["symbolId"]),
            "count": int(count),
        }, GET_TRENDBARS_RES)
        bars = response.get("trendbar") or []
        candles = []
        for bar in bars:
            if not isinstance(bar, dict) or bar.get("low") is None:
                continue
            low_raw = int(bar["low"])
            scale = 100000.0
            low = low_raw / scale
            candles.append({
                "time": int(bar.get("utcTimestampInMinutes") or 0) * 60,
                "open": (low_raw + int(bar.get("deltaOpen") or 0)) / scale,
                "high": (low_raw + int(bar.get("deltaHigh") or 0)) / scale,
                "low": low,
                "close": (low_raw + int(bar.get("deltaClose") or 0)) / scale,
                "volume": int(bar.get("volume") or 0),
            })
        candles.sort(key=lambda item: item["time"])
        return {
            "symbol": str(match.get("symbolName") or symbol),
            "timeframe": timeframe,
            "source": "IC Markets cTrader demo market data",
            "candles": candles,
            "execution_enabled": False,
        }
    finally:
        await ws.close()



async def get_demo_trade_history(customer_id: str, days: int = 7, limit: int = 100) -> dict:
    """Read recent executions directly from the selected IC Markets demo account."""
    try:
        days, limit = int(days), int(limit)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("History range and limit must be valid integers") from exc
    if not 1 <= days <= 30:
        raise ValueError("Trade history range must be between 1 and 30 days")
    if not 1 <= limit <= 100:
        raise ValueError("Trade history limit must be between 1 and 100")

    ws, selected = await _open_selected_demo(customer_id)
    try:
        account_id = selected["account_id"]
        symbols_response = await _request(ws, SYMBOLS_LIST_REQ, {
            "ctidTraderAccountId": int(account_id),
            "includeArchivedSymbols": True,
        }, SYMBOLS_LIST_RES)
        symbol_rows = symbols_response.get("symbol") or []
        symbol_names = {
            str(item.get("symbolId")): str(item.get("symbolName") or item.get("symbolId"))
            for item in symbol_rows if isinstance(item, dict) and item.get("symbolId") is not None
        }
        to_ms = int(time.time() * 1000)
        from_ms = to_ms - days * 24 * 60 * 60 * 1000
        response = await _request(ws, DEAL_LIST_REQ, {
            "ctidTraderAccountId": int(account_id),
            "fromTimestamp": from_ms,
            "toTimestamp": to_ms,
            "maxRows": limit,
        }, DEAL_LIST_RES, timeout=20.0)
        rows = response.get("deal") or []
        if not isinstance(rows, list):
            raise CTraderOpenAPIError("cTrader returned an invalid trade-history response")
        deals = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            money_digits = item.get("moneyDigits", 2)
            side_value = item.get("tradeSide")
            deals.append({
                "deal_id": str(item.get("dealId") or ""),
                "order_id": str(item.get("orderId") or ""),
                "position_id": str(item.get("positionId") or ""),
                "symbol_id": str(item.get("symbolId") or ""),
                "symbol": symbol_names.get(str(item.get("symbolId") or ""), str(item.get("symbolId") or "—")),
                "side": "BUY" if side_value in (1, "1", "BUY") else "SELL",
                "volume_units": _scaled(item.get("volume"), 2),
                "filled_volume_units": _scaled(item.get("filledVolume"), 2),
                "execution_price": item.get("executionPrice"),
                "deal_status": item.get("dealStatus"),
                "create_timestamp_ms": item.get("createTimestamp"),
                "execution_timestamp_ms": item.get("executionTimestamp"),
                "commission": _scaled(item.get("commission"), money_digits),
                "label": str(item.get("label") or "")[:100],
            })
        deals.sort(key=lambda item: int(item.get("execution_timestamp_ms") or 0), reverse=True)
        return {
            "account_id": account_id,
            "environment": "demo",
            "source": "IC Markets cTrader Open API deal history",
            "from_timestamp_ms": from_ms,
            "to_timestamp_ms": to_ms,
            "deals": deals,
            "has_more": bool(response.get("hasMore", False)),
        }
    finally:
        await ws.close()
