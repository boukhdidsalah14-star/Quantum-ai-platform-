"""Customer-isolated paper trading ledger. Never sends orders to a broker."""
from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path
import os

ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
MAX_NOTIONAL_USD = 500.0
MAX_OPEN_TRADES = 5


def _connect():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_paper_db():
    with _connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('long','short')),
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT NOT NULL CHECK(status IN ('open','closed')),
                realized_pnl REAL,
                idempotency_key TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                closed_at INTEGER,
                UNIQUE(customer_id,idempotency_key)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_customer ON paper_trades(customer_id,created_at)")


def open_paper_trade(customer_id: str, symbol: str, side: str, quantity: float,
                     entry_price: float, stop_loss: float | None,
                     take_profit: float | None, idempotency_key: str) -> dict:
    symbol = symbol.upper().strip()
    side = side.lower().strip()
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("Unsupported paper-trading market")
    if side not in {"long", "short"}:
        raise ValueError("Side must be long or short")
    if not (quantity > 0 and entry_price > 0):
        raise ValueError("Quantity and entry price must be positive")
    notional = quantity * entry_price
    if notional > MAX_NOTIONAL_USD:
        raise ValueError("Paper trade exceeds the $500 notional limit")
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValueError("A valid idempotency key is required")
    if stop_loss is not None and stop_loss <= 0:
        raise ValueError("Stop loss must be positive")
    if take_profit is not None and take_profit <= 0:
        raise ValueError("Take profit must be positive")
    if side == "long" and ((stop_loss is not None and stop_loss >= entry_price) or (take_profit is not None and take_profit <= entry_price)):
        raise ValueError("Long trade stop loss must be below entry and take profit above entry")
    if side == "short" and ((stop_loss is not None and stop_loss <= entry_price) or (take_profit is not None and take_profit >= entry_price)):
        raise ValueError("Short trade stop loss must be above entry and take profit below entry")
    now = int(time.time())
    with _connect() as db:
        prior = db.execute("SELECT * FROM paper_trades WHERE customer_id=? AND idempotency_key=?", (customer_id,idempotency_key)).fetchone()
        if prior:
            return dict(prior)
        count = db.execute("SELECT COUNT(*) AS n FROM paper_trades WHERE customer_id=? AND status='open'", (customer_id,)).fetchone()["n"]
        if count >= MAX_OPEN_TRADES:
            raise ValueError("Maximum of five open paper trades reached")
        trade_id = secrets.token_urlsafe(18)
        db.execute("""
            INSERT INTO paper_trades
            (id,customer_id,symbol,side,quantity,entry_price,stop_loss,take_profit,status,idempotency_key,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (trade_id,customer_id,symbol,side,quantity,entry_price,stop_loss,take_profit,"open",idempotency_key,now))
        row = db.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    return dict(row)


def list_paper_trades(customer_id: str) -> list[dict]:
    with _connect() as db:
        rows = db.execute("SELECT * FROM paper_trades WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall()
    return [dict(row) for row in rows]


def close_paper_trade(customer_id: str, trade_id: str, exit_price: float) -> dict | None:
    if exit_price <= 0:
        raise ValueError("Exit price must be positive")
    with _connect() as db:
        row = db.execute("SELECT * FROM paper_trades WHERE id=? AND customer_id=? AND status='open'", (trade_id,customer_id)).fetchone()
        if not row:
            return None
        sign = 1 if row["side"] == "long" else -1
        pnl = (exit_price - row["entry_price"]) * row["quantity"] * sign
        now = int(time.time())
        db.execute("UPDATE paper_trades SET status='closed',exit_price=?,realized_pnl=?,closed_at=? WHERE id=? AND customer_id=? AND status='open'",
                   (exit_price,pnl,now,trade_id,customer_id))
        updated = db.execute("SELECT * FROM paper_trades WHERE id=? AND customer_id=?", (trade_id,customer_id)).fetchone()
    return dict(updated)
