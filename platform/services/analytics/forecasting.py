"""Generation forecasting for solar plants.

Provides persistence and statistical forecast methods behind a unified
:class:`ForecastService`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger("services.analytics.forecasting")


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
@dataclass
class Forecast:
    """Single forecast point."""

    plant_uid: str
    timestamp: datetime
    generation_kwh: float
    method: str
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Forecast method ABC
# ---------------------------------------------------------------------------
class ForecastMethod(ABC):
    """Abstract base for forecast algorithms."""

    @property
    @abstractmethod
    def method_name(self) -> str:
        """Unique method identifier."""

    @abstractmethod
    def forecast(
        self,
        plant_uid: str,
        historical_df: pd.DataFrame,
        horizon_hours: int,
    ) -> list[Forecast]:
        """Produce a list of hourly forecasts for *horizon_hours* ahead."""


# ---------------------------------------------------------------------------
# Persistence forecast — "tomorrow looks like today"
# ---------------------------------------------------------------------------
class PersistenceForecast(ForecastMethod):
    """Naïve persistence: project the most recent day's profile forward."""

    @property
    def method_name(self) -> str:
        return "persistence"

    def forecast(
        self,
        plant_uid: str,
        historical_df: pd.DataFrame,
        horizon_hours: int,
    ) -> list[Forecast]:
        gen_col = _resolve_generation_col(historical_df)
        ts_col = _resolve_ts_col(historical_df)
        if gen_col is None or ts_col is None:
            logger.warning("persistence_missing_columns", plant_uid=plant_uid)
            return []

        df = historical_df[[ts_col, gen_col]].copy()
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        df = df.dropna(subset=[ts_col, gen_col])
        if df.empty:
            return []

        df = df.sort_values(ts_col)
        df = df.set_index(ts_col)
        df[gen_col] = pd.to_numeric(df[gen_col], errors="coerce")

        # Take last 24 h of data as template
        last_ts = df.index.max()
        window_start = last_ts - timedelta(hours=24)
        recent = df.loc[window_start:]

        if recent.empty:
            recent = df.tail(24)

        # Resample to hourly to get a clean profile
        hourly = recent[gen_col].resample("h").mean().dropna()
        if hourly.empty:
            return []

        template = hourly.values
        n_template = len(template)

        now = datetime.now(UTC)
        forecasts: list[Forecast] = []
        for h in range(horizon_hours):
            ts = now + timedelta(hours=h + 1)
            gen = float(template[h % n_template])
            forecasts.append(
                Forecast(
                    plant_uid=plant_uid,
                    timestamp=ts,
                    generation_kwh=max(gen, 0.0),
                    method=self.method_name,
                    confidence_low=max(gen * 0.8, 0.0),
                    confidence_high=gen * 1.2,
                )
            )
        return forecasts


# ---------------------------------------------------------------------------
# Statistical forecast — hourly mean ± std from historical data
# ---------------------------------------------------------------------------
class StatisticalForecast(ForecastMethod):
    """Forecast using hour-of-day statistics from the historical window."""

    @property
    def method_name(self) -> str:
        return "statistical"

    def forecast(
        self,
        plant_uid: str,
        historical_df: pd.DataFrame,
        horizon_hours: int,
    ) -> list[Forecast]:
        gen_col = _resolve_generation_col(historical_df)
        ts_col = _resolve_ts_col(historical_df)
        if gen_col is None or ts_col is None:
            logger.warning("statistical_missing_columns", plant_uid=plant_uid)
            return []

        df = historical_df[[ts_col, gen_col]].copy()
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        df = df.dropna(subset=[ts_col, gen_col])
        if df.empty:
            return []

        df[gen_col] = pd.to_numeric(df[gen_col], errors="coerce")
        df = df.dropna(subset=[gen_col])
        df["hour"] = df[ts_col].dt.hour

        stats = df.groupby("hour")[gen_col].agg(["mean", "std"]).fillna(0)

        now = datetime.now(UTC)
        forecasts: list[Forecast] = []
        for h in range(horizon_hours):
            ts = now + timedelta(hours=h + 1)
            hour_of_day = ts.hour
            if hour_of_day in stats.index:
                mean_val = float(stats.loc[hour_of_day, "mean"])
                std_val = float(stats.loc[hour_of_day, "std"])
            else:
                mean_val = 0.0
                std_val = 0.0

            forecasts.append(
                Forecast(
                    plant_uid=plant_uid,
                    timestamp=ts,
                    generation_kwh=max(mean_val, 0.0),
                    method=self.method_name,
                    confidence_low=max(mean_val - 1.96 * std_val, 0.0),
                    confidence_high=mean_val + 1.96 * std_val,
                )
            )
        return forecasts


# ---------------------------------------------------------------------------
# Orchestrating service
# ---------------------------------------------------------------------------
class ForecastService:
    """Unified forecasting entry-point."""

    def __init__(self, methods: list[ForecastMethod] | None = None):
        self.methods: list[ForecastMethod] = methods or [
            PersistenceForecast(),
            StatisticalForecast(),
        ]

    def forecast(
        self,
        plant_uid: str,
        historical_df: pd.DataFrame,
        horizon_hours: int = 24,
        method_name: str | None = None,
    ) -> list[Forecast]:
        """Generate forecasts.

        If *method_name* is given, only that method is used.  Otherwise the
        first method that returns results is used (priority order).
        """
        for method in self.methods:
            if method_name and method.method_name != method_name:
                continue
            try:
                results = method.forecast(plant_uid, historical_df, horizon_hours)
                if results:
                    logger.info(
                        "forecast_generated",
                        method=method.method_name,
                        plant_uid=plant_uid,
                        points=len(results),
                    )
                    return results
            except Exception:
                logger.exception(
                    "forecast_method_failed",
                    method=method.method_name,
                    plant_uid=plant_uid,
                )
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_GEN_CANDIDATES = ("generation_kwh", "gen_kwh", "energy_kwh", "kwh", "generation")
_TS_CANDIDATES = ("timestamp", "ts", "date", "datetime")


def _resolve_generation_col(df: pd.DataFrame) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in _GEN_CANDIDATES:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _resolve_ts_col(df: pd.DataFrame) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in _TS_CANDIDATES:
        if cand in cols_lower:
            return cols_lower[cand]
    return None
