"""Forecast accuracy metrics for solar generation forecasts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ForecastVsActual:
    """Per-point comparison of forecast vs measured generation."""

    plant_name: str
    timestamp: datetime
    forecast_kwh: float
    actual_kwh: float
    error_kwh: float        # actual - forecast
    abs_error_kwh: float    # |actual - forecast|
    pct_error: Optional[float]  # (actual - forecast) / actual * 100; None if actual == 0


@dataclass(frozen=True)
class AccuracyMetrics:
    """Aggregate accuracy metrics for a single site over a time period."""

    plant_name: str
    n_points: int
    mae_kwh: float          # Mean Absolute Error
    rmse_kwh: float         # Root Mean Square Error
    mbe_kwh: float          # Mean Bias Error (positive = underforecast)
    mape_pct: Optional[float]    # Mean Absolute Percentage Error; None if any actual == 0
    r2: Optional[float]          # R² coefficient of determination; None if < 2 points
    skill_score: Optional[float] # 1 - RMSE_model/RMSE_persistence; None if not computed
    period_start: Optional[datetime]
    period_end: Optional[datetime]


# ── Service ────────────────────────────────────────────────────────────────────

class ForecastAccuracyService:
    """Compare forecast generation against actuals and compute error metrics."""

    # ------------------------------------------------------------------
    # compare()
    # ------------------------------------------------------------------

    def compare(
        self,
        plant_name: str,
        forecast_df: pd.DataFrame,
        actual_df: pd.DataFrame,
        forecast_ts_col: str = "timestamp",
        forecast_gen_col: str = "generation_kwh",
        actual_ts_col: str = "timestamp",
        actual_gen_col: str = "generation_kwh",
        tolerance_minutes: int = 15,
    ) -> list[ForecastVsActual]:
        """Align forecast and actual by timestamp and compute per-point errors.

        Uses ``pd.merge_asof`` with ``direction='nearest'`` so each forecast
        timestamp is matched to the closest actual timestamp within
        *tolerance_minutes*.  Rows where either side is missing after the merge
        are dropped.

        Parameters
        ----------
        plant_name:
            Label attached to every returned ``ForecastVsActual``.
        forecast_df / actual_df:
            DataFrames containing at minimum a timestamp column and a generation
            column.  Column names are configurable via the ``*_col`` parameters.
        tolerance_minutes:
            Maximum allowed offset (in minutes) between forecast and actual
            timestamps for them to be considered the same observation window.
        """
        # --- prepare left (forecast) side --------------------------------
        left = (
            forecast_df[[forecast_ts_col, forecast_gen_col]]
            .copy()
            .rename(columns={forecast_ts_col: "_ts", forecast_gen_col: "forecast_kwh"})
            .sort_values("_ts")
            .reset_index(drop=True)
        )
        left["_ts"] = pd.to_datetime(left["_ts"])

        # --- prepare right (actual) side ---------------------------------
        right = (
            actual_df[[actual_ts_col, actual_gen_col]]
            .copy()
            .rename(columns={actual_ts_col: "_ts_act", actual_gen_col: "actual_kwh"})
            .sort_values("_ts_act")
            .reset_index(drop=True)
        )
        right["_ts_act"] = pd.to_datetime(right["_ts_act"])

        # --- merge_asof: nearest actual for each forecast timestamp ------
        merged = pd.merge_asof(
            left,
            right,
            left_on="_ts",
            right_on="_ts_act",
            tolerance=pd.Timedelta(minutes=tolerance_minutes),
            direction="nearest",
        )

        # Drop rows where either side has no match
        merged = merged.dropna(subset=["forecast_kwh", "actual_kwh"])

        results: list[ForecastVsActual] = []
        for _, row in merged.iterrows():
            actual = float(row["actual_kwh"])
            forecast = float(row["forecast_kwh"])
            error = actual - forecast
            abs_error = abs(error)
            pct_error: Optional[float] = (
                (error / actual * 100.0) if actual != 0.0 else None
            )
            results.append(
                ForecastVsActual(
                    plant_name=plant_name,
                    timestamp=row["_ts"].to_pydatetime(),
                    forecast_kwh=forecast,
                    actual_kwh=actual,
                    error_kwh=error,
                    abs_error_kwh=abs_error,
                    pct_error=pct_error,
                )
            )

        return results

    # ------------------------------------------------------------------
    # compute_metrics()
    # ------------------------------------------------------------------

    def compute_metrics(
        self,
        comparisons: list[ForecastVsActual],
    ) -> AccuracyMetrics:
        """Compute aggregate accuracy metrics from a list of ForecastVsActual.

        Parameters
        ----------
        comparisons:
            Non-empty list of per-point comparison objects (must all share the
            same ``plant_name``).

        Returns
        -------
        AccuracyMetrics
            Aggregate metrics.  ``skill_score`` is always ``None`` here; use
            :meth:`skill_score` to compute it separately.
        """
        if not comparisons:
            raise ValueError("comparisons list must not be empty")

        plant_name = comparisons[0].plant_name
        n = len(comparisons)

        actuals = np.array([c.actual_kwh for c in comparisons], dtype=float)
        forecasts = np.array([c.forecast_kwh for c in comparisons], dtype=float)
        errors = actuals - forecasts  # positive → underforecast

        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        mbe = float(np.mean(errors))

        # MAPE — exclude rows where actual == 0
        nonzero = actuals != 0.0
        mape: Optional[float] = (
            float(np.mean(np.abs(errors[nonzero] / actuals[nonzero]) * 100.0))
            if np.any(nonzero)
            else None
        )

        # R² — skipped when fewer than 2 points
        r2: Optional[float]
        if n < 2:
            r2 = None
        else:
            ss_res = float(np.sum(errors ** 2))
            ss_tot = float(np.sum((actuals - actuals.mean()) ** 2))
            r2 = (1.0 - ss_res / ss_tot) if ss_tot != 0.0 else None

        timestamps = [c.timestamp for c in comparisons]

        return AccuracyMetrics(
            plant_name=plant_name,
            n_points=n,
            mae_kwh=mae,
            rmse_kwh=rmse,
            mbe_kwh=mbe,
            mape_pct=mape,
            r2=r2,
            skill_score=None,
            period_start=min(timestamps),
            period_end=max(timestamps),
        )

    # ------------------------------------------------------------------
    # skill_score()
    # ------------------------------------------------------------------

    def skill_score(
        self,
        comparisons: list[ForecastVsActual],
        persistence_comparisons: list[ForecastVsActual],
    ) -> float:
        """Compute skill score: ``1 - RMSE_model / RMSE_persistence``.

        A positive score means the model beats the persistence baseline.
        Zero means equal performance.  Negative means worse than persistence.

        Parameters
        ----------
        comparisons:
            Model forecast comparisons.
        persistence_comparisons:
            Persistence (naïve) forecast comparisons (same actuals, different
            forecasts).
        """
        def _rmse(comps: list[ForecastVsActual]) -> float:
            errs = np.array(
                [c.actual_kwh - c.forecast_kwh for c in comps], dtype=float
            )
            return float(np.sqrt(np.mean(errs ** 2)))

        rmse_model = _rmse(comparisons)
        rmse_pers = _rmse(persistence_comparisons)

        if rmse_pers == 0.0:
            return 0.0 if rmse_model == 0.0 else float("-inf")

        return 1.0 - rmse_model / rmse_pers
