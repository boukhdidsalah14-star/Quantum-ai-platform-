"""Olymp Trade paper ledger with customer-configured balance and 10% daily loss cap.

This module never connects to Olymp Trade or sends broker orders.
"""
from __future__ import annotations

import math
import os
import secrets
import sqlite3
import time
from pathlib import Path

MAX_OPEN_TRADES = 3
DAILY_LOSS_LIMIT_PERCENT = 10.0
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
        db.execute("""CREATE TABLE IF NOT EXISTS olymp_paper_settings (
            customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
            account_balance REAL NOT NULL CHECK(account_balance > 0),
            updated_at INTEGER NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS olymp_paper_trades (
            id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL, price_source TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
            stake REAL NOT NULL, expiry_minutes INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL,
            status TEXT NOT NULL CHECK(status IN ('open','settled','cancelled')),
            result TEXT, pnl REAL, idempotency_key TEXT NOT NULL, created_at INTEGER NOT NULL, settled_at INTEGER,
            UNIQUE(customer_id,idempotency_key)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_olymp_paper_customer ON olymp_paper_trades(customer_id,created_at)")


def set_account_balance(customer_id: str, account_balance: float) -> dict:
    try:
        balance = float(account_balance)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid account balance") from exc
    if not math.isfinite(balance) or balance <= 0 or balance > 1_000_000_000:
        raise ValueError("Account balance must be greater than zero and no more than 1,000,000,000")
    now = int(time.time())
    with _connect() as db:
        db.execute("""INSERT INTO olymp_paper_settings(customer_id,account_balance,updated_at)
            VALUES(?,?,?) ON CONFLICT(customer_id) DO UPDATE SET
            account_balance=excluded.account_balance,updated_at=excluded.updated_at""",
            (customer_id, balance, now))
    return get_risk_snapshot(customer_id)


def get_risk_snapshot(customer_id: str) -> dict:
    now = int(time.time())
    with _connect() as db:
        settings = db.execute("SELECT account_balance FROM olymp_paper_settings WHERE customer_id=?",
                              (customer_id,)).fetchone()
        if not settings:
            return {"configured": False, "account_balance": None,
                    "daily_loss_limit_percent": DAILY_LOSS_LIMIT_PERCENT,
                    "daily_loss_limit": None, "daily_loss": 0.0,
                    "remaining_loss_allowance": None, "open_trades": 0}
        balance = float(settings["account_balance"])
        stats = db.execute("""SELECT
            SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count,
            COALESCE(SUM(CASE WHEN status='settled' AND pnl<0 AND settled_at>=? THEN -pnl ELSE 0 END),0) AS daily_loss,
            COALESCE(SUM(CASE WHEN status='open' THEN stake ELSE 0 END),0) AS open_stake
            FROM olymp_paper_trades WHERE customer_id=?""", (now-86400, customer_id)).fetchone()
    limit = round(balance * DAILY_LOSS_LIMIT_PERCENT / 100.0, 2)
    loss = round(float(stats["daily_loss"]), 2)
    return {"configured": True, "account_balance": balance,
            "daily_loss_limit_percent": DAILY_LOSS_LIMIT_PERCENT,
            "daily_loss_limit": limit, "daily_loss": loss,
            "remaining_loss_allowance": round(max(0.0, limit-loss), 2),
            "open_trades": int(stats["open_count"] or 0),
            "open_stake": round(float(stats["open_stake"] or 0), 2),
            "trading_paused": loss >= limit}


def open_trade(customer_id, symbol, direction, stake, expiry_minutes, entry_price, idempotency_key, price_source):
    symbol, direction = symbol.strip().upper(), direction.strip().upper()
    try:
        stake, entry_price, expiry_minutes = float(stake), float(entry_price), int(expiry_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid stake, expiry, or entry price") from exc
    if not symbol or len(symbol) > 30: raise ValueError("Invalid asset symbol")
    if direction not in {"CALL", "PUT"}: raise ValueError("Direction must be CALL or PUT")
    if not math.isfinite(stake) or stake < 0.1: raise ValueError("Trade amount must be at least $0.10")
    if expiry_minutes not in ALLOWED_EXPIRIES: raise ValueError("Expiry must be 1, 5, 15, 30, or 60 minutes")
    if not math.isfinite(entry_price) or entry_price <= 0: raise ValueError("Entry price must be positive")
    if not idempotency_key or len(idempotency_key) > 100: raise ValueError("A valid idempotency key is required")
    price_source = str(price_source).strip()
    if not price_source or len(price_source) > 80: raise ValueError("A valid reference-price source is required")
    now = int(time.time())
    with _connect() as db:
        prior = db.execute("SELECT * FROM olymp_paper_trades WHERE customer_id=? AND idempotency_key=?",
                           (customer_id,idempotency_key)).fetchone()
        if prior: return dict(prior)
        settings = db.execute("SELECT account_balance FROM olymp_paper_settings WHERE customer_id=?",
                              (customer_id,)).fetchone()
        if not settings:
            raise ValueError("Set your paper account balance before opening a position")
        balance = float(settings["account_balance"])
        stats = db.execute("""SELECT SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count,
            COALESCE(SUM(CASE WHEN status='settled' AND pnl<0 AND settled_at>=? THEN -pnl ELSE 0 END),0) AS daily_loss,
            COALESCE(SUM(CASE WHEN status='open' THEN stake ELSE 0 END),0) AS open_stake
            FROM olymp_paper_trades WHERE customer_id=?""", (now-86400,customer_id)).fetchone()
        loss_limit = balance * DAILY_LOSS_LIMIT_PERCENT / 100.0
        if float(stats["daily_loss"]) >= loss_limit:
            raise ValueError("Daily loss limit reached (10% of your configured balance); new positions are paused")
        if stake > balance:
            raise ValueError("Trade amount cannot exceed your configured account balance")
        if float(stats["open_stake"] or 0) + stake > balance:
            raise ValueError("Combined open trade amounts cannot exceed your configured account balance")
        if (stats["open_count"] or 0) >= MAX_OPEN_TRADES:
            raise ValueError("Maximum of three open Olymp Trade paper positions reached")
        trade_id = secrets.token_urlsafe(18)
        db.execute("""INSERT INTO olymp_paper_trades
            (id,customer_id,symbol,price_source,direction,stake,expiry_minutes,entry_price,status,idempotency_key,created_at)
            VALUES(?,?,?,?,?,?,?,?,'open',?,?)""",
            (trade_id,customer_id,symbol,price_source,direction,stake,expiry_minutes,entry_price,idempotency_key,now))
        return dict(db.execute("SELECT * FROM olymp_paper_trades WHERE id=?", (trade_id,)).fetchone())


def list_trades(customer_id):
    with _connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM olymp_paper_trades WHERE customer_id=? ORDER BY created_at DESC",
            (customer_id,)).fetchall()]


def settle_trade(customer_id, trade_id, exit_price, payout_rate=0.82):
    try:
        exit_price, payout_rate = float(exit_price), float(payout_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid exit price or payout rate") from exc
    if not math.isfinite(exit_price) or exit_price <= 0: raise ValueError("Exit price must be positive")
    if not math.isfinite(payout_rate) or not 0 < payout_rate <= 1: raise ValueError("Payout rate must be greater than zero and at most one")
    with _connect() as db:
        row = db.execute("SELECT * FROM olymp_paper_trades WHERE id=? AND customer_id=? AND status='open'",
                         (trade_id,customer_id)).fetchone()
        if not row: return None
        if int(time.time()) < int(row["created_at"]) + int(row["expiry_minutes"]) * 60:
            raise ValueError("Paper position has not reached its selected expiry yet")
        if exit_price == row["entry_price"]: result, pnl = "draw", 0.0
        else:
            won = (exit_price > row["entry_price"] and row["direction"]=="CALL") or (exit_price < row["entry_price"] and row["direction"]=="PUT")
            result, pnl = ("win", row["stake"]*payout_rate) if won else ("loss", -row["stake"])
        now = int(time.time())
        db.execute("""UPDATE olymp_paper_trades SET exit_price=?,status='settled',result=?,pnl=?,settled_at=?
            WHERE id=? AND customer_id=? AND status='open'""",
            (exit_price,result,pnl,now,trade_id,customer_id))
        return dict(db.execute("SELECT * FROM olymp_paper_trades WHERE id=? AND customer_id=?",
                               (trade_id,customer_id)).fetchone())
