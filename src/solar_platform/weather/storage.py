"""DuckDB storage layer for weather forecasts and historical data.

Standalone implementation using duckdb directly — no dependency on the
solar_platform.db dated-file modules that cannot be resolved by standard
Python module resolution.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Generator, Optional, Union

import duckdb
import pandas as pd

from solar_platform.weather.nasa_power import DailyHistoricalRecord
from solar_platform.weather.open_meteo import HourlyWeatherRecord

DEFAULT_DB_PATH = Path.home() / ".solar_toolkit" / "plant_registry.duckdb"


@contextmanager
def _connect(db_path: Path, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Open a short-lived DuckDB connection and close it on exit."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


class WeatherRepository:
    """Repository for weather_forecasts and weather_historical DuckDB tables.

    Parameters
    ----------
    db_path:
        Path to the DuckDB file. Defaults to ~/.solar_toolkit/plant_registry.duckdb.
        Pass ":memory:" for an in-memory database (useful in tests).
    """

    def __init__(self, db_path: Optional[Union[Path, str]] = None) -> None:
        self._in_memory = str(db_path) == ":memory:" if db_path else False
        if self._in_memory:
            self._mem_conn = duckdb.connect(":memory:")
            self._ensure_schema_conn(self._mem_conn)
            self.db_path: Path = Path(":memory:")
        else:
            self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
            with _connect(self.db_path) as conn:
                self._ensure_schema_conn(conn)

    @contextmanager
    def _conn(self, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        if self._in_memory:
            yield self._mem_conn
        else:
            with _connect(self.db_path, read_only=read_only) as conn:
                yield conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema_conn(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create tables if they do not already exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_forecasts (
                plant_name           VARCHAR NOT NULL,
                timestamp            TIMESTAMPTZ NOT NULL,
                fetched_at           TIMESTAMPTZ NOT NULL,
                forecast_days_out    INTEGER,
                ghi_wm2              DOUBLE,
                dni_wm2              DOUBLE,
                dhi_wm2              DOUBLE,
                gti_wm2              DOUBLE,
                direct_radiation_wm2 DOUBLE,
                cloud_cover_pct      DOUBLE,
                temperature_c        DOUBLE,
                wind_speed_kmh       DOUBLE,
                snowfall_cm          DOUBLE,
                PRIMARY KEY (plant_name, timestamp, fetched_at)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_historical (
                plant_name          VARCHAR NOT NULL,
                date                DATE NOT NULL,
                ghi_kwh_m2          DOUBLE,
                clearsky_ghi_kwh_m2 DOUBLE,
                cloud_amount_pct    DOUBLE,
                snow_depth_cm       DOUBLE,
                temperature_c       DOUBLE,
                wind_speed_ms       DOUBLE,
                PRIMARY KEY (plant_name, date)
            )
        """)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert_forecasts(
        self,
        records: list[HourlyWeatherRecord],
        fetched_at: Optional[datetime] = None,
    ) -> int:
        """Insert or replace forecast records. Returns count of rows written.

        On conflict (plant_name, timestamp, fetched_at) the row is updated
        in-place with the latest values.  ``fetched_at`` defaults to now (UTC).
        ``forecast_days_out`` is the ceiling of the number of calendar days
        between the fetch date and the forecast timestamp date.
        """
        if not records:
            return 0

        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc)

        fetched_date: date = fetched_at.astimezone(timezone.utc).date()

        rows: list[tuple] = []
        for r in records:
            ts_utc = r.timestamp.astimezone(timezone.utc)
            ts_date = ts_utc.date()
            delta_days = (ts_date - fetched_date).days
            forecast_days_out = math.ceil(delta_days) if delta_days > 0 else 0
            rows.append(
                (
                    r.plant_name,
                    ts_utc,
                    fetched_at,
                    forecast_days_out,
                    r.ghi_wm2,
                    r.dni_wm2,
                    r.dhi_wm2,
                    r.gti_wm2,
                    r.direct_radiation_wm2,
                    r.cloud_cover_pct,
                    r.temperature_c,
                    r.wind_speed_kmh,
                    r.snowfall_cm,
                )
            )

        df = pd.DataFrame(
            rows,
            columns=[
                "plant_name",
                "timestamp",
                "fetched_at",
                "forecast_days_out",
                "ghi_wm2",
                "dni_wm2",
                "dhi_wm2",
                "gti_wm2",
                "direct_radiation_wm2",
                "cloud_cover_pct",
                "temperature_c",
                "wind_speed_kmh",
                "snowfall_cm",
            ],
        )

        with self._conn() as conn:
            conn.register("_wf_tmp", df)
            try:
                conn.execute(
                    """
                    INSERT INTO weather_forecasts
                    SELECT * FROM _wf_tmp
                    ON CONFLICT (plant_name, timestamp, fetched_at) DO UPDATE SET
                        forecast_days_out    = excluded.forecast_days_out,
                        ghi_wm2              = excluded.ghi_wm2,
                        dni_wm2              = excluded.dni_wm2,
                        dhi_wm2              = excluded.dhi_wm2,
                        gti_wm2              = excluded.gti_wm2,
                        direct_radiation_wm2 = excluded.direct_radiation_wm2,
                        cloud_cover_pct      = excluded.cloud_cover_pct,
                        temperature_c        = excluded.temperature_c,
                        wind_speed_kmh       = excluded.wind_speed_kmh,
                        snowfall_cm          = excluded.snowfall_cm
                    """
                )
            finally:
                conn.unregister("_wf_tmp")

        return len(rows)

    def upsert_historical(
        self,
        records: list[DailyHistoricalRecord],
    ) -> int:
        """Insert or ignore historical records (immutable once stored).

        On conflict (plant_name, date) the existing row is kept unchanged.
        Returns the number of records in the input list (not necessarily the
        number of new rows inserted, since duplicates are silently skipped).
        """
        if not records:
            return 0

        rows = [
            (
                r.plant_name,
                r.date,
                r.ghi_kwh_m2,
                r.clearsky_ghi_kwh_m2,
                r.cloud_amount_pct,
                r.snow_depth_cm,
                r.temperature_c,
                r.wind_speed_ms,
            )
            for r in records
        ]

        df = pd.DataFrame(
            rows,
            columns=[
                "plant_name",
                "date",
                "ghi_kwh_m2",
                "clearsky_ghi_kwh_m2",
                "cloud_amount_pct",
                "snow_depth_cm",
                "temperature_c",
                "wind_speed_ms",
            ],
        )

        with self._conn() as conn:
            conn.register("_wh_tmp", df)
            try:
                conn.execute(
                    """
                    INSERT INTO weather_historical
                    SELECT * FROM _wh_tmp
                    ON CONFLICT (plant_name, date) DO NOTHING
                    """
                )
            finally:
                conn.unregister("_wh_tmp")

        return len(rows)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_forecasts(
        self,
        plant_name: str,
        from_ts: datetime,
        to_ts: datetime,
        latest_only: bool = True,
    ) -> pd.DataFrame:
        """Return forecast rows as a DataFrame.

        If *latest_only* is True (default), only rows from the most recent
        ``fetched_at`` per (plant_name, timestamp) are returned, using a
        window function to select the maximum fetch batch.
        """
        if latest_only:
            sql = """
                WITH ranked AS (
                    SELECT *,
                           MAX(fetched_at) OVER (
                               PARTITION BY plant_name, timestamp
                           ) AS _max_fetched_at
                    FROM weather_forecasts
                    WHERE plant_name = ?
                      AND timestamp  >= ?
                      AND timestamp  <= ?
                )
                SELECT plant_name, timestamp, fetched_at, forecast_days_out,
                       ghi_wm2, dni_wm2, dhi_wm2, gti_wm2, direct_radiation_wm2,
                       cloud_cover_pct, temperature_c, wind_speed_kmh, snowfall_cm
                FROM ranked
                WHERE fetched_at = _max_fetched_at
                ORDER BY timestamp
            """
        else:
            sql = """
                SELECT *
                FROM weather_forecasts
                WHERE plant_name = ?
                  AND timestamp  >= ?
                  AND timestamp  <= ?
                ORDER BY timestamp, fetched_at
            """

        with self._conn(read_only=not self._in_memory) as conn:
            return conn.execute(sql, [plant_name, from_ts, to_ts]).fetchdf()

    def get_historical(
        self,
        plant_name: str,
        start_date: Union[date, str],
        end_date: Union[date, str],
    ) -> pd.DataFrame:
        """Return daily historical rows as a DataFrame."""
        sql = """
            SELECT *
            FROM weather_historical
            WHERE plant_name = ?
              AND date >= ?
              AND date <= ?
            ORDER BY date
        """
        with self._conn(read_only=not self._in_memory) as conn:
            return conn.execute(sql, [plant_name, start_date, end_date]).fetchdf()

    def get_available_plants(self, table: str = "weather_forecasts") -> list[str]:
        """Return distinct plant_name values from the given table."""
        allowed = {"weather_forecasts", "weather_historical"}
        if table not in allowed:
            raise ValueError(f"Unknown table '{table}'. Must be one of {allowed}.")
        with self._conn(read_only=not self._in_memory) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT plant_name FROM {table} ORDER BY plant_name"
            ).fetchall()
        return [row[0] for row in rows]
