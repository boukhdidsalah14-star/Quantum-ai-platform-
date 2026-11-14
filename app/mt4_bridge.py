"""Customer-isolated JustMarkets MT4 Expert Advisor bridge.

The bridge stores only a hash of the EA token. It is demo-only by default;
real-account execution is intentionally not implemented by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import time
from pathlib import Path
from typing import Any

from app.database import sqlite3

ALLOWED_SYMBOLS = {
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "XAUUSD",
}
MAX_SYNC_POSITIONS = 100
MAX_ORDER_LOTS = 0.10
MIN_ORDER_LOTS = 0.01
MAX_OPEN_POSITIONS = 3
BRIDGE_FRESH_SECONDS = 60


class BridgeAuthError(RuntimeError):
    """Raised when an EA token or its bound broker account does not match."""


def _db_path() -> Path:
    return Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))


def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _now() -> int:
    return int(time.time())


def _demo_execution_enabled() -> bool:
    return (
        os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
        and os.getenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "").strip().lower() == "true"
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def init_db() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mt4_bridge_accounts (
            customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            account_login TEXT NOT NULL,
            account_server TEXT NOT NULL,
            account_mode TEXT NOT NULL CHECK(account_mode='demo'),
            broker_company TEXT,
            connected INTEGER NOT NULL DEFAULT 0,
            balance REAL,
            equity REAL,
            currency TEXT,
            positions_json TEXT NOT NULL DEFAULT '[]',
            quotes_json TEXT NOT NULL DEFAULT '{}',
            last_seen_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mt4_bridge_commands (
            command_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
            lots REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            broker_ticket INTEGER,
            result_message TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mt4_commands_customer_status
            ON mt4_bridge_commands(customer_id, status, created_at);
        """)


def register_bridge(customer_id: str, account_login: str, account_server: str) -> dict[str, Any]:
    """Create/rotate one demo-only EA token bound to a single MT4 login/server."""
    login = str(account_login or "").strip()
    server = str(account_server or "").strip()
    if not login.isdigit() or not 5 <= len(login) <= 12:
        raise ValueError("Enter the numeric JustMarkets MT4 account login")
    if not server or len(server) > 120 or any(ch in server for ch in "\r\n|"):
        raise ValueError("Enter the exact MT4 server name shown in your terminal")
    token = secrets.token_urlsafe(36)
    now = _now()
    with _connect() as db:
        db.execute("""
            INSERT INTO mt4_bridge_accounts
                (customer_id, token_hash, account_login, account_server, account_mode,
                 connected, positions_json, quotes_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'demo', 0, '[]', '{}', ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                token_hash=excluded.token_hash,
                account_login=excluded.account_login,
                account_server=excluded.account_server,
                account_mode='demo',
                broker_company=NULL,
                connected=0,
                balance=NULL,
                equity=NULL,
                currency=NULL,
                positions_json='[]',
                quotes_json='{}',
                last_seen_at=NULL,
                updated_at=excluded.updated_at
        """, (customer_id, _token_hash(token), login, server, now, now))
        db.execute("DELETE FROM mt4_bridge_commands WHERE customer_id=? AND status IN ('pending','delivered')",
                   (customer_id,))
    return {
        "connected": False,
        "broker": "justmarkets",
        "platform": "mt4",
        "mode": "demo",
        "account_login": login,
        "account_server": server,
        "bridge_token": token,
        "token_shown_once": True,
        "execution_enabled": False,
    }


def _authenticate(db, token: str, account_login: str, account_server: str, company: str):
    if not token or len(token) > 200:
        raise BridgeAuthError("Missing or invalid bridge token")
    row = db.execute("SELECT * FROM mt4_bridge_accounts WHERE token_hash=?", (_token_hash(token),)).fetchone()
    if not row:
        raise BridgeAuthError("Bridge token is not registered")
    if not hmac.compare_digest(str(row["account_login"]), str(account_login or "")):
        raise BridgeAuthError("MT4 account login does not match the registered account")
    if not hmac.compare_digest(str(row["account_server"]), str(account_server or "")):
        raise BridgeAuthError("MT4 server does not match the registered account")
    company_name = str(company or "").lower()
    if "justmarkets" not in company_name and "just global markets" not in company_name:
        raise BridgeAuthError("This bridge token is restricted to a JustMarkets terminal")
    if row["account_mode"] != "demo":
        raise BridgeAuthError("Only a demo MT4 account is supported")
    return row


def _finite(value: Any, name: str, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"Invalid {name}")
    return number


def _clean_positions(positions: Any) -> list[dict[str, Any]]:
    if not isinstance(positions, list) or len(positions) > MAX_SYNC_POSITIONS:
        raise ValueError("Positions must be a list containing no more than 100 open trades")
    cleaned = []
    for item in positions:
        if not isinstance(item, dict):
            raise ValueError("Invalid MT4 position record")
        symbol = str(item.get("symbol") or "").strip().upper()
        side = str(item.get("side") or "").strip().upper()
        if symbol not in ALLOWED_SYMBOLS or side not in {"BUY", "SELL"}:
            continue
        ticket = str(item.get("ticket") or "").strip()
        if not ticket.isdigit() or len(ticket) > 24:
            continue
        lots = _finite(item.get("lots"), "position lots", 0.00001)
        cleaned.append({
            "ticket": ticket,
            "symbol": symbol,
            "side": side,
            "lots": lots,
            "open_price": _finite(item.get("open_price"), "open price", 0.00000001),
            "current_price": _finite(item.get("current_price"), "current price", 0.00000001),
            "stop_loss": _finite(item.get("stop_loss", 0), "stop loss", 0),
            "take_profit": _finite(item.get("take_profit", 0), "take profit", 0),
            "profit": _finite(item.get("profit", 0), "floating profit"),
            "swap": _finite(item.get("swap", 0), "swap"),
            "commission": _finite(item.get("commission", 0), "commission"),
            "open_time": int(item.get("open_time") or 0),
            "magic": int(item.get("magic") or 0),
        })
    return cleaned


def _clean_quotes(quotes: Any) -> dict[str, dict[str, float]]:
    if not isinstance(quotes, dict):
        raise ValueError("MT4 quotes must be an object")
    cleaned = {}
    for symbol, quote in quotes.items():
        name = str(symbol).strip().upper()
        if name not in ALLOWED_SYMBOLS or not isinstance(quote, dict):
            continue
        bid = _finite(quote.get("bid"), "bid", 0.00000001)
        ask = _finite(quote.get("ask"), "ask", 0.00000001)
        if ask < bid:
            continue
        cleaned[name] = {"bid": bid, "ask": ask}
    return cleaned


def sync_snapshot(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid MT4 sync payload")
    login = str(payload.get("account_login") or "")
    server = str(payload.get("account_server") or "")
    company = str(payload.get("company") or "")
    positions = _clean_positions(payload.get("positions", []))
    quotes = _clean_quotes(payload.get("quotes", {}))
    balance = _finite(payload.get("balance"), "account balance", 0)
    equity = _finite(payload.get("equity"), "account equity", 0)
    currency = str(payload.get("currency") or "").upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Invalid MT4 account currency")
    now = _now()
    with _connect() as db:
        row = _authenticate(db, token, login, server, company)
        db.execute("""
            UPDATE mt4_bridge_accounts
            SET connected=1, broker_company=?, balance=?, equity=?, currency=?,
                positions_json=?, quotes_json=?, last_seen_at=?, updated_at=?
            WHERE customer_id=?
        """, (company[:120], balance, equity, currency,
              json.dumps(positions, separators=(",", ":")),
              json.dumps(quotes, separators=(",", ":")), now, now, row["customer_id"]))
    return {"ok": True, "connected": True, "positions_received": len(positions), "quotes_received": len(quotes)}


def bridge_status(customer_id: str) -> dict[str, Any]:
    with _connect() as db:
        row = db.execute("SELECT * FROM mt4_bridge_accounts WHERE customer_id=?", (customer_id,)).fetchone()
    if not row:
        return {"connected": False, "registered": False, "broker": "justmarkets", "platform": "mt4", "mode": "demo", "positions": []}
    last_seen = int(row["last_seen_at"] or 0)
    connected = bool(row["connected"] and _now() - last_seen <= BRIDGE_FRESH_SECONDS)
    return {
        "connected": connected,
        "registered": True,
        "broker": "justmarkets",
        "platform": "mt4",
        "mode": "demo",
        "account_login": row["account_login"],
        "account_server": row["account_server"],
        "broker_company": row["broker_company"],
        "balance": row["balance"],
        "equity": row["equity"],
        "currency": row["currency"],
        "positions": json.loads(row["positions_json"] or "[]") if connected else [],
        "quotes": json.loads(row["quotes_json"] or "{}") if connected else {},
        "last_seen_at": last_seen or None,
        "execution_enabled": False,
    }


def delete_bridge(customer_id: str) -> bool:
    with _connect() as db:
        db.execute("DELETE FROM mt4_bridge_commands WHERE customer_id=?", (customer_id,))
        result = db.execute("DELETE FROM mt4_bridge_accounts WHERE customer_id=?", (customer_id,))
        return result.rowcount > 0


def enqueue_demo_order(customer_id: str, symbol: str, side: str, lots: float,
                       stop_loss: float, take_profit: float) -> dict[str, Any]:
    if not _demo_execution_enabled():
        raise PermissionError("MT4 demo order execution is locked until the demo bridge is explicitly enabled")
    symbol = str(symbol or "").strip().upper()
    side = str(side or "").strip().upper()
    if symbol not in ALLOWED_SYMBOLS or side not in {"BUY", "SELL"}:
        raise ValueError("Unsupported MT4 symbol or side")
    lots = _finite(lots, "order lots", MIN_ORDER_LOTS)
    if lots > MAX_ORDER_LOTS:
        raise ValueError(f"Demo order size cannot exceed {MAX_ORDER_LOTS:.2f} lots")
    stop_loss = _finite(stop_loss, "stop loss", 0.00000001)
    take_profit = _finite(take_profit, "take profit", 0.00000001)
    snapshot = bridge_status(customer_id)
    if not snapshot.get("connected"):
        raise ValueError("The JustMarkets MT4 Expert Advisor is not connected")
    if snapshot.get("mode") != "demo":
        raise ValueError("Only demo orders are supported")
    quote = snapshot.get("quotes", {}).get(symbol)
    if not quote:
        raise ValueError("The MT4 bridge has not supplied a current quote for this symbol")
    reference = quote["ask"] if side == "BUY" else quote["bid"]
    if side == "BUY" and not (stop_loss < reference < take_profit):
        raise ValueError("For BUY orders, stop loss must be below and take profit above the current price")
    if side == "SELL" and not (take_profit < reference < stop_loss):
        raise ValueError("For SELL orders, take profit must be below and stop loss above the current price")
    balance = float(snapshot.get("balance") or 0)
    equity = float(snapshot.get("equity") or 0)
    daily_loss_limit = float(os.getenv("QUANTUM_MT4_MAX_EQUITY_DRAWDOWN_PCT", "10"))
    if balance > 0 and (balance - equity) / balance * 100 >= daily_loss_limit:
        raise PermissionError("MT4 demo equity drawdown guard reached; new orders are paused")
    if len(snapshot.get("positions", [])) >= MAX_OPEN_POSITIONS:
        raise PermissionError("Maximum of three open MT4 positions reached")
    command_id = "qai_" + secrets.token_urlsafe(15)
    now = _now()
    with _connect() as db:
        db.execute("""
            INSERT INTO mt4_bridge_commands
                (command_id, customer_id, symbol, side, lots, stop_loss, take_profit,
                 status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (command_id, customer_id, symbol, side, lots, stop_loss, take_profit, now, now))
    return {"command_id": command_id, "status": "pending", "execution": "demo_only", "broker_order_sent": False}


def pending_commands(token: str, account_login: str, account_server: str, company: str) -> list[dict[str, Any]]:
    now = _now()
    with _connect() as db:
        bridge = _authenticate(db, token, account_login, account_server, company)
        if os.getenv("QUANTUM_MT4_DEMO_EXECUTION_ENABLED", "").strip().lower() != "true":
            return []
        db.execute("""
            UPDATE mt4_bridge_commands
            SET status='expired', result_message='Command expired before MT4 delivery', updated_at=?
            WHERE customer_id=? AND status IN ('pending','delivered') AND created_at<?
        """, (now, bridge["customer_id"], now - 60))
        rows = db.execute("""
            SELECT * FROM mt4_bridge_commands
            WHERE customer_id=? AND created_at>=?
              AND (status='pending' OR (status='delivered' AND updated_at<?))
            ORDER BY created_at LIMIT 10
        """, (bridge["customer_id"], now - 60, now - 30)).fetchall()
        for row in rows:
            db.execute("UPDATE mt4_bridge_commands SET status='delivered', updated_at=? WHERE command_id=?",
                       (now, row["command_id"]))
    return [{
        "command_id": row["command_id"], "symbol": row["symbol"], "side": row["side"],
        "lots": row["lots"], "stop_loss": row["stop_loss"], "take_profit": row["take_profit"],
    } for row in rows]


def command_result(token: str, account_login: str, account_server: str, company: str,
                   command_id: str, status: str, ticket: int | None, message: str) -> dict[str, Any]:
    status = str(status or "").lower()
    if status not in {"executed", "failed"}:
        raise ValueError("Command result must be executed or failed")
    now = _now()
    with _connect() as db:
        bridge = _authenticate(db, token, account_login, account_server, company)
        row = db.execute("""
            SELECT * FROM mt4_bridge_commands WHERE command_id=? AND customer_id=?
        """, (command_id, bridge["customer_id"])).fetchone()
        if not row:
            raise ValueError("MT4 command not found")
        if row["status"] in {"executed", "failed"}:
            return {"ok": True, "duplicate": True, "status": row["status"]}
        db.execute("""
            UPDATE mt4_bridge_commands SET status=?, broker_ticket=?, result_message=?, updated_at=?
            WHERE command_id=? AND customer_id=?
        """, (status, int(ticket or 0) if status == "executed" else None,
              str(message or "")[:240], now, command_id, bridge["customer_id"]))
    return {"ok": True, "duplicate": False, "status": status}


def order_status(customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), 100))
    with _connect() as db:
        rows = db.execute("""
            SELECT command_id, symbol, side, lots, stop_loss, take_profit, status,
                   broker_ticket, result_message, created_at, updated_at
            FROM mt4_bridge_commands WHERE customer_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (customer_id, bounded)).fetchall()
    return [dict(row) for row in rows]
