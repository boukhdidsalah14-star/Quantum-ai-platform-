"""Customer-isolated server-side risk controls for cTrader demo execution.

Daily loss is measured from cTrader account balance (realized P/L only).
Floating/unrealized P&L is excluded until a verified equity feed is implemented.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os, time, uuid
from pathlib import Path
from app.database import sqlite3

class CTraderRiskBlocked(RuntimeError):
    pass

def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def _today():
    return datetime.now(timezone.utc).date().isoformat()

def init_db():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_risk_settings (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          max_daily_loss_pct REAL NOT NULL DEFAULT 10.0,
          max_lots REAL NOT NULL DEFAULT 0.01,
          max_open_positions INTEGER NOT NULL DEFAULT 3,
          emergency_stop INTEGER NOT NULL DEFAULT 0,
          updated_at INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_risk_daily (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL, day_key TEXT NOT NULL,
          start_balance REAL NOT NULL, latest_balance REAL NOT NULL, updated_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id, account_id, day_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_risk_reservations (
          reservation_id TEXT PRIMARY KEY,
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL, created_at INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_risk_positions (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL, position_id TEXT NOT NULL, updated_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id, account_id, position_id))""")

def _ensure_settings(db, customer_id):
    db.execute("INSERT OR IGNORE INTO ctrader_risk_settings (customer_id, updated_at) VALUES (?, ?)",
               (customer_id, int(time.time())))
    return db.execute("SELECT * FROM ctrader_risk_settings WHERE customer_id=?",
                      (customer_id,)).fetchone()

def get_settings(customer_id):
    with _db() as db:
        row = _ensure_settings(db, customer_id)
    return {"max_daily_loss_pct": float(row["max_daily_loss_pct"]),
            "max_lots": float(row["max_lots"]),
            "max_open_positions": int(row["max_open_positions"]),
            "emergency_stop": bool(row["emergency_stop"]), "hard_max_lots": 0.01}

def update_settings(customer_id, max_daily_loss_pct, max_lots, max_open_positions):
    loss, lots, positions = float(max_daily_loss_pct), float(max_lots), int(max_open_positions)
    if not 1 <= loss <= 10:
        raise ValueError("Daily loss limit must be between 1% and 10%")
    if not 0.001 <= lots <= 0.01:
        raise ValueError("Maximum trade size must be between 0.001 and 0.01 lots")
    if not 1 <= positions <= 3:
        raise ValueError("Maximum open positions must be between 1 and 3")
    with _db() as db:
        db.execute("""INSERT INTO ctrader_risk_settings
          (customer_id,max_daily_loss_pct,max_lots,max_open_positions,emergency_stop,updated_at)
          VALUES (?,?,?,?,0,?) ON CONFLICT(customer_id) DO UPDATE SET
          max_daily_loss_pct=excluded.max_daily_loss_pct,max_lots=excluded.max_lots,
          max_open_positions=excluded.max_open_positions,updated_at=excluded.updated_at""",
          (customer_id, loss, lots, positions, int(time.time())))
    return get_settings(customer_id)

def set_emergency_stop(customer_id, enabled):
    with _db() as db:
        _ensure_settings(db, customer_id)
        db.execute("UPDATE ctrader_risk_settings SET emergency_stop=?,updated_at=? WHERE customer_id=?",
                   (1 if enabled else 0, int(time.time()), customer_id))
    return get_settings(customer_id)

def record_account_sync(customer_id, account_id, balance):
    value = float(balance or 0)
    if value <= 0:
        return
    with _db() as db:
        db.execute("""INSERT INTO ctrader_risk_daily
          (customer_id,account_id,day_key,start_balance,latest_balance,updated_at)
          VALUES (?,?,?,?,?,?) ON CONFLICT(customer_id,account_id,day_key) DO UPDATE SET
          latest_balance=excluded.latest_balance,updated_at=excluded.updated_at""",
          (customer_id, str(account_id), _today(), value, value, int(time.time())))

def sync_open_positions(customer_id, account_id, position_ids):
    ids = [str(value) for value in position_ids if str(value).isdigit()]
    with _db() as db:
        db.execute("DELETE FROM ctrader_risk_positions WHERE customer_id=? AND account_id=?",
                   (customer_id, str(account_id)))
        for position_id in ids:
            db.execute("""INSERT OR IGNORE INTO ctrader_risk_positions
              (customer_id,account_id,position_id,updated_at) VALUES (?,?,?,?)""",
              (customer_id,str(account_id),position_id,int(time.time())))


def record_open_position(customer_id, account_id, position_id):
    if not str(position_id or "").isdigit():
        return
    with _db() as db:
        db.execute("""INSERT OR IGNORE INTO ctrader_risk_positions
          (customer_id,account_id,position_id,updated_at) VALUES (?,?,?,?)""",
          (customer_id,str(account_id),str(position_id),int(time.time())))


def reserve_entry(customer_id, account_id, balance, open_positions_count, lots):
    value, size = float(balance or 0), float(lots)
    if value <= 0:
        raise CTraderRiskBlocked("Risk check unavailable: cTrader returned no valid account balance")
    now, today, token = int(time.time()), _today(), uuid.uuid4().hex
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        settings = _ensure_settings(db, customer_id)
        if bool(settings["emergency_stop"]):
            raise CTraderRiskBlocked("Emergency stop is active: new demo entries are blocked")
        max_lots = float(settings["max_lots"])
        if size > max_lots + 1e-9:
            raise CTraderRiskBlocked(f"Trade size exceeds your configured limit of {max_lots:g} lots")
        db.execute("""INSERT INTO ctrader_risk_daily
          (customer_id,account_id,day_key,start_balance,latest_balance,updated_at)
          VALUES (?,?,?,?,?,?) ON CONFLICT(customer_id,account_id,day_key) DO UPDATE SET
          latest_balance=excluded.latest_balance,updated_at=excluded.updated_at""",
          (customer_id, str(account_id), today, value, value, now))
        day = db.execute("""SELECT start_balance FROM ctrader_risk_daily
          WHERE customer_id=? AND account_id=? AND day_key=?""",
          (customer_id, str(account_id), today)).fetchone()
        start = float(day["start_balance"])
        loss = max(0.0, (start-value)/start*100.0) if start > 0 else 0.0
        limit = float(settings["max_daily_loss_pct"])
        if loss >= limit:
            raise CTraderRiskBlocked(f"Daily loss limit reached ({loss:.2f}% of the day's starting balance); new entries are blocked")
        db.execute("DELETE FROM ctrader_risk_reservations WHERE created_at < ?", (now-120,))
        tracked = db.execute("""SELECT COUNT(*) AS total FROM ctrader_risk_positions
          WHERE customer_id=? AND account_id=?""", (customer_id,str(account_id))).fetchone()
        pending = db.execute("""SELECT COUNT(*) AS total FROM ctrader_risk_reservations
          WHERE customer_id=? AND account_id=?""", (customer_id,str(account_id))).fetchone()
        occupied = max(int(open_positions_count), int(tracked["total"])) + int(pending["total"])
        maximum = int(settings["max_open_positions"])
        if occupied >= maximum:
            raise CTraderRiskBlocked(f"Maximum of {maximum} open positions reached")
        db.execute("INSERT INTO ctrader_risk_reservations VALUES (?,?,?,?)",
                   (token,customer_id,str(account_id),now))
    return token

def release_entry(reservation_id):
    if reservation_id:
        with _db() as db:
            db.execute("DELETE FROM ctrader_risk_reservations WHERE reservation_id=?", (reservation_id,))

def get_status(customer_id, account_id=None):
    settings = get_settings(customer_id)
    day = None
    if account_id:
        with _db() as db:
            day = db.execute("""SELECT start_balance,latest_balance,updated_at FROM ctrader_risk_daily
              WHERE customer_id=? AND account_id=? AND day_key=?""",
              (customer_id,str(account_id),_today())).fetchone()
    start = float(day["start_balance"]) if day else None
    latest = float(day["latest_balance"]) if day else None
    loss = max(0.0,(start-latest)/start*100.0) if start and latest is not None else None
    return {**settings,"account_id":str(account_id) if account_id else None,
            "daily_start_balance":start,"latest_synced_balance":latest,
            "daily_loss_pct":round(loss,4) if loss is not None else None,
            "daily_loss_measurement":"realized_balance_only",
            "updated_at":int(day["updated_at"]) if day else None,
            "server_enforced":True,
            "new_entries_blocked":settings["emergency_stop"] or
                (loss is not None and loss >= settings["max_daily_loss_pct"])}
