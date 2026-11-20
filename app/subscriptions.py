"""NOWPayments USDT-TRC20 subscription checkout and signed IPN handling."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.database import sqlite3

SUBSCRIPTION_PRICE_USD = Decimal("30.00")
SUBSCRIPTION_DAYS = 30
UNDERPAYMENT_TOLERANCE_USDT = Decimal("0.05")


def _db_path() -> Path:
    return Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS subscription_orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            payment_id TEXT UNIQUE,
            price_amount TEXT NOT NULL,
            price_currency TEXT NOT NULL,
            pay_currency TEXT NOT NULL,
            payment_status TEXT NOT NULL DEFAULT 'waiting',
            pay_address TEXT,
            pay_amount TEXT,
            invoice_url TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            activated_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_subscription_orders_customer
            ON subscription_orders(customer_id, created_at);
        CREATE TABLE IF NOT EXISTS customer_subscriptions (
            customer_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            starts_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            last_order_id TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """)


def payment_configured() -> bool:
    """Only accept money when the ledger is backed by durable PostgreSQL storage."""
    durable_storage = os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
    database_url = os.getenv("DATABASE_URL", "").strip()
    postgres_ready = database_url.startswith(("postgresql://", "postgres://"))
    return bool(
        durable_storage
        and postgres_ready
        and os.getenv("NOWPAYMENTS_API_KEY", "").strip()
        and os.getenv("NOWPAYMENTS_IPN_SECRET", "").strip()
        and os.getenv("QUANTUM_PUBLIC_URL", "").strip().startswith("https://")
    )


def create_order(customer_id: str) -> str:
    order_id = "qai_" + secrets.token_urlsafe(18)
    now = int(time.time())
    with _connect() as db:
        db.execute(
            """INSERT INTO subscription_orders
               (order_id, customer_id, price_amount, price_currency, pay_currency,
                payment_status, created_at, updated_at)
               VALUES (?, ?, ?, 'usd', 'usdttrc20', 'creating', ?, ?)""",
            (order_id, customer_id, str(SUBSCRIPTION_PRICE_USD), now, now),
        )
    return order_id


def attach_payment(order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    payment_id = str(payload.get("payment_id") or "")
    pay_address = str(payload.get("pay_address") or "")
    pay_amount = str(payload.get("pay_amount") or "")
    pay_currency = str(payload.get("pay_currency") or "").lower()
    try:
        amount = Decimal(pay_amount)
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    if not payment_id or not pay_address or amount <= 0 or pay_currency != "usdttrc20":
        raise ValueError("NOWPayments did not return a complete USDT TRC20 payment instruction")
    now = int(time.time())
    with _connect() as db:
        cur = db.execute(
            """UPDATE subscription_orders SET payment_id=?, pay_address=?, pay_amount=?,
               payment_status=?, updated_at=? WHERE order_id=? AND payment_id IS NULL
               AND payment_status='creating'""",
            (payment_id, pay_address, str(amount), str(payload.get("payment_status") or "waiting"), now, order_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Payment order is no longer available")
    return {
        "order_id": order_id, "payment_id": payment_id, "pay_address": pay_address,
        "pay_amount": str(amount), "pay_currency": "usdttrc20",
        "payment_status": str(payload.get("payment_status") or "waiting"),
    }


def _public_order(row: Any) -> dict[str, Any]:
    return {
        "order_id": row["order_id"],
        "payment_id": row["payment_id"],
        "payment_status": row["payment_status"],
        "pay_address": row["pay_address"],
        "pay_amount": row["pay_amount"],
        "pay_currency": row["pay_currency"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "activated": row["activated_at"] is not None,
    }


def pending_order_for_customer(customer_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(
            """SELECT * FROM subscription_orders
               WHERE customer_id=? AND activated_at IS NULL
               AND payment_status IN ('creating','waiting','confirming','confirmed','partially_paid')
               ORDER BY created_at DESC LIMIT 1""",
            (customer_id,),
        ).fetchone()
    return _public_order(row) if row else None


def update_payment_status(order_id: str, payment_id: str, status: str) -> bool:
    allowed = {"waiting", "confirming", "confirmed", "partially_paid", "finished",
               "failed", "refunded", "expired"}
    normalized = str(status or "").strip().lower()
    if normalized not in allowed:
        raise ValueError("Unsupported payment status")
    with _connect() as db:
        cur = db.execute(
            """UPDATE subscription_orders SET payment_status=?, updated_at=?
               WHERE order_id=? AND payment_id=? AND activated_at IS NULL""",
            (normalized, int(time.time()), order_id, payment_id),
        )
        return cur.rowcount == 1


def sorted_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: sorted_payload(payload[key]) for key in sorted(payload)}
    if isinstance(payload, list):
        return [sorted_payload(item) for item in payload]
    return payload


def verify_ipn_signature(payload: dict[str, Any], signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    serialized = json.dumps(sorted_payload(payload), separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(secret.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def apply_finished_payment(payload: dict[str, Any]) -> dict[str, Any]:
    """Idempotently activate 30 days only for a matching finished $30 USDT-TRC20 order."""
    order_id = str(payload.get("order_id") or "")
    payment_id = str(payload.get("payment_id") or "")
    status = str(payload.get("payment_status") or "").lower()
    currency = str(payload.get("pay_currency") or "").lower()
    price_currency = str(payload.get("price_currency") or "").lower()
    try:
        price_amount = Decimal(str(payload.get("price_amount")))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid payment price")
    if not order_id or not payment_id:
        raise ValueError("Payment callback is missing its order or payment identifier")

    if status != "finished":
        if not update_payment_status(order_id, payment_id, status):
            raise ValueError("Payment notification does not match a pending subscription order")
        return {"accepted": True, "activated": False, "status": status or "unknown"}

    if currency != "usdttrc20" or price_currency != "usd" or price_amount != SUBSCRIPTION_PRICE_USD:
        raise ValueError("Payment does not match the $30 USDT TRC20 subscription")

    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute("SELECT * FROM subscription_orders WHERE order_id=?", (order_id,)).fetchone()
        if not order or order["payment_id"] != payment_id:
            raise ValueError("Payment does not match a known checkout")
        if order["activated_at"] is not None:
            current = db.execute(
                "SELECT expires_at FROM customer_subscriptions WHERE customer_id=?",
                (order["customer_id"],),
            ).fetchone()
            return {
                "accepted": True, "activated": True, "duplicate": True,
                "expires_at": current["expires_at"] if current else None,
            }
        if (order["price_amount"] != str(SUBSCRIPTION_PRICE_USD)
                or order["price_currency"] != "usd"
                or order["pay_currency"] != "usdttrc20"):
            raise ValueError("Stored order configuration does not match subscription policy")
        try:
            expected_pay_amount = Decimal(str(order["pay_amount"]))
            if payload.get("actually_paid") is None:
                raise ValueError("Finished payment is missing the actual amount paid")
            actually_paid = Decimal(str(payload.get("actually_paid")))
        except (InvalidOperation, TypeError):
            raise ValueError("Finished payment contains an invalid actual amount paid")
        if expected_pay_amount <= 0 or actually_paid < expected_pay_amount - UNDERPAYMENT_TOLERANCE_USDT:
            raise ValueError("The finished payment reports an amount below the allowed payment tolerance")

        existing = db.execute(
            "SELECT starts_at, expires_at FROM customer_subscriptions WHERE customer_id=?",
            (order["customer_id"],),
        ).fetchone()
        starts_at = max(now, int(existing["expires_at"])) if existing else now
        expires_at = starts_at + SUBSCRIPTION_DAYS * 24 * 60 * 60
        db.execute(
            """INSERT INTO customer_subscriptions(customer_id,status,starts_at,expires_at,last_order_id,updated_at)
               VALUES(?, 'active', ?, ?, ?, ?)
               ON CONFLICT(customer_id) DO UPDATE SET status='active', starts_at=excluded.starts_at,
               expires_at=excluded.expires_at, last_order_id=excluded.last_order_id, updated_at=excluded.updated_at""",
            (order["customer_id"], starts_at, expires_at, order_id, now),
        )
        db.execute(
            "UPDATE subscription_orders SET payment_status='finished', activated_at=?, updated_at=? WHERE order_id=?",
            (now, now, order_id),
        )
        return {"accepted": True, "activated": True, "duplicate": False, "expires_at": expires_at}


def subscription_for_customer(customer_id: str) -> dict[str, Any]:
    now = int(time.time())
    with _connect() as db:
        owner = db.execute("SELECT role FROM customers WHERE id=?", (customer_id,)).fetchone()
        if owner and owner["role"] == "admin":
            return {"active": True, "status": "lifetime", "expires_at": None,
                    "days_remaining": None, "lifetime": True, "plan": "admin"}
        row = db.execute(
            "SELECT status, starts_at, expires_at FROM customer_subscriptions WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return {"active": False, "status": "inactive", "expires_at": None, "days_remaining": 0}
    active = row["status"] == "active" and int(row["expires_at"]) > now
    remaining = max(0, int(row["expires_at"]) - now)
    return {
        "active": active, "status": "active" if active else "expired",
        "starts_at": row["starts_at"], "expires_at": row["expires_at"],
        "days_remaining": (remaining + 86399) // 86400,
    }
