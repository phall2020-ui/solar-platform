"""Shared utility functions for analysis engines."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd


TIME_COLUMN_CANDIDATES = ["timestamp", "ts", "datetime", "date", "time"]


def detect_time_column(df: pd.DataFrame) -> str | None:
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
    return None


def coerce_datetime(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    out = df.copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
    return out.dropna(subset=[time_col]).sort_values(time_col)


def find_numeric_column(df: pd.DataFrame, keywords: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for key in keywords:
        for low, original in lower_map.items():
            if key in low and pd.api.types.is_numeric_dtype(df[original]):
                return original
    return None


def estimate_interval_hours(df: pd.DataFrame, time_col: str, default_hours: float = 0.25) -> float:
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
    if df.empty or power_col not in df.columns or time_col not in df.columns:
        return 0.0
    hours = estimate_interval_hours(df, time_col)
    power = pd.to_numeric(df[power_col], errors="coerce").fillna(0.0)
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
