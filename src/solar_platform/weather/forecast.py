"""Weather-based solar generation forecasting.

Uses Open-Meteo hourly GHI forecasts combined with historical generation data
to produce efficiency-scaled forecasts.

Algorithm:
1. Compute historical "efficiency factor" = gen_kwh / ghi_wm2 for each hour-of-day
   (only where ghi >= GHI_MIN_WM2 to exclude night zeros)
2. For each forecast hour:
   a. Look up mean efficiency for that hour-of-day from historical stats
   b. Apply snow attenuation: factor = max(0, 1 - SNOW_PENALTY * snowfall_cm)
   c. forecast_kwh = ghi_wm2 * efficiency_mean * snow_factor
   d. confidence bounds use ±1 std of historical efficiency
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

GHI_MIN_WM2 = 5.0       # below this = night/zero — excluded from efficiency calc
SNOW_PENALTY = 0.10      # 10% generation loss per cm of snowfall
METHOD_NAME = "weather_ghi_scaled"


@dataclass(frozen=True)
class WeatherForecastPoint:
    """A single hourly forecast point produced by WeatherBasedForecaster."""

    plant_uid: str
    timestamp: datetime
    generation_kwh: float
    method: str
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    ghi_wm2: Optional[float] = None
    snow_factor: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class WeatherBasedForecaster:
    """Produces hourly generation forecasts by scaling GHI with historical efficiency.

    Parameters
    ----------
    min_historical_points_per_hour:
        Minimum data points per hour-of-day bucket to include that bucket in
        efficiency stats. Buckets below this threshold fall back to the fleet
        mean efficiency (or 0 if no data at all).
    """

    def __init__(self, min_historical_points_per_hour: int = 5):
        self.min_historical_points_per_hour = min_historical_points_per_hour

    def forecast(
        self,
        plant_uid: str,
        historical_gen_df: pd.DataFrame,
        weather_records: list,   # list[HourlyWeatherRecord] — typed as list to avoid circular import
        gen_col: str = "generation_kwh",
        ts_col: str = "timestamp",
    ) -> list[WeatherForecastPoint]:
        """Generate forecasts for the timespan covered by weather_records.

        Parameters
        ----------
        historical_gen_df:
            DataFrame with at minimum `ts_col` and `gen_col` columns.
            Must cover at least 7 days of history for meaningful efficiency stats.
        weather_records:
            List of HourlyWeatherRecord objects for the forecast period.
        """
        if not weather_records:
            return []

        eff_stats = self._compute_efficiency_stats(historical_gen_df, gen_col, ts_col)
        global_mean_eff = eff_stats["mean_efficiency"].mean() if not eff_stats.empty else 0.0

        results: list[WeatherForecastPoint] = []
        for rec in weather_records:
            ghi = rec.ghi_wm2
            if ghi is None or ghi < GHI_MIN_WM2:
                gen_kwh = 0.0
                ci_low = 0.0
                ci_high = 0.0
                snow_factor = 1.0
            else:
                hour = rec.timestamp.hour
                row = eff_stats.loc[hour] if hour in eff_stats.index else None

                if row is not None and row["count"] >= self.min_historical_points_per_hour:
                    mean_eff = float(row["mean_efficiency"])
                    std_eff = float(row["std_efficiency"])
                else:
                    mean_eff = global_mean_eff
                    std_eff = 0.0

                snow_factor = max(0.0, 1.0 - SNOW_PENALTY * (rec.snowfall_cm or 0.0))
                gen_kwh = max(0.0, ghi * mean_eff * snow_factor)
                ci_spread = ghi * std_eff * snow_factor * 1.96
                ci_low = max(0.0, gen_kwh - ci_spread)
                ci_high = gen_kwh + ci_spread

            results.append(WeatherForecastPoint(
                plant_uid=plant_uid,
                timestamp=rec.timestamp,
                generation_kwh=gen_kwh,
                method=METHOD_NAME,
                confidence_low=ci_low,
                confidence_high=ci_high,
                ghi_wm2=rec.ghi_wm2,
                snow_factor=snow_factor,
                metadata={"cloud_cover_pct": rec.cloud_cover_pct},
            ))

        return results

    def _compute_efficiency_stats(
        self,
        df: pd.DataFrame,
        gen_col: str,
        ts_col: str,
    ) -> pd.DataFrame:
        """Return per-hour-of-day mean/std efficiency (gen_kwh / ghi_wm2).

        Returns a DataFrame indexed by hour (0–23) with columns:
        mean_efficiency, std_efficiency, count.

        If the DataFrame lacks a 'ghi_wm2' column, returns an empty DataFrame
        (caller falls back to global_mean_eff = 0).
        """
        if "ghi_wm2" not in df.columns:
            return pd.DataFrame(
                columns=["mean_efficiency", "std_efficiency", "count"]
            )

        work = df[[ts_col, gen_col, "ghi_wm2"]].copy()
        work[ts_col] = pd.to_datetime(work[ts_col], errors="coerce")
        work[gen_col] = pd.to_numeric(work[gen_col], errors="coerce")
        work["ghi_wm2"] = pd.to_numeric(work["ghi_wm2"], errors="coerce")
        work = work.dropna()

        # Keep only daylight hours where GHI is meaningful
        work = work[work["ghi_wm2"] >= GHI_MIN_WM2]
        if work.empty:
            return pd.DataFrame(columns=["mean_efficiency", "std_efficiency", "count"])

        work["efficiency"] = work[gen_col] / work["ghi_wm2"]
        work["hour"] = work[ts_col].dt.hour

        stats = work.groupby("hour")["efficiency"].agg(
            mean_efficiency="mean",
            std_efficiency="std",
            count="count",
        ).fillna({"std_efficiency": 0.0})

        return stats
