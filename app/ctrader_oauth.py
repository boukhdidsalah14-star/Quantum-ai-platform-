"""Secure cTrader OAuth authorization for customer-owned trading accounts.

This module completes the mobile authorization handshake only. It deliberately
does not enable order execution until account discovery, environment
verification, and the cTrader trading session adapter have been implemented
and tested.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from app.database import sqlite3

AUTHORIZATION_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
ALLOWED_SCOPES = {"accounts", "trading"}


class CTraderOAuthError(RuntimeError):
    pass


def _config() -> tuple[str, str, str]:
    client_id = os.getenv("CTRADER_CLIENT_ID", "").strip()
    client_secret = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("CTRADER_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri.startswith("https://"):
        raise CTraderOAuthError("cTrader application credentials are not configured")
    return client_id, client_secret, redirect_uri


def configured() -> bool:
    try:
        _config()
        return True
    except CTraderOAuthError:
        return False


def _credential_storage_ready() -> bool:
    return (
        os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
        and bool(os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip())
    )


def _require_credential_storage() -> None:
    if os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() != "true":
        raise CTraderOAuthError("Durable credential storage is not enabled on this server")
    _cipher()


def _cipher() -> Fernet:
    key = os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise CTraderOAuthError("Secure credential storage is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CTraderOAuthError("Credential encryption configuration is invalid") from exc


def _db():
    path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with _db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS ctrader_oauth_states (
          state_hash TEXT PRIMARY KEY,
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS ctrader_customer_tokens (
          customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
          encrypted_payload BLOB NOT NULL,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        )""")


def create_authorization(customer_id: str, scope: str = "trading") -> tuple[str, str]:
    _require_credential_storage()
    if scope not in ALLOWED_SCOPES:
        raise ValueError("Unsupported cTrader authorization scope")
    client_id, _, redirect_uri = _config()
    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = int(time.time())
    with _db() as db:
        db.execute("DELETE FROM ctrader_oauth_states WHERE expires_at < ?", (now,))
        db.execute(
            "INSERT INTO ctrader_oauth_states (state_hash, customer_id, expires_at) VALUES (?, ?, ?)",
            (state_hash, customer_id, now + 600),
        )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "product": "web",
    }
    return state, AUTHORIZATION_URL + "?" + urlencode(params)


async def complete_authorization(code: str, state: str) -> str:
    _require_credential_storage()
    if not code or len(code) > 2048 or not state or len(state) > 256:
        raise CTraderOAuthError("The cTrader authorization response is invalid")
    client_id, client_secret, redirect_uri = _config()
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    now = int(time.time())
    with _db() as db:
        row = db.execute(
            "SELECT customer_id, expires_at FROM ctrader_oauth_states WHERE state_hash=?",
            (state_hash,),
        ).fetchone()
        if not row or int(row["expires_at"]) < now:
            raise CTraderOAuthError("The connection request expired. Please try connecting again.")
        db.execute("DELETE FROM ctrader_oauth_states WHERE state_hash=?", (state_hash,))
        customer_id = str(row["customer_id"])

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as client:
            response = await client.get(
                TOKEN_URL,
                params={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            raise CTraderOAuthError("cTrader could not complete account authorization")
        payload = response.json()
    except CTraderOAuthError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise CTraderOAuthError("Could not securely complete cTrader authorization") from exc

    access_token = str(payload.get("accessToken") or "").strip()
    refresh_token = str(payload.get("refreshToken") or "").strip()
    expires_in = int(payload.get("expiresIn") or 0)
    if payload.get("errorCode") or not access_token or not refresh_token or expires_in <= 0:
        raise CTraderOAuthError("cTrader returned an incomplete authorization response")

    encrypted = _cipher().encrypt(json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": now + expires_in,
        "token_type": str(payload.get("tokenType") or "bearer"),
    }, separators=(",", ":")).encode("utf-8"))
    with _db() as db:
        db.execute("""
        INSERT INTO ctrader_customer_tokens (customer_id, encrypted_payload, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(customer_id) DO UPDATE SET
          encrypted_payload=excluded.encrypted_payload,
          updated_at=excluded.updated_at
        """, (customer_id, encrypted, now, now))
    return customer_id


def status(customer_id: str) -> dict:
    storage_ready = _credential_storage_ready()
    with _db() as db:
        row = db.execute(
            "SELECT created_at, updated_at FROM ctrader_customer_tokens WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return {
            "authorized": False,
            "connected": False,
            "configured": configured(),
            "credential_storage_ready": storage_ready,
            "broker": "IC Markets",
            "platform": "cTrader",
            "trading_enabled": False,
            "state": ("APPLICATION_SETUP_REQUIRED" if not configured()
                      else "PERSISTENT_STORAGE_REQUIRED" if not storage_ready
                      else "NOT_CONNECTED"),
        }
    return {
        "authorized": True,
        "connected": False,
        "configured": configured(),
        "credential_storage_ready": storage_ready,
        "broker": "IC Markets",
        "platform": "cTrader",
        "trading_enabled": False,
        "state": "AUTHORISED_ACCOUNT_SYNC_PENDING",
        "authorized_at": int(row["created_at"]),
        "updated_at": int(row["updated_at"]),
        "note": "Authorization is saved securely. Account discovery and demo execution validation are still required.",
    }


def delete_authorization(customer_id: str) -> bool:
    with _db() as db:
        db.execute("DELETE FROM ctrader_oauth_states WHERE customer_id=?", (customer_id,))
        result = db.execute(
            "DELETE FROM ctrader_customer_tokens WHERE customer_id=?", (customer_id,)
        )
        return result.rowcount > 0


def load_tokens(customer_id: str) -> dict | None:
    with _db() as db:
        row = db.execute(
            "SELECT encrypted_payload FROM ctrader_customer_tokens WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(_cipher().decrypt(row["encrypted_payload"]).decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise CTraderOAuthError("Stored cTrader authorization could not be decrypted") from exc


async def refresh_access_token(customer_id: str) -> dict:
    _require_credential_storage()
    tokens = load_tokens(customer_id)
    if not tokens:
        raise CTraderOAuthError("No cTrader account is authorized")
    if int(tokens.get("expires_at") or 0) > int(time.time()) + 120:
        return tokens
    client_id, client_secret, _ = _config()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as client:
            response = await client.post(
                TOKEN_URL,
                params={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            raise CTraderOAuthError("cTrader token refresh was rejected")
        payload = response.json()
    except CTraderOAuthError:
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise CTraderOAuthError("Could not refresh the cTrader authorization") from exc
    if payload.get("errorCode") or not payload.get("accessToken") or not payload.get("refreshToken"):
        raise CTraderOAuthError("cTrader returned an invalid refreshed authorization")
    now = int(time.time())
    updated = {
        "access_token": str(payload["accessToken"]),
        "refresh_token": str(payload["refreshToken"]),
        "expires_at": now + int(payload.get("expiresIn") or 0),
        "token_type": str(payload.get("tokenType") or "bearer"),
    }
    encrypted = _cipher().encrypt(json.dumps(updated, separators=(",", ":")).encode("utf-8"))
    with _db() as db:
        db.execute(
            "UPDATE ctrader_customer_tokens SET encrypted_payload=?, updated_at=? WHERE customer_id=?",
            (encrypted, now, customer_id),
        )
    return updated
