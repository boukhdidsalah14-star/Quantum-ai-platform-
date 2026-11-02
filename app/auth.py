"""Minimal customer identity layer with opaque, server-side sessions.

Broker credentials are deliberately not stored by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PBKDF2_ROUNDS = 310_000
SESSION_SECONDS = 7 * 24 * 60 * 60


def _db_path() -> Path:
    return Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_auth_db() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS customer_sessions (
            token_hash TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_customer_sessions_expiry
            ON customer_sessions(expires_at);
        """)


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256\${PBKDF2_ROUNDS}\${salt.hex()}\${digest.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256" or int(rounds) != PBKDF2_ROUNDS:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_customer(email: str, password: str) -> dict:
    normalized = email.strip().lower()
    if len(normalized) > 254 or not EMAIL_RE.fullmatch(normalized):
        raise ValueError("Enter a valid email address")
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Password must be 12–256 characters")
    customer_id = secrets.token_urlsafe(18)
    now = int(time.time())
    try:
        with _connect() as db:
            db.execute(
                "INSERT INTO customers(id,email,password_hash,created_at) VALUES(?,?,?,?)",
                (customer_id, normalized, _password_hash(password), now),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists") from exc
    return {"id": customer_id, "email": normalized, "created_at": now}


def authenticate_customer(email: str, password: str) -> dict | None:
    with _connect() as db:
        row = db.execute(
            "SELECT id,email,password_hash,created_at,is_active FROM customers WHERE email=? COLLATE NOCASE",
            (email.strip().lower(),),
        ).fetchone()
    if not row or not row["is_active"] or not _password_matches(password, row["password_hash"]):
        return None
    return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


def create_session(customer_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with _connect() as db:
        db.execute("DELETE FROM customer_sessions WHERE expires_at < ?", (now,))
        db.execute(
            "INSERT INTO customer_sessions(token_hash,customer_id,expires_at,created_at) VALUES(?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), customer_id, now + SESSION_SECONDS, now),
        )
    return token


def get_customer_for_session(token: str | None) -> dict | None:
    if not token or len(token) > 128:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    with _connect() as db:
        row = db.execute("""
            SELECT c.id,c.email,c.created_at
            FROM customer_sessions s JOIN customers c ON c.id=s.customer_id
            WHERE s.token_hash=? AND s.expires_at>? AND c.is_active=1
        """, (token_hash, now)).fetchone()
    return dict(row) if row else None


def revoke_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        db.execute("DELETE FROM customer_sessions WHERE token_hash=?", (token_hash,))


def signup_enabled() -> bool:
    return os.getenv("ALLOW_CUSTOMER_SIGNUP", "false").strip().lower() in {"1", "true", "yes"}
