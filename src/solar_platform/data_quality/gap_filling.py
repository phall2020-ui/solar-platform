"""Gap filling strategies for solar time-series data.

Implements a Strategy pattern with pluggable filling algorithms.  Every
filled reading is tagged with ``source="estimated"`` so downstream consumers
can distinguish measured from synthetic data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import structlog

from solar_platform.data_quality.gap_detection import DataGap

logger = structlog.get_logger("data_quality.gap_filling")


# Numeric columns eligible for interpolation / estimation.
_NUMERIC_COLUMNS: list[str] = [
    "power_kw",
    "energy_kwh",
    "ghi_wm2",
    "poa_wm2",
    "dni_wm2",
    "dhi_wm2",
    "ambient_temp_c",
    "module_temp_c",
    "wind_speed_ms",
]


@dataclass
class FilledReading:
    """A single synthetic reading generated to fill a gap."""

    timestamp: datetime
    plant_uid: str
    device_id: str = ""
    source: str = "estimated"
    values: dict[str, float] = field(default_factory=dict)
    strategy_used: str = ""


# ── Strategy ABC ─────────────────────────────────────────────────────────


class GapFillingStrategy(ABC):
    """Abstract base for gap-filling algorithms."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""

    @abstractmethod
    def fill(
        self,
        gap: DataGap,
        surrounding: pd.DataFrame,
        freq_minutes: int,
    ) -> list[FilledReading]:
        """Generate synthetic readings to cover *gap*.

        Args:
            gap: The gap to fill.
            surrounding: Readings immediately before and after the gap
                          (a DataFrame with a ``timestamp`` column).
            freq_minutes: Expected interval between readings.

        Returns:
            List of :class:`FilledReading` instances covering the gap.
        """


# ── Linear interpolation ────────────────────────────────────────────────


class LinearInterpolation(GapFillingStrategy):
    """Fill by linearly interpolating between boundary readings."""

    @property
    def name(self) -> str:
        return "linear_interpolation"

    def fill(
        self,
        gap: DataGap,
        surrounding: pd.DataFrame,
        freq_minutes: int,
    ) -> list[FilledReading]:
        if surrounding.empty or len(surrounding) < 2:
            logger.warning("linear_interp_skip", reason="insufficient surrounding data")
            return []

        surrounding = surrounding.sort_values("timestamp").reset_index(drop=True)

        # Identify the last reading before the gap and first reading after
        before = surrounding[surrounding["timestamp"] <= gap.start]
        after = surrounding[surrounding["timestamp"] >= gap.end]

        if before.empty or after.empty:
            return []

        row_before = before.iloc[-1]
        row_after = after.iloc[0]
        total_s = (row_after["timestamp"] - row_before["timestamp"]).total_seconds()
        if total_s <= 0:
            return []

        filled: list[FilledReading] = []
        ts = gap.start + timedelta(minutes=freq_minutes)
        while ts < gap.end:
            frac = (ts - row_before["timestamp"]).total_seconds() / total_s
            values: dict[str, float] = {}
            for col in _NUMERIC_COLUMNS:
                vb = row_before.get(col)
                va = row_after.get(col)
                if pd.notna(vb) and pd.notna(va):
                    values[col] = round(float(vb) + (float(va) - float(vb)) * frac, 4)

            filled.append(
                FilledReading(
                    timestamp=ts,
                    plant_uid=gap.plant_uid,
                    device_id=gap.device_id,
                    source="estimated",
                    values=values,
                    strategy_used=self.name,
                )
            )
            ts += timedelta(minutes=freq_minutes)

        logger.info("linear_interp_done", gap_start=str(gap.start), readings_created=len(filled))
        return filled


# ── Typical-day profile ──────────────────────────────────────────────────


class TypicalDayProfile(GapFillingStrategy):
    """Fill gaps using a typical-day profile built from historical data.

    Computes the average value at each time-of-day (rounded to *freq_minutes*)
    from the *surrounding* data, then substitutes those averages into the gap.
    Best for longer (MEDIUM) gaps where interpolation is unreliable.
    """

    @property
    def name(self) -> str:
        return "typical_day_profile"

    def fill(
        self,
        gap: DataGap,
        surrounding: pd.DataFrame,
        freq_minutes: int,
    ) -> list[FilledReading]:
        if surrounding.empty:
            logger.warning("typical_day_skip", reason="no surrounding data")
            return []

        df = surrounding.copy()
        if "timestamp" not in df.columns:
            return []

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        # Build time-of-day key: (hour, minute_bucket)
        df["_tod"] = df["timestamp"].dt.hour * 60 + (
            df["timestamp"].dt.minute // freq_minutes * freq_minutes
        )

        # Compute average profile per time-of-day
        numeric_cols = [c for c in _NUMERIC_COLUMNS if c in df.columns]
        profile = df.groupby("_tod")[numeric_cols].mean()

        filled: list[FilledReading] = []
        ts = gap.start + timedelta(minutes=freq_minutes)
        while ts < gap.end:
            tod_key = ts.hour * 60 + (ts.minute // freq_minutes * freq_minutes)
            values: dict[str, float] = {}
            if tod_key in profile.index:
                row = profile.loc[tod_key]
                for col in numeric_cols:
                    v = row.get(col)
                    if pd.notna(v):
                        values[col] = round(float(v), 4)

            filled.append(
                FilledReading(
                    timestamp=ts,
                    plant_uid=gap.plant_uid,
                    device_id=gap.device_id,
                    source="estimated",
                    values=values,
                    strategy_used=self.name,
                )
            )
            ts += timedelta(minutes=freq_minutes)

        logger.info("typical_day_done", gap_start=str(gap.start), readings_created=len(filled))
        return filled


# ── Convenience helper ───────────────────────────────────────────────────


def auto_fill_gap(
    gap: DataGap,
    surrounding: pd.DataFrame,
    freq_minutes: int = 15,
) -> list[FilledReading]:
    """Automatically select a filling strategy and apply it.

    * SHORT gaps (< 1 h): :class:`LinearInterpolation`.
    * MEDIUM gaps (1-24 h): :class:`TypicalDayProfile`.
    * LONG gaps (> 24 h): not filled — returns empty list with a log warning.

    All filled readings have ``source="estimated"``.
    """
    from solar_platform.data_quality.gap_detection import GapSeverity

    if gap.severity is GapSeverity.SHORT:
        strategy: GapFillingStrategy = LinearInterpolation()
    elif gap.severity is GapSeverity.MEDIUM:
        strategy = TypicalDayProfile()
    else:
        logger.warning(
            "gap_too_long_to_fill",
            plant_uid=gap.plant_uid,
            duration_minutes=gap.duration_minutes,
        )
        return []

    return strategy.fill(gap, surrounding, freq_minutes)
