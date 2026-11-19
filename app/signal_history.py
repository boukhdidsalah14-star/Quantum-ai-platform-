"""Customer-scoped signal history and manually confirmed outcomes."""
from __future__ import annotations
import os
import secrets
import time
from pathlib import Path
from app.database import sqlite3

def _connect():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    with _connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS customer_signal_history (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                category TEXT NOT NULL CHECK(category IN ('forex','crypto')),
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT','WAIT')),
                strength TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                reference_price REAL,
                source TEXT NOT NULL,
                result TEXT CHECK(result IN ('WIN','LOSS','DRAW') OR result IS NULL),
                generated_at INTEGER NOT NULL,
                settled_at INTEGER
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_signal_history_customer_time ON customer_signal_history(customer_id, generated_at DESC)")

def record_signal(customer_id, category, symbol, timeframe, direction, strength, score, reference_price, source):
    if category not in {"forex", "crypto"} or direction not in {"CALL", "PUT", "WAIT"}:
        raise ValueError("Invalid signal record")
    signal_id = secrets.token_urlsafe(12)
    with _connect() as db:
        db.execute("""INSERT INTO customer_signal_history
            (id,customer_id,category,symbol,timeframe,direction,strength,score,reference_price,source,generated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (signal_id, customer_id, category, symbol, timeframe, direction, strength,
             int(score), float(reference_price) if reference_price is not None else None,
             str(source)[:120], int(time.time())))
    return signal_id

def list_signals(customer_id, limit=50):
    with _connect() as db:
        rows = db.execute("""SELECT id,category,symbol,timeframe,direction,strength,score,reference_price,
            source,result,generated_at,settled_at FROM customer_signal_history
            WHERE customer_id=? ORDER BY generated_at DESC LIMIT ?""", (customer_id, limit)).fetchall()
    return [dict(row) for row in rows]

def set_signal_result(customer_id, signal_id, result):
    result = str(result).upper()
    if result not in {"WIN", "LOSS", "DRAW"}:
        raise ValueError("Result must be WIN, LOSS, or DRAW")
    now = int(time.time())
    with _connect() as db:
        cur = db.execute("""UPDATE customer_signal_history SET result=?,settled_at=?
            WHERE id=? AND customer_id=? AND direction IN ('CALL','PUT') AND result IS NULL""",
            (result, now, signal_id, customer_id))
        if cur.rowcount != 1:
            return None
        row = db.execute("""SELECT id,category,symbol,timeframe,direction,strength,score,reference_price,
            source,result,generated_at,settled_at FROM customer_signal_history WHERE id=? AND customer_id=?""",
            (signal_id, customer_id)).fetchone()
    return dict(row) if row else None

def signal_statistics(customer_id):
    with _connect() as db:
        row = db.execute("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN direction IN ('CALL','PUT') THEN 1 ELSE 0 END) AS actionable,
            SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN result='DRAW' THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN result IS NULL AND direction IN ('CALL','PUT') THEN 1 ELSE 0 END) AS pending
            FROM customer_signal_history WHERE customer_id=?""", (customer_id,)).fetchone()
    data = dict(row)
    for key in ("total", "actionable", "wins", "losses", "draws", "pending"):
        data[key] = int(data[key] or 0)
    decided = data["wins"] + data["losses"]
    data["decided"] = decided
    data["win_rate_pct"] = round(data["wins"] * 100 / decided, 1) if decided else None
    return data
