"""Small SQLite/PostgreSQL compatibility layer for the existing app repositories.

SQLite remains the default for local tests. When DATABASE_URL is configured,
the same repository functions use PostgreSQL with dict rows and safe transaction
handling. PostgreSQL transactions use a transaction-scoped advisory lock for
the few existing SQLite BEGIN IMMEDIATE critical sections.
"""
from __future__ import annotations

import os
import re
import sqlite3 as _sqlite3
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Local SQLite-only environments do not need psycopg.
    psycopg = None
    dict_row = None


class _PostgresConnection:
    def __init__(self, dsn: str, timeout: int = 10):
        if psycopg is None:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]")
        self._conn = psycopg.connect(dsn, connect_timeout=max(1, int(timeout)), row_factory=dict_row)

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        # psycopg is created with dict_row, which preserves sqlite3.Row-style key access.
        return None

    def execute(self, sql: str, parameters: Any = ()):
        statement = sql.strip()
        upper = statement.upper()
        if upper.startswith("PRAGMA "):
            return self._conn.execute("SELECT 1")
        if upper == "BEGIN IMMEDIATE":
            self._conn.execute("BEGIN")
            self._conn.execute("SELECT pg_advisory_xact_lock(7420192601)")
            return self._conn.cursor()
        ignore_conflict = upper.startswith("INSERT OR IGNORE INTO ")
        if ignore_conflict:
            statement = re.sub(r"^INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", statement, flags=re.I)
            statement += " ON CONFLICT DO NOTHING"
        statement = re.sub(r"\?", "%s", statement)
        statement = re.sub(r"\bBLOB\b", "BYTEA", statement, flags=re.I)
        return self._conn.execute(statement, parameters)

    def executescript(self, script: str):
        # Existing scripts contain only table/index DDL, with no semicolons in literals.
        cursor = None
        for statement in script.split(";"):
            if statement.strip():
                cursor = self.execute(statement)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False

    def close(self):
        self._conn.close()


class _SQLiteFacade:
    Row = _sqlite3.Row
    Connection = _sqlite3.Connection
    IntegrityError = psycopg.IntegrityError if psycopg is not None else _sqlite3.IntegrityError

    @staticmethod
    def connect(path: str, timeout: int = 10, **kwargs):
        dsn = os.getenv("DATABASE_URL", "").strip()
        if dsn:
            if not dsn.startswith(("postgresql://", "postgres://")):
                raise RuntimeError("DATABASE_URL must be a PostgreSQL connection string")
            return _PostgresConnection(dsn, timeout=timeout)
        return _sqlite3.connect(path, timeout=timeout, **kwargs)


sqlite3 = _SQLiteFacade()
