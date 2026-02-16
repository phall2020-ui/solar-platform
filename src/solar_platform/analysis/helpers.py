"""Shared utility functions for analysis engines."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd


TIME_COLUMN_CANDIDATES = ["timestamp", "ts", "datetime", "date", "time"]

# ---------------------------------------------------------------------------
# Column-name mappings for the Juggle-style payload after JSON expansion.
# Keys used in _expand_payload_columns (repository.py) produce names like
# ``importActivePower_value``, ``poaIrradiance_value``, etc.
#
# The lookup order below goes from *most specific* to *least specific* so
# ``find_numeric_column`` hits the right column.
# ---------------------------------------------------------------------------

POWER_KEYWORDS = [
    "importactivepower_value",
    "activepower_value",
    "activepower",
    "apparentpower_value",
    "apparentpower",
    "power",
    "pac",
    "p_ac",
    "ac_power",
    "kw",
]

IRRADIANCE_KEYWORDS = [
    "poairradiance_value",
    "horizontalirradiance_value",
    "poa",
    "irradiance",
    "gti",
    "ghi",
]

EXPORT_LIMIT_KEYWORDS = [
    "exportlimit_value",
    "export_limit",
    "limit_pct",
    "curtailment",
]

TEMPERATURE_KEYWORDS = [
    "devicetemperature_value",
    "module_temp",
    "cell_temp",
    "pv_temp",
    "temperature",
]


def detect_time_column(df: pd.DataFrame) -> str | None:
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
    return None


def coerce_datetime(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    out = df.copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    return out.dropna(subset=[time_col]).sort_values(time_col)


def find_numeric_column(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Find the first matching numeric column using keyword substring matching.

    Also attempts coercion for columns that contain numeric data stored as
    object/string dtype (common after JSON payload expansion).
    """
    lower_map = {c.lower(): c for c in df.columns}
    for key in keywords:
        for low, original in lower_map.items():
            if key in low:
                # Try to use the column even if dtype is object — the payload
                # expander sometimes leaves values as object strings.
                if pd.api.types.is_numeric_dtype(df[original]):
                    return original
                # Attempt coercion to see if it's actually numeric data
                try:
                    coerced = pd.to_numeric(df[original], errors="coerce")
                    if coerced.notna().any():
                        return original
                except Exception:
                    pass
    return None


def estimate_interval_hours(df: pd.DataFrame, time_col: str, default_hours: float = 0.5) -> float:
    if df.empty:
        return default_hours
    diffs = df[time_col].diff().dropna()
    if diffs.empty:
        return default_hours
    median_seconds = diffs.median().total_seconds()
    if median_seconds <= 0:
        return default_hours
    return float(median_seconds / 3600)


def estimate_energy_kwh(df: pd.DataFrame, power_col: str, time_col: str) -> float:
    """Estimate energy from a power timeseries.

    Handles either kW (pass-through) or W (divides by 1000) by inspecting
    the unit column if available (``<power_col_base>_unit``).
    """
    if df.empty or power_col not in df.columns or time_col not in df.columns:
        return 0.0
    hours = estimate_interval_hours(df, time_col)
    power = pd.to_numeric(df[power_col], errors="coerce").fillna(0.0)

    # Auto-detect W vs kW via companion _unit column
    unit_col = power_col.replace("_value", "_unit")
    if unit_col in df.columns:
        sample_unit = str(df[unit_col].dropna().iloc[0]).strip().lower() if df[unit_col].notna().any() else ""
        if sample_unit in ("w", "watt", "watts"):
            power = power / 1000.0  # convert W → kW

    return float((power * hours).sum())


def normalized_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    ratio = num / den.replace(0, np.nan)
    return ratio.replace([np.inf, -np.inf], np.nan)


def date_bounds_or_default(start: datetime | None, end: datetime | None, days: int = 30) -> tuple[datetime, datetime]:
    if start and end:
        return start, end
    now = datetime.now(UTC)
    if start and not end:
        return start, now
    if end and not start:
        return end - pd.Timedelta(days=days), end
    return now - pd.Timedelta(days=days), now


# ---------------------------------------------------------------------------
# Data merge: join inverter power rows with weather-station irradiance rows
# ---------------------------------------------------------------------------

def merge_power_and_irradiance(df: pd.DataFrame, ts_col: str) -> pd.DataFrame:
    """Merge inverter (power) and weather-station (irradiance) readings.

    In the Juggle data model, inverter readings and weather-station readings
    are stored as *separate rows* under the same ``plant_uid`` but with
    different ``emig_id`` values (``INVERT:*`` vs ``WETH:*``).
    After payload expansion they have different column sets:
    - Inverter rows: ``importActivePower_value``, ``apparentPower_value``, …
    - Weather rows:  ``poaIrradiance_value``, ``horizontalIrradiance_value``, …

    This function:
    1. Identifies irradiance rows (those with ``poaIrradiance_value`` not NaN
       or ``emig_id`` starting with ``WETH``).
    2. Pivots the irradiance data by timestamp.
    3. Merges it back onto inverter rows so every inverter reading carries the
       coincident irradiance.

    If the data already has power and irradiance in the same rows (non-Juggle
    format), the function is a no-op.
    """
    power_col = find_numeric_column(df, POWER_KEYWORDS)
    irr_col = find_numeric_column(df, IRRADIANCE_KEYWORDS)

    if not power_col or not irr_col:
        return df

    # Check if any rows already have both power and irradiance
    has_power = pd.to_numeric(df[power_col], errors="coerce").notna()
    has_irr = pd.to_numeric(df[irr_col], errors="coerce").notna()

    if (has_power & has_irr).any():
        # Data already merged — nothing to do
        return df

    # Separate weather rows and inverter rows
    irr_rows = df[has_irr].copy()
    inv_rows = df[has_power].copy()

    if irr_rows.empty or inv_rows.empty:
        return df

    # Build an irradiance lookup by timestamp
    irr_lookup = (
        irr_rows.groupby(ts_col, as_index=False)[irr_col]
        .first()
        .rename(columns={irr_col: "__irr_merged__"})
    )

    # Also grab horizontal irradiance if available
    hirr_col = find_numeric_column(df, ["horizontalirradiance_value", "ghi"])
    if hirr_col and hirr_col != irr_col:
        hirr_lookup = (
            irr_rows.groupby(ts_col, as_index=False)[hirr_col]
            .first()
            .rename(columns={hirr_col: "__hirr_merged__"})
        )
        irr_lookup = irr_lookup.merge(hirr_lookup, on=ts_col, how="left")

    # Merge onto inverter rows
    merged = inv_rows.merge(irr_lookup, on=ts_col, how="left")

    # Fill the original irradiance column with merged values
    merged[irr_col] = pd.to_numeric(merged.get("__irr_merged__"), errors="coerce")
    if "__irr_merged__" in merged.columns:
        merged = merged.drop(columns=["__irr_merged__"])
    if hirr_col and "__hirr_merged__" in merged.columns:
        merged[hirr_col] = pd.to_numeric(merged["__hirr_merged__"], errors="coerce")
        merged = merged.drop(columns=["__hirr_merged__"])

    return merged


def load_plant_capacity_kw(plant_uid: str) -> float | None:
    """Load dc_size_kw from the plant registry, or None."""
    try:
        from solar_platform.db.repository import PlantRepository
        plant = PlantRepository().get_by_uid(plant_uid)
        if plant:
            return float(plant.get("dc_size_kw") or 0) or None
    except Exception:
        pass
    return None
