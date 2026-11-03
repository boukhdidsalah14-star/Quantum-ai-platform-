"""Customer-isolated, hard demo-only Deriv binary execution and trade ledger."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import websockets

from app.deriv_demo import _get_demo_ws_url, ACCOUNT_RE
from app.risk import (
    DAILY_LOSS_LIMIT_USD,
    MAX_CONSECUTIVE_LOSSES,
    MAX_OPEN_DEMO_CONTRACTS,
    validate_demo_quote,
)

SYMBOL_RE = re.compile(r"^[A-Za-z0-9_]{2,30}$")
ALLOWED_CONTRACT_TYPES = {"CALL", "PUT"}
TERMINAL_STATUSES = ("won", "lost", "sold", "expired")
OPEN_STATUSES = ("pending", "unknown", "open")


class DerivExecutionError(RuntimeError):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


def _db() -> sqlite3.Connection:
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_deriv_trading_db() -> None:
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS deriv_demo_trades (
          id TEXT PRIMARY KEY,
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          idempotency_key TEXT NOT NULL,
          account_id TEXT NOT NULL,
          symbol TEXT NOT NULL,
          contract_type TEXT NOT NULL CHECK(contract_type IN ('CALL','PUT')),
          stake REAL NOT NULL,
          duration_minutes INTEGER NOT NULL,
          currency TEXT NOT NULL DEFAULT 'USD',
          status TEXT NOT NULL CHECK(status IN ('pending','unknown','open','won','lost','sold','expired','failed')),
          proposal_id TEXT,
          contract_id TEXT,
          buy_price REAL,
          payout REAL,
          profit REAL,
          buy_time INTEGER,
          expiry_time INTEGER,
          settled_at INTEGER,
          longcode TEXT,
          error_message TEXT,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          UNIQUE(customer_id,idempotency_key)
        )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_deriv_demo_customer ON deriv_demo_trades(customer_id,created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_deriv_demo_open ON deriv_demo_trades(status,updated_at)")


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def get_trade(customer_id: str, trade_id: str) -> dict[str, Any] | None:
    with _db() as db:
        return _row(db.execute(
            "SELECT * FROM deriv_demo_trades WHERE customer_id=? AND id=?",
            (customer_id, trade_id),
        ).fetchone())


def list_customer_trades(customer_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.execute(
            "SELECT * FROM deriv_demo_trades WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
            (customer_id, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def list_open_trades() -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.execute(
            "SELECT * FROM deriv_demo_trades WHERE status IN ('pending','unknown','open') ORDER BY created_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def _risk_snapshot(db: sqlite3.Connection, customer_id: str, now: int) -> dict[str, Any]:
    day_start = now - (now % 86400)
    today = db.execute(
        "SELECT COALESCE(SUM(profit),0) AS net FROM deriv_demo_trades "
        "WHERE customer_id=? AND settled_at>=? AND status IN ('won','lost','sold','expired')",
        (customer_id, day_start),
    ).fetchone()
    daily_loss = max(0.0, -float(today["net"] or 0.0))
    recent = db.execute(
        "SELECT profit FROM deriv_demo_trades WHERE customer_id=? "
        "AND status IN ('won','lost','sold','expired') ORDER BY settled_at DESC,id DESC LIMIT 20",
        (customer_id,),
    ).fetchall()
    consecutive = 0
    for item in recent:
        if float(item["profit"] or 0.0) < 0:
            consecutive += 1
        else:
            break
    opened = db.execute(
        "SELECT COUNT(*) AS n FROM deriv_demo_trades WHERE customer_id=? AND status IN ('pending','unknown','open')",
        (customer_id,),
    ).fetchone()
    open_count = int(opened["n"])
    reasons = []
    if daily_loss >= DAILY_LOSS_LIMIT_USD:
        reasons.append("Daily net loss limit reached")
    if consecutive >= MAX_CONSECUTIVE_LOSSES:
        reasons.append("Maximum consecutive losses reached")
    if open_count >= MAX_OPEN_DEMO_CONTRACTS:
        reasons.append("An open or unconfirmed demo contract already exists")
    return {
        "trading_paused": bool(reasons),
        "pause_reasons": reasons,
        "daily_net_loss": round(daily_loss, 2),
        "consecutive_losses": consecutive,
        "open_contracts": open_count,
        "daily_loss_limit": DAILY_LOSS_LIMIT_USD,
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
        "max_open_contracts": MAX_OPEN_DEMO_CONTRACTS,
        "max_stake": 2.0,
        "real_trading_enabled": False,
    }


def risk_snapshot(customer_id: str) -> dict[str, Any]:
    with _db() as db:
        return _risk_snapshot(db, customer_id, int(time.time()))


def reserve_trade(
    customer_id: str,
    account_id: str,
    symbol: str,
    contract_type: str,
    stake: float,
    duration_minutes: int,
    idempotency_key: str,
) -> tuple[dict[str, Any], bool]:
    account_id = str(account_id or "").strip().upper()
    symbol = str(symbol or "").strip()
    contract_type = str(contract_type or "").strip().upper()
    if not ACCOUNT_RE.fullmatch(account_id):
        raise ValueError("Only Deriv virtual demo accounts (VRTC...) can trade")
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("Invalid Deriv market symbol")
    if contract_type not in ALLOWED_CONTRACT_TYPES:
        raise ValueError("Only CALL and PUT binary contracts are enabled")
    stake, duration_minutes = validate_demo_quote(stake, duration_minutes)
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValueError("A valid Idempotency-Key header is required")
    now = int(time.time())
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute(
            "SELECT * FROM deriv_demo_trades WHERE customer_id=? AND idempotency_key=?",
            (customer_id, idempotency_key),
        ).fetchone()
        if prior:
            return dict(prior), True
        risk = _risk_snapshot(db, customer_id, now)
        if risk["trading_paused"]:
            raise ValueError("Demo trading paused: " + "; ".join(risk["pause_reasons"]))
        trade_id = secrets.token_urlsafe(18)
        db.execute("""
          INSERT INTO deriv_demo_trades
          (id,customer_id,idempotency_key,account_id,symbol,contract_type,stake,duration_minutes,
           currency,status,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,'USD','pending',?,?)
        """, (trade_id, customer_id, idempotency_key, account_id, symbol,
              contract_type, stake, duration_minutes, now, now))
        row = db.execute("SELECT * FROM deriv_demo_trades WHERE id=?", (trade_id,)).fetchone()
    return dict(row), False


def mark_trade_failed(customer_id: str, trade_id: str, message: str, uncertain: bool = False) -> None:
    status = "unknown" if uncertain else "failed"
    safe_message = str(message or "Deriv execution failed")[:240]
    with _db() as db:
        db.execute(
            "UPDATE deriv_demo_trades SET status=?,error_message=?,updated_at=? "
            "WHERE customer_id=? AND id=? AND status='pending'",
            (status, safe_message, int(time.time()), customer_id, trade_id),
        )


def mark_trade_open(customer_id: str, trade_id: str, result: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    with _db() as db:
        db.execute("""
          UPDATE deriv_demo_trades SET status='open',proposal_id=?,contract_id=?,buy_price=?,
            payout=?,buy_time=?,expiry_time=?,longcode=?,updated_at=?,error_message=NULL
          WHERE customer_id=? AND id=? AND status='pending'
        """, (
            str(result["proposal_id"]), str(result["contract_id"]),
            float(result["buy_price"]), float(result.get("payout") or 0),
            int(result.get("buy_time") or now), result.get("expiry_time"),
            str(result.get("longcode") or "")[:500], now, customer_id, trade_id,
        ))
        row = db.execute(
            "SELECT * FROM deriv_demo_trades WHERE customer_id=? AND id=?",
            (customer_id, trade_id),
        ).fetchone()
    if not row:
        raise DerivExecutionError("Trade ledger record disappeared after purchase", uncertain=True)
    return dict(row)


def apply_contract_update(customer_id: str, trade_id: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    now = int(time.time())
    is_sold = contract.get("is_sold") in (1, True, "1")
    status = "open"
    profit = None
    settled_at = None
    if is_sold:
        profit = float(contract.get("profit") or 0.0)
        contract_status = str(contract.get("status") or "").lower()
        if contract_status in {"won", "lost", "sold", "expired"}:
            status = contract_status
        else:
            status = "won" if profit > 0 else "lost" if profit < 0 else "sold"
        settled_at = int(contract.get("sell_time") or now)
    with _db() as db:
        db.execute("""
          UPDATE deriv_demo_trades SET status=?,profit=?,settled_at=?,expiry_time=COALESCE(?,expiry_time),
            updated_at=?,error_message=NULL
          WHERE customer_id=? AND id=? AND status IN ('open','unknown')
        """, (
            status, profit, settled_at, contract.get("date_expiry"), now, customer_id, trade_id,
        ))
        row = db.execute(
            "SELECT * FROM deriv_demo_trades WHERE customer_id=? AND id=?",
            (customer_id, trade_id),
        ).fetchone()
    return dict(row) if row else None


async def _ws_request(ws: Any, payload: dict[str, Any], req_id: int, expected: str, timeout: float = 12.0) -> dict[str, Any]:
    await ws.send(json.dumps({**payload, "req_id": req_id}))
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        message = json.loads(raw)
        if message.get("error"):
            error = message["error"]
            raise DerivExecutionError(str(error.get("message") or "Deriv rejected the request")[:240])
        if message.get("req_id") == req_id and message.get("msg_type") == expected:
            return message


async def execute_demo_binary_trade(
    token: str,
    account_id: str,
    app_id: str,
    symbol: str,
    contract_type: str,
    stake: float,
    duration_minutes: int,
) -> dict[str, Any]:
    """Buy exactly one CALL/PUT contract through a verified demo-only OTP URL."""
    account_id = str(account_id or "").strip().upper()
    if not ACCOUNT_RE.fullmatch(account_id):
        raise DerivExecutionError("Only VRTC demo accounts are permitted")
    stake, duration_minutes = validate_demo_quote(stake, duration_minutes)
    symbol = str(symbol or "").strip()
    contract_type = str(contract_type or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol) or contract_type not in ALLOWED_CONTRACT_TYPES:
        raise DerivExecutionError("Invalid symbol or binary contract direction")
    try:
        ws_url = await _get_demo_ws_url(token, account_id, app_id)
        parsed = urlparse(ws_url)
        if parsed.scheme != "wss" or parsed.hostname != "api.derivws.com" or not parsed.path.endswith("/demo"):
            raise DerivExecutionError("Refusing any non-demo Deriv connection")
        async with websockets.connect(
            ws_url, open_timeout=10, close_timeout=3, ping_interval=20,
            ping_timeout=10, max_size=1_000_000,
        ) as ws:
            balance_msg = await _ws_request(ws, {"balance": 1}, 1, "balance")
            balance = balance_msg.get("balance") or {}
            currency = str(balance.get("currency") or "").upper()
            if currency != "USD":
                raise DerivExecutionError("This first demo release supports USD-denominated accounts only")
            proposal_msg = await _ws_request(ws, {
                "proposal": 1,
                "amount": float(stake),
                "basis": "stake",
                "contract_type": contract_type,
                "currency": currency,
                "duration": int(duration_minutes),
                "duration_unit": "m",
                "underlying_symbol": symbol,
            }, 2, "proposal")
            proposal = proposal_msg.get("proposal") or {}
            proposal_id = proposal.get("id")
            ask_price = float(proposal.get("ask_price") or 0)
            if not proposal_id or ask_price <= 0 or ask_price > stake + 0.01:
                raise DerivExecutionError("Deriv returned an invalid or over-limit contract proposal")
            try:
                buy_msg = await _ws_request(ws, {
                    "buy": str(proposal_id),
                    "price": ask_price,
                }, 3, "buy", timeout=15.0)
            except DerivExecutionError:
                raise
            except Exception as exc:
                raise DerivExecutionError(
                    "The buy request may have reached Deriv; check the Deriv portfolio before retrying",
                    uncertain=True,
                ) from exc
            buy = buy_msg.get("buy") or {}
            contract_id = buy.get("contract_id")
            if not contract_id:
                raise DerivExecutionError(
                    "Deriv accepted a buy response without a contract ID; reconcile the account portfolio",
                    uncertain=True,
                )
            return {
                "proposal_id": str(proposal_id),
                "contract_id": str(contract_id),
                "buy_price": float(buy.get("buy_price") or ask_price),
                "payout": float(buy.get("payout") or proposal.get("payout") or 0),
                "buy_time": int(buy.get("purchase_time") or time.time()),
                "expiry_time": int(buy.get("expiry_time")) if buy.get("expiry_time") else None,
                "longcode": str(buy.get("longcode") or proposal.get("longcode") or ""),
                "account_mode": "demo",
                "currency": currency,
            }
    except DerivExecutionError:
        raise
    except asyncio.TimeoutError as exc:
        raise DerivExecutionError("Deriv demo request timed out; verify the portfolio before retrying", uncertain=True) from exc
    except Exception as exc:
        raise DerivExecutionError("Could not complete the Deriv demo order request") from exc


async def get_demo_contract_status(token: str, account_id: str, app_id: str, contract_id: str) -> dict[str, Any]:
    if not ACCOUNT_RE.fullmatch(str(account_id or "").strip().upper()):
        raise DerivExecutionError("Only VRTC demo accounts can be monitored")
    if not str(contract_id).isdigit():
        raise DerivExecutionError("Invalid Deriv contract ID")
    try:
        ws_url = await _get_demo_ws_url(token, account_id, app_id)
        parsed = urlparse(ws_url)
        if parsed.scheme != "wss" or parsed.hostname != "api.derivws.com" or not parsed.path.endswith("/demo"):
            raise DerivExecutionError("Refusing any non-demo Deriv connection")
        async with websockets.connect(
            ws_url, open_timeout=10, close_timeout=3, ping_interval=20,
            ping_timeout=10, max_size=1_000_000,
        ) as ws:
            message = await _ws_request(ws, {
                "proposal_open_contract": 1,
                "contract_id": int(contract_id),
            }, 4, "proposal_open_contract")
            contract = message.get("proposal_open_contract")
            if not isinstance(contract, dict):
                raise DerivExecutionError("Deriv returned an incomplete contract status")
            return contract
    except DerivExecutionError:
        raise
    except Exception as exc:
        raise DerivExecutionError("Could not refresh Deriv demo contract status") from exc
