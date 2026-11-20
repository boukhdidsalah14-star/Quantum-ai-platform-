"""Explicit per-customer MEXC USD-M live-trading authorization.

Authorization is bound to the currently saved API credential version. Replacing
an API key invalidates the previous consent. This module never stores secrets.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from app.database import sqlite3


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS mexc_live_permissions_v2 (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          enabled INTEGER NOT NULL DEFAULT 0,
          emergency_stop INTEGER NOT NULL DEFAULT 1,
          max_daily_loss_percent REAL NOT NULL DEFAULT 2.0,
          credential_fingerprint TEXT,
          acknowledged_at INTEGER,
          updated_at INTEGER NOT NULL
        )""")


def get_live_authorization(customer_id: str, credential_updated_at: int | None = None) -> dict:
    init_db()
    with _db() as db:
        row = db.execute(
            "SELECT * FROM mexc_live_permissions WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return {
            "authorized": False, "emergency_stop": True,
            "max_daily_loss_percent": 2.0, "reason": "not_authorized",
        }
    same_credentials = (
        credential_updated_at is not None
        and row["credential_updated_at"] is not None
        and int(row["credential_updated_at"]) == int(credential_updated_at)
    )
    authorized = bool(row["enabled"]) and not bool(row["emergency_stop"]) and same_credentials
    reason = (
        "authorized" if authorized else
        "emergency_stop" if bool(row["emergency_stop"]) else
        "credentials_changed" if bool(row["enabled"]) and not same_credentials else
        "not_authorized"
    )
    return {
        "authorized": authorized,
        "emergency_stop": bool(row["emergency_stop"]),
        "max_daily_loss_percent": float(row["max_daily_loss_percent"]),
        "acknowledged_at": int(row["acknowledged_at"]) if row["acknowledged_at"] else None,
        "updated_at": int(row["updated_at"]),
        "reason": reason,
    }


def set_live_authorization(
    customer_id: str,
    credential_updated_at: int,
    enabled: bool,
    acknowledged: bool,
    max_daily_loss_percent: float = 2.0,
) -> dict:
    if enabled and not acknowledged:
        raise ValueError("Explicit acknowledgement of MEXC futures live-trading risks is required")
    if enabled and (credential_updated_at is None or int(credential_updated_at) <= 0):
        raise ValueError("Connect and verify your MEXC Futures API credentials first")
    try:
        loss_limit = float(max_daily_loss_percent)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Daily loss limit must be between 1% and 10%") from exc
    if not 1 <= loss_limit <= 10:
        raise ValueError("Daily loss limit must be between 1% and 10%")
    now = int(time.time())
    init_db()
    with _db() as db:
        db.execute("""
        INSERT INTO mexc_live_permissions
          (customer_id,enabled,emergency_stop,max_daily_loss_percent,
           credential_updated_at,acknowledged_at,updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(customer_id) DO UPDATE SET
          enabled=excluded.enabled,
          emergency_stop=excluded.emergency_stop,
          max_daily_loss_percent=excluded.max_daily_loss_percent,
          credential_updated_at=excluded.credential_updated_at,
          acknowledged_at=excluded.acknowledged_at,
          updated_at=excluded.updated_at
        """, (
            customer_id, 1 if enabled else 0, 0 if enabled else 1,
            loss_limit, int(credential_updated_at) if enabled else None,
            now if enabled else None, now,
        ))
    return get_live_authorization(customer_id, credential_updated_at if enabled else None)


def activate_emergency_stop(customer_id: str) -> dict:
    now = int(time.time())
    init_db()
    with _db() as db:
        db.execute("""
        INSERT INTO mexc_live_permissions
          (customer_id,enabled,emergency_stop,max_daily_loss_percent,
           credential_updated_at,acknowledged_at,updated_at)
        VALUES (?,0,1,2.0,NULL,NULL,?)
        ON CONFLICT(customer_id) DO UPDATE SET
          enabled=0,emergency_stop=1,acknowledged_at=NULL,updated_at=excluded.updated_at
        """, (customer_id, now))
    return get_live_authorization(customer_id)


def require_live_authorization(customer_id: str, credential_updated_at: int) -> dict:
    state = get_live_authorization(customer_id, credential_updated_at)
    if not state["authorized"]:
        raise PermissionError(
            "MEXC futures live trading is not authorized for this customer and current API key"
        )
    return state
