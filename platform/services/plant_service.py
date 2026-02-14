"""
Plant-level business logic.

Single plant operations: detail, daily summary, device list.
Framework-agnostic — no Streamlit imports.

DESIGN NOTES FOR EXTRACTION:
- When adding FastAPI, expose as GET /api/plants/{uid}
- Same service, different transport
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from services.database.repository import PlantRepository, ReadingsRepository
from services.logging import get_logger

logger = get_logger("services.plant")


class PlantService:
    """Single-plant operations."""

    def __init__(self):
        self._plants = PlantRepository()
        self._readings = ReadingsRepository()

    def get_plant(self, uid: str) -> dict[str, Any] | None:
        """Get plant details with current PR."""
        plant = self._plants.get_by_uid(uid)
        if plant is None:
            return None
        now = datetime.now(UTC)
        pr = self._get_pr(uid, now - timedelta(hours=24), now)
        plant["current_pr"] = pr
        return plant

    def get_all_plants(self) -> list[dict[str, Any]]:
        """Get all plants as list of dicts."""
        df = self._plants.get_all()
        if df.empty:
            return []
        return df.to_dict("records")

    def get_daily_summary(self, uid: str) -> dict[str, Any]:
        """Get today's summary for a plant."""
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        gen = self._get_generation(uid, today_start, now)
        pr = self._get_pr(uid, today_start, now)
        power = self._get_latest_power(uid)

        return {
            "today_mwh": (gen or 0) / 1000,
            "current_kw": power or 0,
            "pr": pr or 0,
            "availability": 99.5,  # Placeholder until availability calculation
        }

    def get_production_data(self, uid: str, days: int = 30) -> pd.DataFrame:
        """Get production data for charts."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        return self._readings.get_readings(uid, start=start, end=end)

    def get_devices(self, uid: str) -> list[dict[str, Any]]:
        """Get list of devices for a plant.
        
        Extracts unique device IDs from the readings table.
        """
        try:
            df = self._readings.get_readings(uid, limit=10000)
            if df.empty:
                return []
            device_col = None
            for candidate in ["device_id", "emig_id", "inverter_id"]:
                if candidate in df.columns:
                    device_col = candidate
                    break
            if device_col is None:
                return []
            devices = df[device_col].unique()
            return [{"device_id": str(d), "type": "inverter"} for d in devices if pd.notna(d)]
        except Exception as e:
            logger.warning("devices_fetch_failed", plant_uid=uid, error=str(e))
            return []

    # ── Private helpers ─────────────────────────────────────────────

    def _get_generation(self, uid: str, start: datetime, end: datetime) -> float | None:
        """Total generation (kWh) for a plant in period."""
        try:
            df = self._readings.get_readings(uid, start=start, end=end)
            if df.empty:
                return None
            energy_cols = [c for c in df.columns if any(
                kw in c.lower() for kw in ["energy", "generation", "yield", "kwh", "e_grid"]
            )]
            if energy_cols:
                return float(df[energy_cols[0]].sum())
            power_cols = [c for c in df.columns if any(
                kw in c.lower() for kw in ["power", "pac", "p_grid", "kw"]
            )]
            if power_cols:
                return float(df[power_cols[0]].sum()) * 0.25
            return None
        except Exception as e:
            logger.warning("generation_failed", uid=uid, error=str(e))
            return None

    def _get_pr(self, uid: str, start: datetime, end: datetime) -> float | None:
        """Performance ratio for a plant in period."""
        try:
            df = self._readings.get_readings(uid, start=start, end=end)
            if df.empty:
                return None
            pr_cols = [c for c in df.columns if "pr" in c.lower() or "performance_ratio" in c.lower()]
            if pr_cols:
                val = df[pr_cols[0]].mean()
                return float(val) if pd.notna(val) else None
            return None
        except Exception as e:
            logger.warning("pr_failed", uid=uid, error=str(e))
            return None

    def _get_latest_power(self, uid: str) -> float | None:
        """Get latest power reading (kW)."""
        try:
            df = self._readings.get_readings(uid, limit=1)
            if df.empty:
                return None
            power_cols = [c for c in df.columns if any(
                kw in c.lower() for kw in ["power", "pac", "p_grid", "kw"]
            )]
            if power_cols:
                val = df[power_cols[0]].iloc[-1]
                return float(val) if pd.notna(val) else None
            return None
        except Exception as e:
            logger.warning("latest_power_failed", uid=uid, error=str(e))
            return None
