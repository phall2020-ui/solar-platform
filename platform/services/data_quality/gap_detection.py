"""Gap detection in solar time-series data.

Identifies missing intervals in the ``readings`` table by comparing actual
timestamps against an expected regular grid at a given frequency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import pandas as pd
import structlog

from services.database.engine import get_engine

logger = structlog.get_logger("data_quality.gap_detection")


class GapSeverity(str, Enum):
    """Classification of gap length."""

    SHORT = "short"      # < 1 hour
    MEDIUM = "medium"    # 1 – 24 hours
    LONG = "long"        # > 24 hours


@dataclass(frozen=True)
class DataGap:
    """A contiguous period of missing data."""

    plant_uid: str
    start: datetime
    end: datetime
    severity: GapSeverity
    duration_minutes: float
    expected_readings: int
    device_id: str = ""

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def _classify(duration_minutes: float) -> GapSeverity:
    if duration_minutes < 60:
        return GapSeverity.SHORT
    if duration_minutes < 24 * 60:
        return GapSeverity.MEDIUM
    return GapSeverity.LONG


class GapDetector:
    """Detect gaps and measure daily completeness.

    Uses the DuckDB engine to query the ``readings`` table directly.
    """

    def __init__(self) -> None:
        self.engine = get_engine()

    def detect_gaps(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        expected_freq_minutes: int = 15,
        device_id: str | None = None,
    ) -> list[DataGap]:
        """Identify gaps in readings for a plant within a time range.

        Args:
            plant_uid: Plant unique identifier.
            start: Start of analysis window (inclusive).
            end: End of analysis window (inclusive).
            expected_freq_minutes: Expected interval between readings.
            device_id: Optional device filter.

        Returns:
            List of :class:`DataGap` instances sorted by start time.
        """
        if not self.engine.table_exists("readings"):
            logger.warning("gap_detect_skip", reason="readings table missing")
            return []

        conditions = ["plant_uid = ?", "timestamp >= ?", "timestamp <= ?"]
        params: list[Any] = [plant_uid, start, end]
        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)

        where = " AND ".join(conditions)
        sql = f"SELECT DISTINCT timestamp FROM readings WHERE {where} ORDER BY timestamp"
        df = self.engine.execute_df(sql, tuple(params))

        if df.empty:
            # Entire window is a gap
            dur = (end - start).total_seconds() / 60
            exp = int(dur / expected_freq_minutes)
            return [
                DataGap(
                    plant_uid=plant_uid,
                    start=start,
                    end=end,
                    severity=_classify(dur),
                    duration_minutes=round(dur, 1),
                    expected_readings=exp,
                    device_id=device_id or "",
                )
            ]

        timestamps = sorted(pd.to_datetime(df["timestamp"]).tolist())
        threshold_s = expected_freq_minutes * 60 * 1.5
        gaps: list[DataGap] = []

        # Check leading gap (start → first timestamp)
        if timestamps:
            first_delta = (timestamps[0] - start).total_seconds()
            if first_delta > threshold_s:
                dur_min = first_delta / 60
                gaps.append(
                    DataGap(
                        plant_uid=plant_uid,
                        start=start,
                        end=timestamps[0],
                        severity=_classify(dur_min),
                        duration_minutes=round(dur_min, 1),
                        expected_readings=max(int(first_delta / (expected_freq_minutes * 60)) - 1, 0),
                        device_id=device_id or "",
                    )
                )

        # Check inter-reading gaps
        for i in range(1, len(timestamps)):
            delta_s = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if delta_s > threshold_s:
                dur_min = delta_s / 60
                gaps.append(
                    DataGap(
                        plant_uid=plant_uid,
                        start=timestamps[i - 1],
                        end=timestamps[i],
                        severity=_classify(dur_min),
                        duration_minutes=round(dur_min, 1),
                        expected_readings=max(int(delta_s / (expected_freq_minutes * 60)) - 1, 0),
                        device_id=device_id or "",
                    )
                )

        # Check trailing gap (last timestamp → end)
        if timestamps:
            last_delta = (end - timestamps[-1]).total_seconds()
            if last_delta > threshold_s:
                dur_min = last_delta / 60
                gaps.append(
                    DataGap(
                        plant_uid=plant_uid,
                        start=timestamps[-1],
                        end=end,
                        severity=_classify(dur_min),
                        duration_minutes=round(dur_min, 1),
                        expected_readings=max(int(last_delta / (expected_freq_minutes * 60)) - 1, 0),
                        device_id=device_id or "",
                    )
                )

        logger.info("gaps_detected", plant_uid=plant_uid, gap_count=len(gaps))
        return gaps

    def daily_completeness(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        expected_freq_minutes: int = 15,
    ) -> pd.DataFrame:
        """Compute per-day completeness for a plant.

        Returns a DataFrame with columns: ``date``, ``expected``,
        ``actual``, ``completeness_pct``.
        """
        if not self.engine.table_exists("readings"):
            return pd.DataFrame(columns=["date", "expected", "actual", "completeness_pct"])

        sql = (
            "SELECT CAST(timestamp AS DATE) AS date, COUNT(*) AS actual "
            "FROM readings "
            "WHERE plant_uid = ? AND timestamp >= ? AND timestamp <= ? "
            "GROUP BY CAST(timestamp AS DATE) "
            "ORDER BY date"
        )
        df = self.engine.execute_df(sql, (plant_uid, start, end))

        expected_per_day = int(24 * 60 / expected_freq_minutes)

        if df.empty:
            return pd.DataFrame(columns=["date", "expected", "actual", "completeness_pct"])

        df["expected"] = expected_per_day
        df["completeness_pct"] = (df["actual"] / expected_per_day * 100).round(2).clip(upper=100.0)
        return df[["date", "expected", "actual", "completeness_pct"]]
