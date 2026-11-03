"""Olymp Trade paper ledger. No broker connection or order placement."""
from __future__ import annotations
import secrets, sqlite3, time, os
from pathlib import Path

MAX_STAKE_USD = 2.0
MAX_OPEN_TRADES = 3
DAILY_LOSS_LIMIT_USD = 10.0
ALLOWED_EXPIRIES = {1, 5, 15, 30, 60}

def _connect():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS olymp_paper_trades (
            id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
            stake REAL NOT NULL, expiry_minutes INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL,
            status TEXT NOT NULL CHECK(status IN ('open','settled','cancelled')),
            result TEXT, pnl REAL, idempotency_key TEXT NOT NULL, created_at INTEGER NOT NULL, settled_at INTEGER,
            UNIQUE(customer_id,idempotency_key))""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_olymp_paper_customer ON olymp_paper_trades(customer_id,created_at)")

def open_trade(customer_id, symbol, direction, stake, expiry_minutes, entry_price, idempotency_key):
    symbol, direction = symbol.strip().upper(), direction.strip().upper()
    stake, entry_price, expiry_minutes = float(stake), float(entry_price), int(expiry_minutes)
    if not symbol or len(symbol) > 30: raise ValueError("Invalid asset symbol")
    if direction not in {"CALL", "PUT"}: raise ValueError("Direction must be CALL or PUT")
    if not 0.1 <= stake <= MAX_STAKE_USD: raise ValueError("Paper stake must be between 0.10 and 2.00 USD")
    if expiry_minutes not in ALLOWED_EXPIRIES: raise ValueError("Expiry must be 1, 5, 15, 30, or 60 minutes")
    if not entry_price > 0: raise ValueError("Entry price must be positive")
    if not idempotency_key or len(idempotency_key) > 100: raise ValueError("A valid idempotency key is required")
    now = int(time.time())
    with _connect() as db:
        prior = db.execute("SELECT * FROM olymp_paper_trades WHERE customer_id=? AND idempotency_key=?", (customer_id,idempotency_key)).fetchone()
        if prior: return dict(prior)
        stats = db.execute("""SELECT SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count,
            COALESCE(SUM(CASE WHEN status='settled' AND pnl<0 AND settled_at>=? THEN -pnl ELSE 0 END),0) AS daily_loss
            FROM olymp_paper_trades WHERE customer_id=?""", (now-86400,customer_id)).fetchone()
        if (stats["open_count"] or 0) >= MAX_OPEN_TRADES: raise ValueError("Maximum of three open Olymp Trade paper positions reached")
        if float(stats["daily_loss"]) >= DAILY_LOSS_LIMIT_USD: raise ValueError("Daily paper loss limit reached")
        trade_id = secrets.token_urlsafe(18)
        db.execute("""INSERT INTO olymp_paper_trades (id,customer_id,symbol,direction,stake,expiry_minutes,entry_price,status,idempotency_key,created_at)
            VALUES(?,?,?,?,?,?,?,'open',?,?)""", (trade_id,customer_id,symbol,direction,stake,expiry_minutes,entry_price,idempotency_key,now))
        return dict(db.execute("SELECT * FROM olymp_paper_trades WHERE id=?", (trade_id,)).fetchone())

def list_trades(customer_id):
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM olymp_paper_trades WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall()]

def settle_trade(customer_id, trade_id, exit_price, payout_rate=0.82):
    exit_price, payout_rate = float(exit_price), float(payout_rate)
    if exit_price <= 0: raise ValueError("Exit price must be positive")
    if not 0 < payout_rate <= 1: raise ValueError("Payout rate must be greater than zero and at most one")
    with _connect() as db:
        row = db.execute("SELECT * FROM olymp_paper_trades WHERE id=? AND customer_id=? AND status='open'", (trade_id,customer_id)).fetchone()
        if not row: return None
        if exit_price == row["entry_price"]: result, pnl = "draw", 0.0
        else:
            won = (exit_price > row["entry_price"] and row["direction"]=="CALL") or (exit_price < row["entry_price"] and row["direction"]=="PUT")
            result, pnl = ("win", row["stake"]*payout_rate) if won else ("loss", -row["stake"])
        now = int(time.time())
        db.execute("UPDATE olymp_paper_trades SET exit_price=?,status='settled',result=?,pnl=?,settled_at=? WHERE id=? AND customer_id=? AND status='open'", (exit_price,result,pnl,now,trade_id,customer_id))
        return dict(db.execute("SELECT * FROM olymp_paper_trades WHERE id=? AND customer_id=?", (trade_id,customer_id)).fetchone())
