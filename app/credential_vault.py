"""Encrypted customer-isolated storage for Deriv demo credentials only."""
import json
import os
from app.database import sqlite3
import time
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken


class VaultError(RuntimeError):
    pass


def _cipher():
    key = os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise VaultError("Credential encryption is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise VaultError("Credential encryption key is invalid")


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_vault_db():
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS broker_credentials (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          broker TEXT NOT NULL CHECK(broker='deriv'),
          mode TEXT NOT NULL CHECK(mode='demo'),
          encrypted_payload BLOB NOT NULL,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id, broker, mode)
        )""")


def save_demo(customer_id, account_id, token):
    account_id, token = account_id.strip().upper(), token.strip()
    if not account_id.startswith("VRTC") or len(account_id) > 64:
        raise ValueError("Only Deriv virtual demo accounts (VRTC IDs) are supported")
    if not token or len(token) > 4096:
        raise ValueError("A valid demo token is required")
    encrypted = _cipher().encrypt(json.dumps(
        {"account_id": account_id, "token": token}, separators=(",", ":")
    ).encode())
    now = int(time.time())
    with _db() as db:
        db.execute("""
        INSERT INTO broker_credentials VALUES (?, 'deriv', 'demo', ?, ?, ?)
        ON CONFLICT(customer_id, broker, mode) DO UPDATE SET
          encrypted_payload=excluded.encrypted_payload, updated_at=excluded.updated_at
        """, (customer_id, encrypted, now, now))
    return metadata(customer_id)


def metadata(customer_id):
    with _db() as db:
        row = db.execute("""
        SELECT created_at, updated_at FROM broker_credentials
        WHERE customer_id=? AND broker='deriv' AND mode='demo'
        """, (customer_id,)).fetchone()
    if not row:
        return {"connected": False, "broker": "deriv", "mode": "demo"}
    return {"connected": True, "broker": "deriv", "mode": "demo",
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def load_demo(customer_id):
    with _db() as db:
        row = db.execute("""
        SELECT encrypted_payload FROM broker_credentials
        WHERE customer_id=? AND broker='deriv' AND mode='demo'
        """, (customer_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(_cipher().decrypt(row["encrypted_payload"]).decode())
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise VaultError("Stored demo credentials could not be decrypted")


def delete_demo(customer_id):
    with _db() as db:
        result = db.execute("""
        DELETE FROM broker_credentials
        WHERE customer_id=? AND broker='deriv' AND mode='demo'
        """, (customer_id,))
        return result.rowcount > 0
