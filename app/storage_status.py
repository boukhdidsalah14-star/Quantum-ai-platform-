"""Runtime checks for durable customer credential storage.

Production credential storage is ready only when an explicitly enabled durable
backend is actually configured: PostgreSQL via DATABASE_URL or a mounted
persistent volume containing the SQLite database. A directory merely existing
inside the container image is not evidence of persistence.
"""
from __future__ import annotations

import os
from pathlib import Path


def inspect_storage() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    postgres_configured = database_url.startswith(("postgresql://", "postgres://"))
    database_path = Path(os.getenv("QUANTUM_DB_PATH", "data/quantum_ai.sqlite3"))
    mount_path = database_path.parent
    try:
        volume_mounted = os.path.ismount(str(mount_path))
    except (OSError, TypeError):
        volume_mounted = False

    backend = "postgresql" if postgres_configured else "sqlite"
    durable_backend_configured = bool(postgres_configured or volume_mounted)
    explicitly_enabled = os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
    encryption_key_configured = bool(os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip())
    production = os.getenv("ENVIRONMENT", "development").strip().lower() == "production"

    # Local/test environments may explicitly opt in with isolated test storage.
    # Production must prove that its backing database or volume is durable.
    durable_backend_ready = durable_backend_configured or not production
    credentials_ready = explicitly_enabled and encryption_key_configured and durable_backend_ready

    return {
        "storage_backend": backend,
        "postgres_configured": bool(postgres_configured),
        "persistent_volume_mounted": bool(volume_mounted),
        "durable_backend_configured": bool(durable_backend_configured),
        "persistent_storage_flag_enabled": bool(explicitly_enabled),
        "encryption_key_configured": bool(encryption_key_configured),
        "credential_storage_ready": bool(credentials_ready),
    }


def credential_storage_ready() -> bool:
    return bool(inspect_storage()["credential_storage_ready"])
