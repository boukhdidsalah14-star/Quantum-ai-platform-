"""MetaApi cloud provisioning for customer-owned MT4/MT5 accounts.

Customer credentials are entered on MetaApi's hosted configuration page, not
collected or stored by QUANTUM AI. This module stores only MetaApi account IDs.
"""
from __future__ import annotations

import os
import uuid
import time
from pathlib import Path
from app.database import sqlite3
import httpx

PROVISIONING_URL = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
ALLOWED_PLATFORMS = {"mt4", "mt5"}


class MetaApiError(RuntimeError):
    pass


def _token() -> str:
    token = os.getenv("METAAPI_TOKEN", "").strip()
    if not token:
        raise MetaApiError("Cloud MetaTrader connection is not configured yet")
    return token


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
        CREATE TABLE IF NOT EXISTS metaapi_customer_accounts (
          customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          platform TEXT NOT NULL CHECK(platform IN ('mt4','mt5')),
          account_id TEXT NOT NULL UNIQUE,
          broker TEXT NOT NULL,
          server TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          PRIMARY KEY(customer_id, platform)
        )""")


async def _request(method: str, path: str, *, body=None, transaction_id=None):
    headers = {"auth-token": _token(), "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if transaction_id:
        headers["transaction-id"] = transaction_id
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=6)) as client:
            response = await client.request(
                method, PROVISIONING_URL + path, headers=headers, json=body
            )
        if response.status_code >= 400:
            # Do not relay provider payloads: they can contain account details.
            raise MetaApiError("MetaTrader cloud provider rejected the request")
        return response.json() if response.content else {}
    except httpx.TimeoutException as exc:
        raise MetaApiError("MetaTrader cloud request timed out; check account status before retrying") from exc
    except httpx.HTTPError as exc:
        raise MetaApiError("MetaTrader cloud provider is temporarily unavailable") from exc
    except ValueError as exc:
        raise MetaApiError("MetaTrader cloud provider returned an invalid response") from exc


def metadata(customer_id: str) -> list[dict]:
    with _db() as db:
        rows = db.execute(
            "SELECT platform, account_id, broker, server, created_at "
            "FROM metaapi_customer_accounts WHERE customer_id=? ORDER BY platform",
            (customer_id,),
        ).fetchall()
    return [
        {"platform": row["platform"], "account_id": row["account_id"],
         "broker": row["broker"], "server": row["server"],
         "created_at": row["created_at"], "connected": True}
        for row in rows
    ]


async def connect_customer_account(customer_id: str, platform: str, broker: str, server: str) -> dict:
    platform = str(platform or "").strip().lower()
    broker = str(broker or "").strip()
    server = str(server or "").strip()
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError("Choose MT4 or MT5")
    if not broker or len(broker) > 80 or any(c in broker for c in "\r\n"):
        raise ValueError("Enter a valid broker name")
    if not server or len(server) > 120 or any(c in server for c in "\r\n"):
        raise ValueError("Enter the exact trading server shown in MetaTrader")
    # Avoid duplicate cloud accounts and accidental paid provisioning.
    with _db() as db:
        existing = db.execute(
            "SELECT account_id FROM metaapi_customer_accounts WHERE customer_id=? AND platform=?",
            (customer_id, platform),
        ).fetchone()
    if existing:
        raise MetaApiError("An account for this platform is already registered. Disconnect it before replacing it.")

    created = await _request(
        "POST", "/users/current/accounts",
        body={
            "name": f"QUANTUM AI {broker} {platform.upper()}",
            "server": server,
            "platform": platform,
            "type": "cloud-g2",
            "magic": 914110,
            "application": "QUANTUM AI",
            "keywords": [broker],
            "reliability": "high",
            "metadata": {"customerReference": str(customer_id)[:64], "product": "QUANTUM AI"},
        },
        transaction_id=uuid.uuid4().hex,
    )
    account_id = str(created.get("id") or "").strip()
    if not account_id:
        raise MetaApiError("Cloud provider did not return an account identifier")
    try:
        link_result = await _request(
            "PUT", f"/users/current/accounts/{account_id}/configuration-link?ttlInDays=1"
        )
        config_link = str(link_result.get("configurationLink") or "").strip()
        if not config_link.startswith("https://app.metaapi.cloud/"):
            raise MetaApiError("Cloud provider did not return a valid secure setup link")
        with _db() as db:
            db.execute(
                "INSERT INTO metaapi_customer_accounts "
                "(customer_id, platform, account_id, broker, server, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (customer_id, platform, account_id, broker, server, int(time.time())),
            )
        return {
            "connected": False,
            "platform": platform,
            "broker": broker,
            "server": server,
            "account_id": account_id,
            "state": str(created.get("state") or "DRAFT"),
            "configuration_link": config_link,
            "configuration_link_expires_in_days": 1,
            "credentials_handled_by": "MetaApi hosted secure configuration",
        }
    except Exception:
        # Do not leave a paid orphaned account if link generation or local persistence fails.
        try:
            await _request("DELETE", f"/users/current/accounts/{account_id}")
        except Exception:
            pass
        raise


async def account_status(customer_id: str, platform: str) -> dict:
    platform = str(platform or "").strip().lower()
    with _db() as db:
        row = db.execute(
            "SELECT account_id, broker, server FROM metaapi_customer_accounts "
            "WHERE customer_id=? AND platform=?", (customer_id, platform)
        ).fetchone()
    if not row:
        return {"connected": False, "platform": platform}
    data = await _request("GET", f"/users/current/accounts/{row['account_id']}")
    replicas = data.get("replicas") or {}
    replica = next(iter(replicas.values()), {}) if isinstance(replicas, dict) else {}
    connection_status = str(replica.get("connectionStatus") or data.get("connectionStatus") or "UNKNOWN")
    state = str(data.get("state") or "UNKNOWN")
    return {
        "connected": state == "DEPLOYED" and connection_status.upper() == "CONNECTED",
        "platform": platform,
        "broker": row["broker"],
        "server": row["server"],
        "state": state,
        "connection_status": connection_status,
        "account_id": row["account_id"],
        "login": str(data.get("login") or ""),
    }


async def disconnect_customer_account(customer_id: str, platform: str) -> bool:
    platform = str(platform or "").strip().lower()
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError("Choose MT4 or MT5")
    with _db() as db:
        row = db.execute(
            "SELECT account_id FROM metaapi_customer_accounts WHERE customer_id=? AND platform=?",
            (customer_id, platform),
        ).fetchone()
    if not row:
        return False
    await _request("DELETE", f"/users/current/accounts/{row['account_id']}")
    with _db() as db:
        db.execute(
            "DELETE FROM metaapi_customer_accounts WHERE customer_id=? AND platform=?",
            (customer_id, platform),
        )
    return True
