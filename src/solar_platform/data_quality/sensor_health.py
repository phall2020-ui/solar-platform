"""Sensor health monitoring for solar plants.

Queries the ``readings`` table to compute per-plant health metrics over a
rolling window: uptime, flatline percentage, missing data, latency, and
error rate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import structlog

from solar_platform.db.engine import get_engine

logger = structlog.get_logger("data_quality.sensor_health")


class SensorHealthMonitor:
    """Compute sensor health indicators from stored readings."""

    def __init__(self) -> None:
        self.engine = get_engine()

    def compute_health(
        self,
        plant_uid: str,
        days: int = 30,
        expected_freq_minutes: int = 15,
    ) -> dict[str, Any]:
        """Return a health summary dict for *plant_uid* over the last *days*.

        Keys:
            - ``uptime_pct``: percentage of expected intervals that have data.
            - ``flatline_pct``: percentage of readings where power_kw is repeated
              identically for ≥ 6 consecutive intervals.
            - ``missing_pct``: 100 - uptime_pct.
            - ``latency_hours``: hours since the most recent reading.
            - ``error_rate``: fraction of readings with quality_score < 50
              (if ``quality_score`` column exists, else 0.0).
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        result: dict[str, Any] = {
            "plant_uid": plant_uid,
            "window_days": days,
            "uptime_pct": 0.0,
            "flatline_pct": 0.0,
            "missing_pct": 100.0,
            "latency_hours": None,
            "error_rate": 0.0,
        }

        if not self.engine.table_exists("readings"):
            logger.warning("sensor_health_skip", reason="readings table missing")
            return result

        # ── Fetch readings ────────────────────────────────────────────
        df = self.engine.execute_df(
            "SELECT * FROM readings WHERE plant_uid = ? AND timestamp >= ? ORDER BY timestamp",
            (plant_uid, start),
        )

        if df.empty:
            logger.info("sensor_health_no_data", plant_uid=plant_uid)
            return result

        total_expected = days * 24 * 60 / expected_freq_minutes
        actual_count = len(df)

        # ── Uptime / missing ──────────────────────────────────────────
        uptime = min(actual_count / total_expected * 100, 100.0) if total_expected > 0 else 0.0
        result["uptime_pct"] = round(uptime, 2)
        result["missing_pct"] = round(100.0 - uptime, 2)

        # ── Latency ──────────────────────────────────────────────────
        ts_col = "timestamp"
        if ts_col in df.columns:
            latest = pd.to_datetime(df[ts_col]).max()
            if pd.notna(latest):
                if latest.tzinfo is None:
                    latest = latest.tz_localize("UTC")
                latency = (now - latest).total_seconds() / 3600
                result["latency_hours"] = round(latency, 2)

        # ── Flatline detection ────────────────────────────────────────
        result["flatline_pct"] = self._flatline_pct(df)

        # ── Error rate (quality_score based) ──────────────────────────
        if "quality_score" in df.columns:
            low_quality = (df["quality_score"] < 50).sum()
            result["error_rate"] = round(low_quality / len(df), 4) if len(df) > 0 else 0.0

        logger.info(
            "sensor_health_computed",
            plant_uid=plant_uid,
            uptime_pct=result["uptime_pct"],
            latency_hours=result["latency_hours"],
        )
        return result

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _flatline_pct(df: pd.DataFrame, column: str = "power_kw", min_run: int = 6) -> float:
        """Percentage of readings that belong to a flat-line run of ≥ *min_run*."""
        if column not in df.columns or df.empty:
            return 0.0

        values = df[column].tolist()
        total = len(values)
        flatline_count = 0
        run_length = 1

        for i in range(1, total):
            if values[i] is not None and values[i] == values[i - 1]:
                run_length += 1
            else:
                if run_length >= min_run:
                    flatline_count += run_length
                run_length = 1
        # trailing run
        if run_length >= min_run:
            flatline_count += run_length

        return round(flatline_count / total * 100, 2) if total > 0 else 0.0
