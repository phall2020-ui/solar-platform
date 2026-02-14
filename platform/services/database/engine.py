"""Database engine abstraction.

Provides a unified interface for database operations regardless of backend.
Current: DuckDB. Future: PostgreSQL via SQLAlchemy asyncpg.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import duckdb
import pandas as pd


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabaseEngine(Protocol):
    """Protocol for database engines. Implement this for new backends."""

    def execute(self, query: str, params: tuple | None = None) -> list[Any]: ...
    def execute_df(self, query: str, params: tuple | None = None) -> pd.DataFrame: ...
    def table_exists(self, table_name: str) -> bool: ...
    def get_tables(self) -> list[str]: ...

    @contextmanager
    def connection(self, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]: ...

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]: ...


class DuckDBEngine:
    """DuckDB implementation of DatabaseEngine."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    @contextmanager
    def connection(self, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Get a DuckDB connection with automatic fallback for lock conflicts."""
        conn: duckdb.DuckDBPyConnection | None = None
        try:
            conn = duckdb.connect(self.db_path, read_only=read_only)
        except duckdb.ConnectionException:
            try:
                conn = duckdb.connect(self.db_path, read_only=True)
            except duckdb.ConnectionException:
                conn = duckdb.connect(self.db_path, config={"access_mode": "automatic"})

        try:
            yield conn
        finally:
            if conn is not None:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Execute statements in a transaction boundary."""
        with self.connection(read_only=False) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def execute(self, query: str, params: tuple | None = None) -> list[Any]:
        """Execute a query and return rows."""
        with self.connection(read_only=False) as conn:
            if params is not None:
                return conn.execute(query, params).fetchall()
            return conn.execute(query).fetchall()

    def execute_df(self, query: str, params: tuple | None = None) -> pd.DataFrame:
        """Execute a query and return DataFrame rows."""
        with self.connection(read_only=False) as conn:
            if params is not None:
                return conn.execute(query, params).fetchdf()
            return conn.execute(query).fetchdf()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in main schema."""
        with self.connection(read_only=True) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_name = ?",
                [table_name.lower()],
            ).fetchone()
        return bool(result and result[0] > 0)

    def get_tables(self) -> list[str]:
        """List all main-schema tables."""
        with self.connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        return [row[0] for row in rows]

    def execute_insert(self, table: str, data: dict[str, Any]) -> None:
        """Insert a single row."""
        if not data:
            raise ValueError("data cannot be empty")
        self._validate_identifier(table)
        columns = list(data.keys())
        for column in columns:
            self._validate_identifier(column)

        cols_sql = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        query = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
        self.execute(query, tuple(data[col] for col in columns))

    def execute_upsert(self, table: str, data: dict[str, Any], conflict_columns: list[str]) -> None:
        """Upsert a single row using ON CONFLICT."""
        if not data:
            raise ValueError("data cannot be empty")
        if not conflict_columns:
            raise ValueError("conflict_columns cannot be empty")

        self._validate_identifier(table)
        columns = list(data.keys())
        for column in columns:
            self._validate_identifier(column)
        for conflict_column in conflict_columns:
            self._validate_identifier(conflict_column)

        cols_sql = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conflict_sql = ", ".join(conflict_columns)
        updates = [f"{column} = EXCLUDED.{column}" for column in columns if column not in conflict_columns]

        if not updates:
            query = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) ON CONFLICT ({conflict_sql}) DO NOTHING"
        else:
            updates_sql = ", ".join(updates)
            query = (
                f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {updates_sql}"
            )

        self.execute(query, tuple(data[col] for col in columns))

    def bulk_insert_df(self, table: str, df: pd.DataFrame) -> int:
        """Bulk insert from DataFrame and return inserted row count."""
        if df.empty:
            return 0

        self._validate_identifier(table)
        with self.connection(read_only=False) as conn:
            conn.register("__bulk_insert_df", df)
            try:
                conn.execute(f"INSERT INTO {table} SELECT * FROM __bulk_insert_df")
            finally:
                conn.unregister("__bulk_insert_df")

        return len(df)

    @staticmethod
    def _validate_identifier(identifier: str) -> None:
        if not _IDENTIFIER_RE.match(identifier):
            raise ValueError(f"Unsafe SQL identifier: {identifier}")


_engines: dict[str, DuckDBEngine] = {}


def get_engine(db_path: str | Path | None = None) -> DuckDBEngine:
    """Get or create a DuckDBEngine singleton for a given DB path."""
    if db_path is None:
        from services.config import get_settings

        db_path = str(get_settings().db_path)

    key = str(db_path)
    if key not in _engines:
        _engines[key] = DuckDBEngine(key)
    return _engines[key]
