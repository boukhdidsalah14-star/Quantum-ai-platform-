"""Encrypted, customer-isolated MEXC API credential storage.

Credentials are persisted only when the caller has verified that the configured
database is durable. This module never logs or returns API secrets.
"""
import json
import os
from app.database import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class MexcVaultError(RuntimeError):
    pass


def _cipher():
    key = os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise MexcVaultError("Credential encryption is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise MexcVaultError("Credential encryption key is invalid")


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS mexc_customer_credentials (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          encrypted_payload BLOB NOT NULL,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        )""")


def save(customer_id: str, api_key: str, api_secret: str):
    api_key, api_secret = api_key.strip(), api_secret.strip()
    if not api_key or len(api_key) > 256 or not api_secret or len(api_secret) > 512:
        raise ValueError("Valid MEXC API key and secret are required")
    encrypted = _cipher().encrypt(json.dumps(
        {"api_key": api_key, "api_secret": api_secret}, separators=(",", ":")
    ).encode())
    now = int(time.time())
    with _db() as db:
        db.execute("""
        INSERT INTO mexc_customer_credentials VALUES (?, ?, ?, ?)
        ON CONFLICT(customer_id) DO UPDATE SET
          encrypted_payload=excluded.encrypted_payload,
          updated_at=excluded.updated_at
        """, (customer_id, encrypted, now, now))
    return metadata(customer_id)


def load(customer_id: str):
    with _db() as db:
        row = db.execute("""
        SELECT encrypted_payload FROM mexc_customer_credentials WHERE customer_id=?
        """, (customer_id,)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(_cipher().decrypt(row["encrypted_payload"]).decode())
        if not isinstance(payload, dict) or set(payload) != {"api_key", "api_secret"}:
            raise ValueError("Invalid credential payload")
        return payload
    except (InvalidToken, ValueError, UnicodeDecodeError, TypeError):
        raise MexcVaultError("Stored MEXC credentials could not be decrypted")


def metadata(customer_id: str):
    with _db() as db:
        row = db.execute("""
        SELECT created_at, updated_at FROM mexc_customer_credentials WHERE customer_id=?
        """, (customer_id,)).fetchone()
    if not row:
        return {"connected": False, "broker": "mexc", "mode": "real"}
    return {"connected": True, "broker": "mexc", "mode": "real",
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def delete(customer_id: str):
    with _db() as db:
        result = db.execute(
            "DELETE FROM mexc_customer_credentials WHERE customer_id=?", (customer_id,)
        )
        return result.rowcount > 0
