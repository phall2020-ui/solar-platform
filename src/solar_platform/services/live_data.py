"""
Live Data Service — unified access to real-time and recent plant readings.

Provides a clean interface for UI components that need:
  • Plant lists with metadata
  • Time-series readings with standardised column names
  • Daily KPI summaries
  • On-demand data refresh via the ingestion pipeline

All database access goes through :mod:`backend.database` and column names
from the raw DuckDB ``readings`` payload are mapped to a consistent schema.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from solar_platform.db.legacy import get_db
from solar_platform.config import get_settings
from solar_platform.services.logging import get_logger

logger = get_logger(__name__)

# ── Column mapping from raw payload → standard names ───────────────────

_COL_MAP: dict[str, str] = {
    "activePower_value": "power_kw",
    "poaIrradiance_value": "irradiance_wm2",
    "exportEnergy_value": "energy_kwh",
    "ambientTemperature_value": "temperature_c",
    "moduleTemperature_value": "temperature_c",  # fallback
}

_STANDARD_COLUMNS = [
    "ts",
    "device_id",
    "power_kw",
    "energy_kwh",
    "irradiance_wm2",
    "temperature_c",
]

# ── Cache TTL for plant list ───────────────────────────────────────────

_DEFAULT_PLANT_CACHE_TTL = 300  # seconds


class LiveDataService:
    """Centralised service for live / recent solar-plant data access."""

    # Class-level plant-list cache: {"data": [...], "ts": float}
    _plant_cache: dict[str, Any] = {}

    def __init__(self) -> None:
        self._settings = get_settings()

    # ──────────────────────────────────────────────────────────────────
    # 1. Plant list
    # ──────────────────────────────────────────────────────────────────

    def get_plant_list(self) -> list[dict[str, Any]]:
        """Return registered plants as ``[{uid, alias, dc_size_kw}, ...]``.

        Results are cached at the class level with a 5-minute TTL to avoid
        repeated DuckDB round-trips in a single Streamlit session.
        """
        now = time.monotonic()
        cached = self._plant_cache.get("data")
        cached_ts = self._plant_cache.get("ts", 0.0)

        if cached is not None and (now - cached_ts) < _DEFAULT_PLANT_CACHE_TTL:
            return cached  # type: ignore[return-value]

        try:
            db = get_db()
            plants = db.get_plants()
            result = [
                {
                    "uid": p.plant_uid,
                    "alias": p.alias,
                    "dc_size_kw": p.dc_size_kw,
                }
                for p in plants
            ]
            LiveDataService._plant_cache = {"data": result, "ts": now}
            logger.info("plant_list_refreshed", count=len(result))
            return result
        except Exception:
            logger.exception("failed_to_load_plant_list")
            return []

    # ──────────────────────────────────────────────────────────────────
    # 2. Readings (single day)
    # ──────────────────────────────────────────────────────────────────

    def get_readings(
        self,
        plant_uid: str,
        date: date,
        device_ids: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch readings for a single day and return a standardised DataFrame.

        Parameters
        ----------
        plant_uid:
            Unique plant identifier.
        date:
            Calendar date (UTC) to query.
        device_ids:
            Optional subset of device / EMIG IDs.

        Returns
        -------
        pd.DataFrame
            Columns: ``ts``, ``device_id``, ``power_kw``, ``energy_kwh``,
            ``irradiance_wm2``, ``temperature_c``.
        """
        start_str = date.isoformat()
        end_str = date.isoformat()

        return self._query_and_normalise(plant_uid, start_str, end_str, device_ids)

    # ──────────────────────────────────────────────────────────────────
    # 3. Daily KPIs
    # ──────────────────────────────────────────────────────────────────

    def get_daily_kpis(self, plant_uid: str, date: date) -> dict[str, Any]:
        """Compute key performance indicators for a single day.

        Parameters
        ----------
        plant_uid:
            Unique plant identifier.
        date:
            Calendar date (UTC).

        Returns
        -------
        dict
            Keys: ``total_energy_kwh``, ``peak_power_kw``, ``current_power_kw``,
            ``avg_irradiance_wm2``, ``capacity_kw``, ``pr_pct``,
            ``data_freshness``, ``reading_count``.
        """
        df = self.get_readings(plant_uid, date)

        # Look up plant capacity
        capacity_kw = self._get_plant_capacity(plant_uid)

        if df.empty:
            return {
                "total_energy_kwh": 0.0,
                "peak_power_kw": 0.0,
                "current_power_kw": 0.0,
                "avg_irradiance_wm2": 0.0,
                "capacity_kw": capacity_kw,
                "pr_pct": 0.0,
                "data_freshness": None,
                "reading_count": 0,
            }

        total_energy = float(df["energy_kwh"].sum()) if "energy_kwh" in df.columns else 0.0
        peak_power = float(df["power_kw"].max()) if "power_kw" in df.columns else 0.0
        avg_irradiance = float(df["irradiance_wm2"].mean()) if "irradiance_wm2" in df.columns else 0.0
        reading_count = len(df)

        # Latest reading → current power
        latest = df.sort_values("ts").iloc[-1]
        current_power = float(latest.get("power_kw", 0.0) or 0.0)
        data_freshness = latest["ts"] if pd.notna(latest["ts"]) else None

        # Performance ratio estimate: PR = E / (G * C * H)
        #   E = total energy (kWh)
        #   G = avg irradiance (W/m²) / 1000 → kW/m²
        #   C = capacity (kW)
        #   H = daylight hours approximation from data span
        pr_pct = self._estimate_pr(df, total_energy, avg_irradiance, capacity_kw)

        return {
            "total_energy_kwh": round(total_energy, 2),
            "peak_power_kw": round(peak_power, 2),
            "current_power_kw": round(current_power, 2),
            "avg_irradiance_wm2": round(avg_irradiance, 2),
            "capacity_kw": capacity_kw,
            "pr_pct": round(pr_pct, 2),
            "data_freshness": data_freshness,
            "reading_count": reading_count,
        }

    # ──────────────────────────────────────────────────────────────────
    # 4. Multi-day readings
    # ──────────────────────────────────────────────────────────────────

    def get_multi_day_readings(
        self,
        plant_uid: str,
        start_date: date,
        end_date: date,
        device_ids: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch readings across a date range.

        Used by the "go back previous days" UI functionality.

        Parameters
        ----------
        plant_uid:
            Unique plant identifier.
        start_date:
            First date (inclusive, UTC).
        end_date:
            Last date (inclusive, UTC).
        device_ids:
            Optional subset of device / EMIG IDs.

        Returns
        -------
        pd.DataFrame
            Same schema as :meth:`get_readings`.
        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        return self._query_and_normalise(plant_uid, start_str, end_str, device_ids)

    # ──────────────────────────────────────────────────────────────────
    # 5. Device list
    # ──────────────────────────────────────────────────────────────────

    def get_device_list(self, plant_uid: str) -> list[str]:
        """Return distinct device IDs that have readings for a plant.

        Parameters
        ----------
        plant_uid:
            Unique plant identifier.

        Returns
        -------
        list[str]
            Sorted list of device / EMIG ID strings.
        """
        try:
            db = get_db()
            return db.get_device_ids(plant_uid)
        except Exception:
            logger.exception("failed_to_get_device_list", plant_uid=plant_uid)
            return []

    # ──────────────────────────────────────────────────────────────────
    # 6. Live data refresh
    # ──────────────────────────────────────────────────────────────────

    def refresh_live_data(self, plant_uid: str) -> bool:
        """Trigger an on-demand data pull via the ingestion pipeline.

        Returns ``True`` on success, ``False`` if ingestion is not
        configured or the pull fails.
        """
        try:
            from solar_platform.ingestion.coordinator import IngestionCoordinator

            coord = IngestionCoordinator()
            end = datetime.now(tz=UTC)
            start = end - timedelta(hours=1)

            result = coord.sync_ingest_plant(plant_uid, start, end)
            logger.info(
                "live_refresh_complete",
                plant_uid=plant_uid,
                readings=getattr(result, "readings_stored", 0),
            )
            return True
        except ImportError:
            logger.warning("ingestion_not_available", plant_uid=plant_uid)
            return False
        except Exception:
            logger.exception("live_refresh_failed", plant_uid=plant_uid)
            return False

    # ══════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════

    def _query_and_normalise(
        self,
        plant_uid: str,
        start_str: str,
        end_str: str,
        device_ids: list[str] | None = None,
    ) -> pd.DataFrame:
        """Query DuckDB via ``DatabaseManager`` and map to standard columns."""
        try:
            db = get_db()
            df = db.query_readings_df(
                plant_uid,
                start_date=start_str,
                end_date=end_str,
                device_ids=device_ids,
                limit=50_000,
            )
        except Exception:
            logger.exception(
                "query_readings_failed",
                plant_uid=plant_uid,
                start=start_str,
                end=end_str,
            )
            return self._empty_df()

        if df.empty:
            return self._empty_df()

        return self._normalise(df)

    def _normalise(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map raw payload columns to the standard schema."""
        out = pd.DataFrame()

        # Timestamp
        out["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")

        # Device ID — raw column is ``emig_id``
        out["device_id"] = df["emig_id"].astype(str) if "emig_id" in df.columns else ""

        # Power (kW) — activePower_value is already in kW from EMIG
        out["power_kw"] = self._safe_numeric(df, "activePower_value")

        # Energy (kWh)
        out["energy_kwh"] = self._safe_numeric(df, "exportEnergy_value")

        # Irradiance (W/m²)
        out["irradiance_wm2"] = self._safe_numeric(df, "poaIrradiance_value")

        # Temperature (°C) — prefer module temp, fall back to ambient
        if "moduleTemperature_value" in df.columns:
            out["temperature_c"] = self._safe_numeric(df, "moduleTemperature_value")
        else:
            out["temperature_c"] = self._safe_numeric(df, "ambientTemperature_value")

        # Drop rows with no valid timestamp
        out = out.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)

        return out

    @staticmethod
    def _safe_numeric(df: pd.DataFrame, col: str) -> pd.Series:
        """Extract a column as float64, returning NaN where missing or invalid."""
        if col not in df.columns:
            return pd.Series([float("nan")] * len(df), dtype="float64")
        return pd.to_numeric(df[col], errors="coerce").astype("float64")

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        """Return an empty DataFrame with the standard column schema."""
        return pd.DataFrame(columns=_STANDARD_COLUMNS)

    def _get_plant_capacity(self, plant_uid: str) -> float:
        """Look up ``dc_size_kw`` for a plant, returning 0.0 on failure."""
        try:
            db = get_db()
            plant = db.get_plant(plant_uid)
            if plant and plant.dc_size_kw:
                return float(plant.dc_size_kw)
        except Exception:
            logger.warning("could_not_resolve_capacity", plant_uid=plant_uid)
        return 0.0

    @staticmethod
    def _estimate_pr(
        df: pd.DataFrame,
        total_energy: float,
        avg_irradiance: float,
        capacity_kw: float,
    ) -> float:
        """Estimate performance ratio from daily data.

        PR = E / (G_avg/1000 × C × H)

        where H is the number of hours spanned by the data with non-zero
        irradiance.
        """
        if not capacity_kw or not avg_irradiance or avg_irradiance <= 0:
            return 0.0

        try:
            irr_mask = df["irradiance_wm2"].notna() & (df["irradiance_wm2"] > 0)
            if irr_mask.sum() < 2:
                return 0.0

            ts_irr = df.loc[irr_mask, "ts"]
            span = (ts_irr.max() - ts_irr.min()).total_seconds() / 3600.0
            if span <= 0:
                return 0.0

            expected = (avg_irradiance / 1000.0) * capacity_kw * span
            if expected <= 0:
                return 0.0

            pr = (total_energy / expected) * 100.0
            return min(pr, 150.0)  # cap at 150 % to flag anomalies
        except Exception:
            return 0.0
