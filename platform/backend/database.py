"""
Database abstraction layer with a backend-agnostic protocol.

Current implementation: **DuckDB** (single-file, zero-config).
Future drop-in: **PostgreSQL / TimescaleDB** via asyncpg or psycopg pool.

Consumer code talks only to :class:`DatabaseManager` (obtained via
:func:`get_db`), which delegates to the active :class:`DatabaseBackend`.

Usage:
    from backend.database import get_db

    db = get_db()
    plants = db.get_plants()
    df = db.query_readings_df("PLANT-UID-001", "2025-01-01", "2025-01-31")
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Protocol, runtime_checkable

import duckdb
import pandas as pd

from services.config import Settings, get_settings
from backend.models import DataQualityScore, Plant, Reading, TimeSeriesQuery, TimeSeriesResponse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Protocol — any backend must implement these
# ═══════════════════════════════════════════════════════════════════════


@runtime_checkable
class DatabaseBackend(Protocol):
    """Minimal contract every database backend must satisfy."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def get_plants(self) -> list[Plant]: ...
    def get_plant(self, plant_uid: str) -> Plant | None: ...
    def get_device_ids(self, plant_uid: str) -> list[str]: ...
    def get_date_range(self, plant_uid: str) -> tuple[str | None, str | None]: ...
    def query_readings_df(
        self,
        plant_uid: str,
        start_date: str | None = None,
        end_date: str | None = None,
        device_ids: list[str] | None = None,
        limit: int = 50_000,
    ) -> pd.DataFrame: ...
    def get_readings_stats(self, plant_uid: str | None = None) -> dict[str, Any]: ...
    def get_data_quality(
        self, plant_uid: str, start: datetime, end: datetime, interval_minutes: int
    ) -> DataQualityScore: ...


# ═══════════════════════════════════════════════════════════════════════
# DuckDB implementation
# ═══════════════════════════════════════════════════════════════════════


class DuckDBBackend:
    """DuckDB-backed implementation of :class:`DatabaseBackend`."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        logger.info("DuckDBBackend initialised → %s", db_path)

    # ── connection helpers ──────────────────────────────────────────────

    def connect(self) -> None:
        """No-op for DuckDB (connections are per-query)."""

    def close(self) -> None:
        """No-op for DuckDB."""

    @contextmanager
    def _conn(self, read_only: bool = True) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context-managed connection with conflict fallback."""
        conn: duckdb.DuckDBPyConnection | None = None
        try:
            conn = duckdb.connect(self._db_path, read_only=read_only)
        except duckdb.ConnectionException:
            try:
                conn = duckdb.connect(self._db_path, config={"access_mode": "automatic"})
            except duckdb.ConnectionException:
                conn = duckdb.connect(self._db_path, read_only=True)
        try:
            yield conn
        finally:
            if conn is not None:
                conn.close()

    # ── plant queries ──────────────────────────────────────────────────

    def get_plants(self) -> list[Plant]:
        """Return all registered plants."""
        with self._conn() as conn:
            # Query only the columns that exist in the current schema
            cols_available = self._get_plant_columns(conn)
            col_list = ", ".join(cols_available)
            rows = conn.execute(
                f"SELECT {col_list} FROM plants ORDER BY alias"
            ).fetchall()
            return [Plant.model_validate(dict(zip(cols_available, row))) for row in rows]

    @staticmethod
    def _get_plant_columns(conn: duckdb.DuckDBPyConnection) -> list[str]:
        """Return plant table columns that actually exist, in a safe order."""
        all_possible = [
            "alias", "plant_uid", "inverter_ids", "weather_id",
            "dc_size_kw", "latitude", "longitude", "tilt", "azimuth",
        ]
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'plants'"
            ).fetchall()
        }
        return [c for c in all_possible if c in existing]

    def get_plant(self, plant_uid: str) -> Plant | None:
        """Return a single plant by UID, or None."""
        with self._conn() as conn:
            cols_available = self._get_plant_columns(conn)
            col_list = ", ".join(cols_available)
            rows = conn.execute(
                f"SELECT {col_list} FROM plants WHERE plant_uid = ?",
                [plant_uid],
            ).fetchall()
            if not rows:
                return None
            return Plant.model_validate(dict(zip(cols_available, rows[0])))

    def get_plant_by_alias(self, alias: str) -> Plant | None:
        """Return a single plant by alias, or None."""
        with self._conn() as conn:
            cols_available = self._get_plant_columns(conn)
            col_list = ", ".join(cols_available)
            rows = conn.execute(
                f"SELECT {col_list} FROM plants WHERE alias = ?",
                [alias],
            ).fetchall()
            if not rows:
                return None
            return Plant.model_validate(dict(zip(cols_available, rows[0])))

    # ── device queries ──────────────────────────────────────────────────

    def get_device_ids(self, plant_uid: str) -> list[str]:
        """Distinct EMIG device IDs that have readings for this plant."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT emig_id FROM readings WHERE plant_uid = ? ORDER BY emig_id",
                [plant_uid],
            ).fetchall()
            return [r[0] for r in rows]

    # ── date range ─────────────────────────────────────────────────────

    def get_date_range(self, plant_uid: str) -> tuple[str | None, str | None]:
        """Earliest and latest timestamp strings for a plant."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MIN(ts), MAX(ts) FROM readings WHERE plant_uid = ?",
                [plant_uid],
            ).fetchone()
            return (row[0], row[1]) if row else (None, None)

    # ── readings ───────────────────────────────────────────────────────

    def query_readings_df(
        self,
        plant_uid: str,
        start_date: str | None = None,
        end_date: str | None = None,
        device_ids: list[str] | None = None,
        limit: int = 50_000,
    ) -> pd.DataFrame:
        """
        Query readings and return a *flat* DataFrame with payload columns
        expanded (e.g. ``activePower_value``, ``poaIrradiance_value``).

        Mirrors the existing DataViewer.get_readings() contract so that
        consumers do not need to change.
        """
        with self._conn() as conn:
            where: list[str] = ["plant_uid = ?"]
            params: list[Any] = [plant_uid]

            if start_date:
                where.append("ts >= ?")
                params.append(start_date)
            if end_date:
                where.append("ts < (CAST(? AS DATE) + INTERVAL '1 day')::VARCHAR")
                params.append(end_date)
            if device_ids:
                placeholders = ", ".join(["?"] * len(device_ids))
                where.append(f"emig_id IN ({placeholders})")
                params.extend(device_ids)

            where_sql = " AND ".join(where)
            params.append(limit)

            df = conn.execute(
                f"""
                SELECT plant_uid, emig_id, ts, payload
                FROM readings
                WHERE {where_sql}
                ORDER BY ts ASC
                LIMIT ?
                """,
                params,
            ).fetchdf()

        if df.empty:
            return df

        # Expand payload JSON
        return self._expand_payload(df)

    @staticmethod
    def _expand_payload(df: pd.DataFrame) -> pd.DataFrame:
        """Expand the JSON ``payload`` column into flat columns."""
        payload_records: list[dict[str, Any]] = []
        for raw in df["payload"]:
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
                flat: dict[str, Any] = {}
                for key, value in payload.items():
                    if key in {"ts", "emigId", "plant_uid", "emig_id", "timestamp"}:
                        continue
                    if isinstance(value, dict):
                        for sub_key, sub_val in value.items():
                            flat[f"{key}_{sub_key}"] = sub_val
                    else:
                        flat[key] = value
                payload_records.append(flat)
            except (json.JSONDecodeError, TypeError, AttributeError):
                payload_records.append({})

        if payload_records:
            payload_df = pd.DataFrame(payload_records)
            result = pd.concat(
                [df[["plant_uid", "emig_id", "ts"]].reset_index(drop=True), payload_df.reset_index(drop=True)],
                axis=1,
            )
            return result

        return df[["plant_uid", "emig_id", "ts"]]

    # ── stats ──────────────────────────────────────────────────────────

    def get_readings_stats(self, plant_uid: str | None = None) -> dict[str, Any]:
        """Aggregate stats mirroring DataViewer.get_readings_stats()."""
        with self._conn() as conn:
            where = "plant_uid = ?" if plant_uid else "1=1"
            params = [plant_uid] if plant_uid else []
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT plant_uid) AS plants,
                       COUNT(DISTINCT emig_id) AS devices,
                       MIN(ts) AS earliest,
                       MAX(ts) AS latest
                FROM readings
                WHERE {where}
                """,
                params,
            ).fetchone()
            return {
                "total_readings": row[0],
                "unique_plants": row[1],
                "unique_devices": row[2],
                "earliest_reading": row[3],
                "latest_reading": row[4],
            }

    # ── data quality ───────────────────────────────────────────────────

    def get_data_quality(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        interval_minutes: int = 15,
    ) -> DataQualityScore:
        """
        Compute a data-completeness score.

        ``expected_readings`` is calculated from the time span and the
        number of devices, assuming one reading per ``interval_minutes``.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS actual,
                       COUNT(DISTINCT emig_id) AS n_devices
                FROM readings
                WHERE plant_uid = ?
                  AND ts >= ?
                  AND ts < ?
                """,
                [plant_uid, start.isoformat(), end.isoformat()],
            ).fetchone()
            actual = row[0]
            n_devices = max(row[1], 1)

        total_minutes = (end - start).total_seconds() / 60
        expected_per_device = max(int(total_minutes / interval_minutes), 1)
        expected = expected_per_device * n_devices

        return DataQualityScore(
            plant_uid=plant_uid,
            start=start,
            end=end,
            expected_readings=expected,
            actual_readings=actual,
        )


# ═══════════════════════════════════════════════════════════════════════
# PostgreSQL placeholder (for future implementation)
# ═══════════════════════════════════════════════════════════════════════


class PostgreSQLBackend:  # pragma: no cover
    """
    Placeholder for a PostgreSQL / TimescaleDB backend.

    When ready, implement the :class:`DatabaseBackend` protocol using
    ``psycopg_pool`` or ``asyncpg`` and switch via ``DB_BACKEND=postgresql``
    in the environment.
    """

    def __init__(self, dsn: str, pool_min: int = 2, pool_max: int = 10) -> None:
        self._dsn = dsn
        self._pool_min = pool_min
        self._pool_max = pool_max
        raise NotImplementedError(
            "PostgreSQLBackend is a future milestone. "
            "Set DB_BACKEND=duckdb (default) for now."
        )


# ═══════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════

_db_instance: DatabaseManager | None = None  # noqa: forward ref


class DatabaseManager:
    """
    Thin façade that delegates to the active backend.

    Obtain via :func:`get_db` — never instantiate directly.
    """

    def __init__(self, backend: DuckDBBackend) -> None:
        self._backend = backend

    # Expose every backend method on the manager for convenience
    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)


def get_db(settings: Settings | None = None) -> DatabaseManager:
    """Return a module-level singleton :class:`DatabaseManager`."""
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    settings = settings or get_settings()

    if settings.db_backend == "duckdb":
        backend = DuckDBBackend(db_path=settings.duckdb_path)
    elif settings.db_backend == "postgresql":
        backend = PostgreSQLBackend(
            dsn=settings.database_url,
            pool_min=settings.db_pool_min,
            pool_max=settings.db_pool_max,
        )
    else:
        raise ValueError(f"Unknown DB_BACKEND: {settings.db_backend}")

    _db_instance = DatabaseManager(backend)
    return _db_instance
