"""Passwordless one-time-code authentication for the QUANTUM AI owner account."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import httpx

from app.auth import _connect, _password_hash

OWNER_EMAIL = os.getenv("QUANTUM_ADMIN_EMAIL", "smartgoomaps@gmail.com").strip().lower()
CODE_TTL_SECONDS = 600
RESEND_COOLDOWN_SECONDS = 60
MAX_CODE_ATTEMPTS = 5


def email_provider_ready() -> bool:
    return bool(
        os.getenv("RESEND_API_KEY", "").strip()
        and os.getenv("QUANTUM_EMAIL_FROM", "").strip()
        and os.getenv("QUANTUM_ADMIN_OTP_SECRET", "").strip()
    )


def init_admin_auth_db() -> None:
    with _connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_codes (
                email TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                last_sent_at INTEGER NOT NULL
            )
        """)


def _code_digest(code: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), code.encode("ascii"), hashlib.sha256).hexdigest()


def send_owner_login_code(email: str) -> None:
    normalized = email.strip().lower()
    if normalized != OWNER_EMAIL:
        raise ValueError("This email is not configured for passwordless administrator access")
    if not email_provider_ready():
        raise RuntimeError("Admin email delivery is not configured on the server")
    init_admin_auth_db()
    now = int(time.time())
    with _connect() as db:
        row = db.execute("SELECT last_sent_at FROM admin_login_codes WHERE email=?", (normalized,)).fetchone()
        if row and now - int(row["last_sent_at"]) < RESEND_COOLDOWN_SECONDS:
            raise ValueError("Please wait one minute before requesting another code")
    code = f"{secrets.randbelow(1_000_000):06d}"
    secret = os.getenv("QUANTUM_ADMIN_OTP_SECRET", "")
    with _connect() as db:
        db.execute(
            """INSERT INTO admin_login_codes(email,code_hash,expires_at,attempts,created_at,last_sent_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET
               code_hash=excluded.code_hash,expires_at=excluded.expires_at,
               attempts=0,created_at=excluded.created_at,last_sent_at=excluded.last_sent_at""",
            (normalized, _code_digest(code, secret), now + CODE_TTL_SECONDS, 0, now, now),
        )
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": "Bearer " + os.getenv("RESEND_API_KEY", ""),
                     "Content-Type": "application/json"},
            json={
                "from": os.getenv("QUANTUM_EMAIL_FROM", ""),
                "to": [normalized],
                "subject": "Your QUANTUM AI administrator login code",
                "text": f"Your QUANTUM AI admin login code is {code}. It expires in 10 minutes. If you did not request it, ignore this email.",
            },
            timeout=15,
        )
        response.raise_for_status()
    except Exception as exc:
        with _connect() as db:
            db.execute("DELETE FROM admin_login_codes WHERE email=?", (normalized,))
        raise RuntimeError("The login email could not be sent. Check the server email settings.") from exc


def verify_owner_login_code(email: str, code: str) -> dict | None:
    normalized = email.strip().lower()
    if normalized != OWNER_EMAIL or not code.isdigit() or len(code) != 6:
        return None
    init_admin_auth_db()
    now = int(time.time())
    secret = os.getenv("QUANTUM_ADMIN_OTP_SECRET", "")
    with _connect() as db:
        row = db.execute(
            "SELECT code_hash,expires_at,attempts FROM admin_login_codes WHERE email=?",
            (normalized,),
        ).fetchone()
        if not row or int(row["expires_at"]) <= now or int(row["attempts"]) >= MAX_CODE_ATTEMPTS:
            db.execute("DELETE FROM admin_login_codes WHERE email=?", (normalized,))
            return None
        if not hmac.compare_digest(str(row["code_hash"]), _code_digest(code, secret)):
            db.execute("UPDATE admin_login_codes SET attempts=attempts+1 WHERE email=?", (normalized,))
            return None
        db.execute("DELETE FROM admin_login_codes WHERE email=?", (normalized,))
        customer = db.execute("SELECT id,email,created_at,is_active FROM customers WHERE lower(email)=lower(?)", (normalized,)).fetchone()
        if customer:
            if not customer["is_active"]:
                return None
            db.execute("UPDATE customers SET role='admin' WHERE id=?", (customer["id"],))
            return {"id": customer["id"], "email": customer["email"], "created_at": customer["created_at"], "role": "admin"}
        customer_id = secrets.token_urlsafe(18)
        password_hash = _password_hash(secrets.token_urlsafe(48))
        db.execute(
            "INSERT INTO customers(id,email,password_hash,created_at,is_active,role) VALUES(?,?,?,?,1,'admin')",
            (customer_id, normalized, password_hash, now),
        )
        return {"id": customer_id, "email": normalized, "created_at": now, "role": "admin"}
