"""Per-customer, per-account trading consent for cTrader.

Demo permission requires an explicit customer acknowledgement. Live permission
is deliberately never granted by this module; global broker/app approval and
separate live safeguards remain mandatory.
"""
from __future__ import annotations
import os, time
from pathlib import Path
from app.database import sqlite3

class CTraderPermissionError(RuntimeError):
    pass

def _db():
    path=Path(os.getenv("QUANTUM_DB_PATH","data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(path),timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS ctrader_customer_permissions (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          account_id TEXT NOT NULL,
          environment TEXT NOT NULL CHECK(environment IN ('demo','live')),
          enabled INTEGER NOT NULL DEFAULT 0,
          acknowledged_at INTEGER,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id,account_id,environment))""")

def set_demo_permission(customer_id, account_id, enabled, acknowledged):
    if not str(account_id or "").isdigit():
        raise ValueError("Select your cTrader demo account first")
    if enabled and not acknowledged:
        raise ValueError("You must acknowledge the demo-trading risks before enabling trading")
    init_db()
    now=int(time.time())
    with _db() as db:
        db.execute("""INSERT INTO ctrader_customer_permissions
          (customer_id,account_id,environment,enabled,acknowledged_at,updated_at)
          VALUES (?,?,'demo',?,?,?)
          ON CONFLICT(customer_id,account_id,environment) DO UPDATE SET
          enabled=excluded.enabled,acknowledged_at=excluded.acknowledged_at,
          updated_at=excluded.updated_at""",
          (customer_id,str(account_id),1 if enabled else 0,now if enabled else None,now))
    return get_permission(customer_id,account_id)

def get_permission(customer_id, account_id):
    if not account_id:
        return {"account_id":None,"environment":"demo","demo_trading_authorized":False,
                "live_trading_authorized":False,"live_trading_available":False}
    init_db()
    with _db() as db:
        row=db.execute("""SELECT enabled,acknowledged_at,updated_at
          FROM ctrader_customer_permissions WHERE customer_id=? AND account_id=?
          AND environment='demo'""",(customer_id,str(account_id))).fetchone()
    enabled=bool(row and row["enabled"])
    return {"account_id":str(account_id),"environment":"demo",
            "demo_trading_authorized":enabled,"acknowledged_at":int(row["acknowledged_at"]) if row and row["acknowledged_at"] else None,
            "updated_at":int(row["updated_at"]) if row else None,
            "live_trading_authorized":False,"live_trading_available":False}

def require_demo_permission(customer_id, account_id):
    permission=get_permission(customer_id,account_id)
    if not permission["demo_trading_authorized"]:
        raise CTraderPermissionError("Demo trading is not authorized for this customer and account. Enable it in Account Authorization first.")
    return permission
