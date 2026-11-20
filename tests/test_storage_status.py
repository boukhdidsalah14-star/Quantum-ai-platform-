import pytest
from cryptography.fernet import Fernet

from app.storage_status import credential_storage_ready, inspect_storage


def clear_storage_env(monkeypatch):
    for key in (
        "DATABASE_URL", "QUANTUM_DB_PATH", "QUANTUM_PERSISTENT_STORAGE",
        "QUANTUM_CREDENTIALS_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_production_sqlite_without_mounted_volume_is_not_durable(monkeypatch, tmp_path):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "data.sqlite3"))
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.storage_status.os.path.ismount", lambda path: False)

    result = inspect_storage()

    assert result["storage_backend"] == "sqlite"
    assert result["persistent_volume_mounted"] is False
    assert result["credential_storage_ready"] is False
    assert credential_storage_ready() is False


def test_production_sqlite_with_mounted_volume_can_be_ready(monkeypatch, tmp_path):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "data.sqlite3"))
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.storage_status.os.path.ismount", lambda path: True)

    result = inspect_storage()

    assert result["persistent_volume_mounted"] is True
    assert result["durable_backend_configured"] is True
    assert result["credential_storage_ready"] is True


def test_postgres_configuration_requires_successful_connect(monkeypatch):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@example.invalid/db")
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.storage_status._postgres_reachable", lambda dsn: False)

    result = inspect_storage()

    assert result["postgres_configured"] is True
    assert result["postgres_reachable"] is False
    assert result["durable_backend_configured"] is False
    assert result["credential_storage_ready"] is False


def test_production_postgres_backend_can_be_ready_after_probe(monkeypatch):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@example.invalid/db")
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.storage_status._postgres_reachable", lambda dsn: True)

    result = inspect_storage()

    assert result["storage_backend"] == "postgresql"
    assert result["postgres_configured"] is True
    assert result["postgres_reachable"] is True
    assert result["durable_backend_configured"] is True
    assert result["credential_storage_ready"] is True


def test_invalid_encryption_key_blocks_credential_storage(monkeypatch, tmp_path):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "data.sqlite3"))
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "invalid-key")
    monkeypatch.setattr("app.storage_status.os.path.ismount", lambda path: True)

    result = inspect_storage()

    assert result["encryption_key_configured"] is False
    assert credential_storage_ready() is False


def test_test_environment_can_use_isolated_explicit_storage(monkeypatch, tmp_path):
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "data.sqlite3"))
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())

    assert credential_storage_ready() is True
