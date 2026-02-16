"""Base repository pattern for data access.

All data access should go through repository classes that extend BaseRepository.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import pandas as pd

from solar_platform.db.engine import DatabaseEngine, get_engine


class BaseRepository:
    """Base class for all repositories."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self.engine = engine or get_engine()


class PlantRepository(BaseRepository):
    """Data access for plants table."""

    def get_all(self) -> pd.DataFrame:
        return self.engine.execute_df("SELECT * FROM plants ORDER BY alias")

    def list_all(self) -> pd.DataFrame:
        """Compatibility alias used by analysis and alert services."""
        return self.get_all()

    def get_by_uid(self, plant_uid: str) -> dict[str, Any] | None:
        rows = self.engine.execute("SELECT * FROM plants WHERE plant_uid = ?", (plant_uid,))
        if not rows:
            return None
        columns = self._get_columns("plants")
        return dict(zip(columns, rows[0]))

    def get_by_alias(self, alias: str) -> dict[str, Any] | None:
        rows = self.engine.execute("SELECT * FROM plants WHERE alias = ?", (alias,))
        if not rows:
            return None
        columns = self._get_columns("plants")
        return dict(zip(columns, rows[0]))

    def list_aliases(self) -> list[str]:
        rows = self.engine.execute("SELECT alias FROM plants ORDER BY alias")
        return [row[0] for row in rows]

    def list_uids(self) -> list[str]:
        rows = self.engine.execute("SELECT plant_uid FROM plants ORDER BY plant_uid")
        return [row[0] for row in rows]

    def upsert(self, plant: dict[str, Any]) -> None:
        self.engine.execute_upsert("plants", plant, ["plant_uid"])

    def _get_columns(self, table_name: str) -> list[str]:
        with self.engine.connection(read_only=True) as conn:
            columns = [desc[0] for desc in conn.execute(f"SELECT * FROM {table_name} LIMIT 0").description]
        return columns


class ReadingsRepository(BaseRepository):
    """Data access for time-series readings."""

    def get_readings(
        self,
        plant_uid: str,
        start: datetime | None = None,
        end: datetime | None = None,
        device_id: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        time_column = self._resolve_column("readings", ["timestamp", "ts"])
        device_column = self._resolve_column("readings", ["device_id", "emig_id"])

        conditions = ["plant_uid = ?"]
        params: list[Any] = [plant_uid]

        if start is not None:
            conditions.append(f"CAST({time_column} AS TIMESTAMP) >= ?")
            params.append(start)
        if end is not None:
            conditions.append(f"CAST({time_column} AS TIMESTAMP) <= ?")
            params.append(end)
        if device_id:
            conditions.append(f"{device_column} = ?")
            params.append(device_id)

        where_sql = " AND ".join(conditions)
        sql = f"SELECT * FROM readings WHERE {where_sql} ORDER BY {time_column} ASC"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        df = self.engine.execute_df(sql, tuple(params))
        if df.empty or "payload" not in df.columns:
            return df
        return self._expand_payload_columns(df)

    def get_readings_df(
        self,
        plant_uid: str,
        start: datetime | None = None,
        end: datetime | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Compatibility helper for analysis engines that request selected columns."""
        df = self.get_readings(plant_uid=plant_uid, start=start, end=end)
        if not columns:
            return df

        available_columns = [column for column in columns if column in df.columns]
        if not available_columns:
            return df.iloc[0:0].copy()
        return df.loc[:, available_columns].copy()

    @staticmethod
    def _expand_payload_columns(df: pd.DataFrame) -> pd.DataFrame:
        payload_records: list[dict[str, Any]] = []
        for raw in df["payload"]:
            if raw is None:
                payload_records.append({})
                continue
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(payload, dict):
                    payload_records.append({})
                    continue
                flat: dict[str, Any] = {}
                for key, value in payload.items():
                    if isinstance(value, dict):
                        for sub_key, sub_val in value.items():
                            flat[f"{key}_{sub_key}"] = sub_val
                    else:
                        flat[key] = value
                payload_records.append(flat)
            except (json.JSONDecodeError, TypeError, ValueError):
                payload_records.append({})

        if not payload_records:
            return df

        payload_df = pd.DataFrame(payload_records)
        if payload_df.empty:
            return df

        for col in payload_df.columns:
            if col in df.columns:
                base = df[col]
                if not pd.api.types.is_numeric_dtype(base):
                    continue
                df[col] = base.where(base.notna(), pd.to_numeric(payload_df[col], errors="coerce"))
                continue
            df[col] = payload_df[col]

        return df

    def _resolve_column(self, table_name: str, candidates: list[str]) -> str:
        with self.engine.connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ?",
                [table_name.lower()],
            ).fetchall()
        existing = {row[0] for row in rows}
        for candidate in candidates:
            if candidate in existing:
                return candidate
        joined = ", ".join(candidates)
        raise ValueError(f"None of the expected columns exist in {table_name}: {joined}")


class SolarDataRepository(BaseRepository):
    """Data access for monthly reporting `solar_data` table."""

    def get_monthly(self, month: str | None = None, site: str | None = None) -> pd.DataFrame:
        conditions: list[str] = []
        params: list[Any] = []

        if month:
            conditions.append('"Date" = ?')
            params.append(month)
        if site:
            conditions.append('"Site" = ?')
            params.append(site)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f'SELECT * FROM solar_data{where_clause} ORDER BY "Site" ASC, "Date" ASC'
        return self.engine.execute_df(sql, tuple(params) if params else None)

    def list_sites(self) -> list[str]:
        rows = self.engine.execute('SELECT DISTINCT "Site" FROM solar_data ORDER BY "Site"')
        return [row[0] for row in rows if row and row[0] is not None]

    def list_months(self) -> list[str]:
        rows = self.engine.execute('SELECT DISTINCT "Date" FROM solar_data ORDER BY "Date"')
        return [row[0] for row in rows if row and row[0] is not None]
