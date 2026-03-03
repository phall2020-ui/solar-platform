"""Fleet-wide forecast accuracy aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from solar_platform.weather.accuracy import (
    AccuracyMetrics,
    ForecastAccuracyService,
    ForecastVsActual,
)


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FleetAccuracySummary:
    """Aggregated accuracy metrics across an entire portfolio of sites."""

    n_sites: int
    fleet_mae_kwh: float    # capacity-weighted average MAE
    fleet_rmse_kwh: float   # capacity-weighted average RMSE
    fleet_mbe_kwh: float    # capacity-weighted MBE
    best_site: Optional[str]   # site with lowest MAE
    worst_site: Optional[str]  # site with highest MAE
    sites: list[AccuracyMetrics]  # per-site metrics (insertion order preserved)


# ── Service ────────────────────────────────────────────────────────────────────

class FleetAccuracyService:
    """Aggregate accuracy metrics across multiple sites."""

    def __init__(self) -> None:
        self._accuracy_svc = ForecastAccuracyService()

    # ------------------------------------------------------------------
    # compute_fleet_accuracy()
    # ------------------------------------------------------------------

    def compute_fleet_accuracy(
        self,
        site_comparisons: dict[str, list[ForecastVsActual]],
        site_capacities: Optional[dict[str, float]] = None,
    ) -> FleetAccuracySummary:
        """Compute fleet summary from per-site comparison lists.

        Parameters
        ----------
        site_comparisons:
            Mapping of ``plant_name`` → list of ``ForecastVsActual`` objects.
        site_capacities:
            Optional mapping of ``plant_name`` → installed capacity in kWp.
            Used as weights for the fleet-level averages.  When ``None`` all
            sites receive equal weight (1.0).

        Returns
        -------
        FleetAccuracySummary
        """
        if not site_comparisons:
            raise ValueError("site_comparisons must not be empty")

        # --- per-site metrics -------------------------------------------
        site_metrics: list[AccuracyMetrics] = []
        for plant_name, comps in site_comparisons.items():
            metrics = self._accuracy_svc.compute_metrics(comps)
            site_metrics.append(metrics)

        n_sites = len(site_metrics)

        # --- weights ----------------------------------------------------
        if site_capacities is None:
            weights = np.ones(n_sites, dtype=float)
        else:
            weights = np.array(
                [site_capacities.get(m.plant_name, 1.0) for m in site_metrics],
                dtype=float,
            )

        weights_norm = weights / weights.sum()

        mae_arr = np.array([m.mae_kwh for m in site_metrics], dtype=float)
        rmse_arr = np.array([m.rmse_kwh for m in site_metrics], dtype=float)
        mbe_arr = np.array([m.mbe_kwh for m in site_metrics], dtype=float)

        fleet_mae = float(np.dot(weights_norm, mae_arr))
        fleet_rmse = float(np.dot(weights_norm, rmse_arr))
        fleet_mbe = float(np.dot(weights_norm, mbe_arr))

        # --- best / worst by MAE ----------------------------------------
        best_idx = int(np.argmin(mae_arr))
        worst_idx = int(np.argmax(mae_arr))
        best_site: Optional[str] = site_metrics[best_idx].plant_name
        worst_site: Optional[str] = site_metrics[worst_idx].plant_name

        return FleetAccuracySummary(
            n_sites=n_sites,
            fleet_mae_kwh=fleet_mae,
            fleet_rmse_kwh=fleet_rmse,
            fleet_mbe_kwh=fleet_mbe,
            best_site=best_site,
            worst_site=worst_site,
            sites=site_metrics,
        )

    # ------------------------------------------------------------------
    # to_dataframe()
    # ------------------------------------------------------------------

    def to_dataframe(self, summary: FleetAccuracySummary) -> pd.DataFrame:
        """Return per-site metrics as a DataFrame sorted by MAE ascending.

        Columns: ``plant_name``, ``n_points``, ``mae_kwh``, ``rmse_kwh``,
        ``mbe_kwh``, ``mape_pct``, ``r2``, ``period_start``, ``period_end``.
        """
        rows = [
            {
                "plant_name": m.plant_name,
                "n_points": m.n_points,
                "mae_kwh": m.mae_kwh,
                "rmse_kwh": m.rmse_kwh,
                "mbe_kwh": m.mbe_kwh,
                "mape_pct": m.mape_pct,
                "r2": m.r2,
                "period_start": m.period_start,
                "period_end": m.period_end,
            }
            for m in summary.sites
        ]
        df = pd.DataFrame(rows)
        return df.sort_values("mae_kwh", ascending=True).reset_index(drop=True)
