"""Unit tests for ForecastAccuracyService (Task 4.1) and FleetAccuracyService (Task 4.2)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd
import pytest

from solar_platform.weather.accuracy import (
    AccuracyMetrics,
    ForecastAccuracyService,
    ForecastVsActual,
)
from solar_platform.weather.fleet_accuracy import FleetAccuracyService, FleetAccuracySummary


# ── Helpers ────────────────────────────────────────────────────────────────────

BASE_TS = datetime(2025, 6, 1, 6, 0, 0)


def _make_ts_seq(n: int, step_minutes: int = 60) -> list[datetime]:
    """Return *n* evenly-spaced timestamps starting at BASE_TS."""
    return [BASE_TS + timedelta(minutes=step_minutes * i) for i in range(n)]


def _make_fva(
    plant: str,
    timestamp: datetime,
    forecast: float,
    actual: float,
) -> ForecastVsActual:
    """Construct a ForecastVsActual from raw values."""
    error = actual - forecast
    pct = (error / actual * 100.0) if actual != 0.0 else None
    return ForecastVsActual(
        plant_name=plant,
        timestamp=timestamp,
        forecast_kwh=forecast,
        actual_kwh=actual,
        error_kwh=error,
        abs_error_kwh=abs(error),
        pct_error=pct,
    )


def _make_forecast_df(
    timestamps: list[datetime],
    values: list[float],
) -> pd.DataFrame:
    return pd.DataFrame({"timestamp": timestamps, "generation_kwh": values})


# ── Task 4.1 tests ─────────────────────────────────────────────────────────────

class TestCompare:
    """Tests for ForecastAccuracyService.compare()."""

    def setup_method(self):
        self.svc = ForecastAccuracyService()

    def test_compare_aligns_by_timestamp(self):
        """Five matching timestamps → five ForecastVsActual objects."""
        ts = _make_ts_seq(5)
        forecast_df = _make_forecast_df(ts, [100.0] * 5)
        actual_df = _make_forecast_df(ts, [90.0] * 5)

        result = self.svc.compare("Plant-A", forecast_df, actual_df)

        assert len(result) == 5
        assert all(isinstance(r, ForecastVsActual) for r in result)
        assert all(r.plant_name == "Plant-A" for r in result)

    def test_error_computation(self):
        """forecast=100, actual=80 → error=-20, abs_error=20, pct_error=-25.0."""
        ts = [BASE_TS]
        forecast_df = _make_forecast_df(ts, [100.0])
        actual_df = _make_forecast_df(ts, [80.0])

        result = self.svc.compare("Plant-B", forecast_df, actual_df)

        assert len(result) == 1
        r = result[0]
        assert r.forecast_kwh == pytest.approx(100.0)
        assert r.actual_kwh == pytest.approx(80.0)
        assert r.error_kwh == pytest.approx(-20.0)
        assert r.abs_error_kwh == pytest.approx(20.0)
        assert r.pct_error == pytest.approx(-25.0)

    def test_tolerance_drops_distant_timestamps(self):
        """Actual timestamp 20 min away with tolerance=15 → no match."""
        ts_forecast = [BASE_TS]
        ts_actual = [BASE_TS + timedelta(minutes=20)]
        forecast_df = _make_forecast_df(ts_forecast, [100.0])
        actual_df = _make_forecast_df(ts_actual, [80.0])

        result = self.svc.compare(
            "Plant-C", forecast_df, actual_df, tolerance_minutes=15
        )

        assert len(result) == 0

    def test_tolerance_matches_within_window(self):
        """Actual timestamp 10 min away with tolerance=15 → one match."""
        ts_forecast = [BASE_TS]
        ts_actual = [BASE_TS + timedelta(minutes=10)]
        forecast_df = _make_forecast_df(ts_forecast, [100.0])
        actual_df = _make_forecast_df(ts_actual, [80.0])

        result = self.svc.compare(
            "Plant-D", forecast_df, actual_df, tolerance_minutes=15
        )

        assert len(result) == 1


class TestComputeMetrics:
    """Tests for ForecastAccuracyService.compute_metrics()."""

    def setup_method(self):
        self.svc = ForecastAccuracyService()
        self.ts = _make_ts_seq(3)

    def _comps(self, forecasts: list[float], actuals: list[float]) -> list[ForecastVsActual]:
        return [
            _make_fva("Plant-X", self.ts[i], forecasts[i], actuals[i])
            for i in range(len(forecasts))
        ]

    def test_mae_calculation(self):
        """Errors [10, 20, 30] (actual > forecast) → MAE=20.0."""
        # actuals - forecasts == [10, 20, 30]
        comps = self._comps(
            forecasts=[90.0, 80.0, 70.0],
            actuals=[100.0, 100.0, 100.0],
        )
        metrics = self.svc.compute_metrics(comps)
        assert metrics.mae_kwh == pytest.approx(20.0)

    def test_rmse_calculation(self):
        """Errors [10, 20, 30] → RMSE = sqrt((100+400+900)/3) ≈ 21.602."""
        comps = self._comps(
            forecasts=[90.0, 80.0, 70.0],
            actuals=[100.0, 100.0, 100.0],
        )
        expected_rmse = math.sqrt((10 ** 2 + 20 ** 2 + 30 ** 2) / 3)
        metrics = self.svc.compute_metrics(comps)
        assert metrics.rmse_kwh == pytest.approx(expected_rmse, rel=1e-5)

    def test_mbe_positive_means_underforecast(self):
        """Forecast always below actual → MBE > 0 (positive = underforecast)."""
        comps = self._comps(
            forecasts=[80.0, 85.0, 90.0],  # all below actual
            actuals=[100.0, 100.0, 100.0],
        )
        metrics = self.svc.compute_metrics(comps)
        assert metrics.mbe_kwh > 0.0

    def test_mape_excludes_zero_actuals(self):
        """One zero-actual row is skipped; MAPE computed from non-zero rows only."""
        # actuals: [0, 80, 120], forecasts: [10, 100, 100]
        # errors:  [-10, -20, 20]
        # non-zero pct errors: |-20/80*100|=25.0, |20/120*100|≈16.667
        # MAPE ≈ mean(25.0, 16.667) ≈ 20.833
        ts = _make_ts_seq(3)
        comps = [
            _make_fva("Plant-X", ts[0], 10.0, 0.0),    # zero actual
            _make_fva("Plant-X", ts[1], 100.0, 80.0),
            _make_fva("Plant-X", ts[2], 100.0, 120.0),
        ]
        metrics = self.svc.compute_metrics(comps)
        assert metrics.mape_pct is not None
        assert metrics.mape_pct == pytest.approx((25.0 + 100 / 6) / 2, rel=1e-4)

    def test_r2_none_for_single_point(self):
        """R² is None when there is only one comparison point."""
        comps = [_make_fva("Plant-X", BASE_TS, 100.0, 90.0)]
        metrics = self.svc.compute_metrics(comps)
        assert metrics.r2 is None

    def test_n_points_correct(self):
        comps = self._comps([100.0] * 3, [90.0] * 3)
        metrics = self.svc.compute_metrics(comps)
        assert metrics.n_points == 3

    def test_period_start_end(self):
        comps = self._comps([100.0] * 3, [90.0] * 3)
        metrics = self.svc.compute_metrics(comps)
        assert metrics.period_start == self.ts[0]
        assert metrics.period_end == self.ts[2]

    def test_empty_comparisons_raises(self):
        with pytest.raises(ValueError):
            self.svc.compute_metrics([])


# ── Task 4.2 tests ─────────────────────────────────────────────────────────────

def _site_comps(
    plant: str,
    n: int,
    forecast_val: float,
    actual_val: float,
) -> list[ForecastVsActual]:
    """Build *n* identical ForecastVsActual entries for *plant*."""
    ts = _make_ts_seq(n)
    return [_make_fva(plant, ts[i], forecast_val, actual_val) for i in range(n)]


class TestFleetAccuracy:
    """Tests for FleetAccuracyService."""

    def setup_method(self):
        self.svc = FleetAccuracyService()

    def test_fleet_summary_n_sites(self):
        """Three sites → FleetAccuracySummary.n_sites == 3."""
        comparisons = {
            "A": _site_comps("A", 4, 90.0, 100.0),
            "B": _site_comps("B", 4, 80.0, 100.0),
            "C": _site_comps("C", 4, 70.0, 100.0),
        }
        summary = self.svc.compute_fleet_accuracy(comparisons)
        assert summary.n_sites == 3

    def test_fleet_best_worst_site(self):
        """Site A (MAE=5) beats site B (MAE=30) → best_site='A', worst_site='B'."""
        comparisons = {
            "A": _site_comps("A", 4, 95.0, 100.0),   # error=5 per point, MAE=5
            "B": _site_comps("B", 4, 70.0, 100.0),   # error=30 per point, MAE=30
        }
        summary = self.svc.compute_fleet_accuracy(comparisons)
        assert summary.best_site == "A"
        assert summary.worst_site == "B"

    def test_to_dataframe_sorted_by_mae(self):
        """DataFrame rows must be sorted by mae_kwh ascending."""
        comparisons = {
            "High": _site_comps("High", 4, 60.0, 100.0),  # MAE=40
            "Low": _site_comps("Low", 4, 95.0, 100.0),    # MAE=5
            "Mid": _site_comps("Mid", 4, 80.0, 100.0),    # MAE=20
        }
        summary = self.svc.compute_fleet_accuracy(comparisons)
        df = self.svc.to_dataframe(summary)

        assert list(df["plant_name"]) == ["Low", "Mid", "High"]
        assert df["mae_kwh"].is_monotonic_increasing

    def test_equal_weights_when_no_capacities(self):
        """site_capacities=None runs without error and produces sensible output."""
        comparisons = {
            "X": _site_comps("X", 3, 90.0, 100.0),
            "Y": _site_comps("Y", 3, 80.0, 100.0),
        }
        summary = self.svc.compute_fleet_accuracy(comparisons, site_capacities=None)
        # Equal weights → fleet_mae = mean(10, 20) = 15
        assert summary.fleet_mae_kwh == pytest.approx(15.0)
        assert isinstance(summary, FleetAccuracySummary)

    def test_capacity_weighted_mae(self):
        """Heavier-capacity site dominates the fleet MAE."""
        comparisons = {
            "Small": _site_comps("Small", 4, 95.0, 100.0),  # MAE=5, cap=1 kWp
            "Large": _site_comps("Large", 4, 60.0, 100.0),  # MAE=40, cap=9 kWp
        }
        capacities = {"Small": 1.0, "Large": 9.0}
        summary = self.svc.compute_fleet_accuracy(comparisons, site_capacities=capacities)
        # Weighted MAE = 0.1*5 + 0.9*40 = 0.5 + 36 = 36.5
        assert summary.fleet_mae_kwh == pytest.approx(36.5)

    def test_to_dataframe_columns(self):
        """DataFrame contains expected columns."""
        comparisons = {"A": _site_comps("A", 3, 90.0, 100.0)}
        summary = self.svc.compute_fleet_accuracy(comparisons)
        df = self.svc.to_dataframe(summary)
        expected_cols = {
            "plant_name", "n_points", "mae_kwh", "rmse_kwh",
            "mbe_kwh", "mape_pct", "r2", "period_start", "period_end",
        }
        assert expected_cols.issubset(set(df.columns))
