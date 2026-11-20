"""Runtime checks for durable customer credential storage.

A configured PostgreSQL URL is not proof of durable, reachable storage. Production
readiness requires a successful short connection probe, a valid encryption key,
and the explicit storage opt-in. SQLite requires its database directory to be an
actual mounted persistent volume.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


def _postgres_reachable(database_url: str) -> bool:
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except Exception:
        return False


def inspect_storage() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    postgres_configured = database_url.startswith(("postgresql://", "postgres://"))
    postgres_reachable = _postgres_reachable(database_url) if postgres_configured else False

    database_path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    mount_path = database_path.parent
    try:
        volume_mounted = os.path.ismount(str(mount_path))
    except (OSError, TypeError):
        volume_mounted = False

    backend = "postgresql" if postgres_configured else "sqlite"
    durable_backend_configured = postgres_reachable if postgres_configured else volume_mounted
    explicitly_enabled = os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
    key = os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip()
    encryption_key_configured = False
    if key:
        try:
            Fernet(key.encode("ascii"))
            encryption_key_configured = True
        except (ValueError, UnicodeEncodeError):
            encryption_key_configured = False

    production = os.getenv("ENVIRONMENT", "development").strip().lower() == "production"
    durable_backend_ready = durable_backend_configured or not production
    credentials_ready = explicitly_enabled and encryption_key_configured and durable_backend_ready

    return {
        "storage_backend": backend,
        "postgres_configured": bool(postgres_configured),
        "postgres_reachable": bool(postgres_reachable),
        "persistent_volume_mounted": bool(volume_mounted),
        "durable_backend_configured": bool(durable_backend_configured),
        "persistent_storage_flag_enabled": bool(explicitly_enabled),
        "encryption_key_configured": bool(encryption_key_configured),
        "credential_storage_ready": bool(credentials_ready),
    }


def credential_storage_ready() -> bool:
    return bool(inspect_storage()["credential_storage_ready"])
