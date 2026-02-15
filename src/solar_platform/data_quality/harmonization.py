"""Multi-source data harmonization for solar readings.

When a plant has data from multiple sources (SCADA, monitoring portal,
satellite, etc.) this module aligns, normalises, and deduplicates them
into a single consistent time-series.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd
import structlog

from solar_platform.data_quality.source_priority import SOURCE_PRIORITY, pick_best_source

logger = structlog.get_logger("data_quality.harmonization")


# ── Unit conversion helpers ──────────────────────────────────────────────

_UNIT_CONVERSIONS: dict[str, dict[str, float]] = {
    # column → { from_unit: multiplier_to_standard }
    "power_kw": {"w": 0.001, "kw": 1.0, "mw": 1000.0},
    "energy_kwh": {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0},
    "poa_wm2": {"wm2": 1.0, "kwm2": 1000.0},
    "ghi_wm2": {"wm2": 1.0, "kwm2": 1000.0},
    "ambient_temp_c": {"c": 1.0, "f": None},  # handled specially
}


def _convert_f_to_c(val: float) -> float:
    return (val - 32.0) * 5.0 / 9.0


class MultiSourceHarmonizer:
    """Pipeline for harmonizing multi-source solar data.

    Typical usage::

        harmonizer = MultiSourceHarmonizer()
        result = harmonizer.harmonize(df, freq_minutes=15)
    """

    def __init__(self, freq_minutes: int = 15) -> None:
        self.freq_minutes = freq_minutes

    # ── Pipeline steps ───────────────────────────────────────────────

    def align_timestamps(
        self,
        df: pd.DataFrame,
        freq_minutes: int | None = None,
    ) -> pd.DataFrame:
        """Round timestamps to the nearest frequency bucket.

        Args:
            df: Must have a ``timestamp`` column.
            freq_minutes: Resolution in minutes (default: instance setting).

        Returns:
            DataFrame with aligned ``timestamp`` column.
        """
        freq = freq_minutes or self.freq_minutes
        result = df.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"])
        result["timestamp"] = result["timestamp"].dt.round(f"{freq}min")
        logger.debug("timestamps_aligned", rows=len(result), freq_minutes=freq)
        return result

    def normalize_units(
        self,
        df: pd.DataFrame,
        unit_hints: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        """Convert columns to standard units using *unit_hints*.

        *unit_hints* maps column names to their current unit, e.g.
        ``{"power_kw": "mw", "ambient_temp_c": "f"}``.

        If no hints are provided the data passes through unchanged.
        """
        if not unit_hints:
            return df
        result = df.copy()
        for col, unit in unit_hints.items():
            if col not in result.columns:
                continue
            unit_lower = unit.lower()
            if col == "ambient_temp_c" and unit_lower == "f":
                result[col] = result[col].apply(
                    lambda v: _convert_f_to_c(float(v)) if pd.notna(v) else v
                )
                logger.debug("unit_converted", column=col, from_unit="F", to_unit="C")
                continue
            conversions = _UNIT_CONVERSIONS.get(col, {})
            multiplier = conversions.get(unit_lower)
            if multiplier is not None and multiplier != 1.0:
                result[col] = result[col] * multiplier
                logger.debug("unit_converted", column=col, from_unit=unit, multiplier=multiplier)
        return result

    def deduplicate_sources(
        self,
        df: pd.DataFrame,
        timestamp_col: str = "timestamp",
        source_col: str = "source",
        device_col: str = "device_id",
    ) -> pd.DataFrame:
        """When multiple sources provide data for the same timestamp + device,
        keep only the highest-priority source.

        Returns a deduplicated DataFrame.
        """
        if source_col not in df.columns:
            return df
        result = df.copy()

        def _priority(src: Any) -> int:
            return SOURCE_PRIORITY.get(str(src).lower(), 0)

        result["_src_prio"] = result[source_col].apply(_priority)

        group_cols = [timestamp_col]
        if device_col in result.columns:
            group_cols.append(device_col)

        result = result.sort_values("_src_prio", ascending=False)
        result = result.drop_duplicates(subset=group_cols, keep="first")
        result = result.drop(columns=["_src_prio"]).sort_values(timestamp_col).reset_index(drop=True)

        logger.info("deduplicated", rows_in=len(df), rows_out=len(result))
        return result

    def harmonize(
        self,
        df: pd.DataFrame,
        freq_minutes: int | None = None,
        unit_hints: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        """Run the full harmonization pipeline.

        Steps:
        1. Align timestamps to regular grid.
        2. Normalise units.
        3. Deduplicate across sources.

        Returns a clean, deduplicated DataFrame.
        """
        freq = freq_minutes or self.freq_minutes
        result = self.align_timestamps(df, freq)
        result = self.normalize_units(result, unit_hints)
        result = self.deduplicate_sources(result)
        logger.info("harmonization_complete", rows=len(result), freq_minutes=freq)
        return result
