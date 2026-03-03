"""Historical Performance Ratio (PR) calculations using irradiance + generation data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

# ── Constants ──────────────────────────────────────────────────────────────────
PR_MIN_EXPECTED = 0.5    # kWh — below this, skip PR (near-zero irradiance period)
PR_MAX_PLAUSIBLE = 1.10  # flag if PR exceeds this (likely data or measurement error)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DailyPR:
    """Performance Ratio result for a single calendar day."""

    plant_name: str
    date: date
    actual_kwh: float
    expected_kwh: float       # H_poa * capacity_kwp
    h_poa_kwh_m2: float       # plane-of-array irradiance (kWh/m²)
    capacity_kwp: float
    pr: Optional[float]       # None when expected_kwh < PR_MIN_EXPECTED


@dataclass(frozen=True)
class MonthlyPR:
    """Performance Ratio aggregated over a calendar month."""

    plant_name: str
    year: int
    month: int
    actual_kwh: float
    expected_kwh: float
    h_poa_kwh_m2: float
    capacity_kwp: float
    pr: Optional[float]
    days_with_data: int


# ── Calculator ─────────────────────────────────────────────────────────────────

class HistoricalPRCalculator:
    """Calculates daily and monthly Performance Ratio from generation + irradiance.

    Supports two irradiance input modes:
    - Hourly: pass a DataFrame with `timestamp`, `generation_kwh`, `ghi_wm2`
      (from Open-Meteo actuals or historical hourly data)
    - Daily: pass a DataFrame with `date`, `actual_kwh`, `ghi_kwh_m2`
      (from NASA POWER DailyHistoricalRecord data)
    """

    def __init__(self, capacity_kwp: float, plant_name: str = "") -> None:
        self.capacity_kwp = capacity_kwp
        self.plant_name = plant_name

    # ── helpers ────────────────────────────────────────────────────────────────

    def _compute_pr(self, expected_kwh: float, actual_kwh: float) -> Optional[float]:
        """Return PR ratio, or None if expected_kwh is below the minimum threshold."""
        if expected_kwh < PR_MIN_EXPECTED:
            return None
        return actual_kwh / expected_kwh

    # ── public methods ─────────────────────────────────────────────────────────

    def daily_pr_from_hourly(
        self,
        df: pd.DataFrame,
        ts_col: str = "timestamp",
        gen_col: str = "generation_kwh",
        ghi_col: str = "ghi_wm2",
    ) -> list[DailyPR]:
        """Calculate daily PR from hourly generation + GHI data.

        GHI should be in W/m². Converts to kWh/m² by dividing by 1000.
        """
        if df.empty:
            return []

        work = df[[ts_col, gen_col, ghi_col]].copy()
        work[ts_col] = pd.to_datetime(work[ts_col])
        work = work.set_index(ts_col)

        # Convert W/m² → kWh/m² for each hourly interval, then aggregate daily
        work["h_poa_kwh_m2"] = work[ghi_col] / 1000.0

        daily = work.resample("D").agg(
            actual_kwh=(gen_col, "sum"),
            h_poa_kwh_m2=("h_poa_kwh_m2", "sum"),
        )

        results: list[DailyPR] = []
        for day_ts, row in daily.iterrows():
            h_poa = float(row["h_poa_kwh_m2"])
            actual = float(row["actual_kwh"])
            expected = h_poa * self.capacity_kwp
            results.append(
                DailyPR(
                    plant_name=self.plant_name,
                    date=day_ts.date(),
                    actual_kwh=actual,
                    expected_kwh=expected,
                    h_poa_kwh_m2=h_poa,
                    capacity_kwp=self.capacity_kwp,
                    pr=self._compute_pr(expected, actual),
                )
            )

        return results

    def daily_pr_from_nasa(
        self,
        df: pd.DataFrame,
        date_col: str = "date",
        gen_col: str = "actual_kwh",
        irr_col: str = "ghi_kwh_m2",
    ) -> list[DailyPR]:
        """Calculate daily PR from NASA POWER daily GHI (already in kWh/m²)."""
        if df.empty:
            return []

        results: list[DailyPR] = []
        for _, row in df.iterrows():
            h_poa = float(row[irr_col])
            actual = float(row[gen_col])
            expected = h_poa * self.capacity_kwp

            # Normalise date value to datetime.date
            raw_date = row[date_col]
            if hasattr(raw_date, "date"):
                day = raw_date.date()
            elif isinstance(raw_date, date):
                day = raw_date
            else:
                day = pd.Timestamp(raw_date).date()

            results.append(
                DailyPR(
                    plant_name=self.plant_name,
                    date=day,
                    actual_kwh=actual,
                    expected_kwh=expected,
                    h_poa_kwh_m2=h_poa,
                    capacity_kwp=self.capacity_kwp,
                    pr=self._compute_pr(expected, actual),
                )
            )

        return results

    def monthly_pr(self, daily_prs: list[DailyPR]) -> list[MonthlyPR]:
        """Aggregate daily PR records into monthly summaries.

        Monthly PR = sum(actual_kwh) / sum(expected_kwh) for the month.
        Not an average of daily PRs.
        """
        if not daily_prs:
            return []

        # Group by (year, month)
        groups: dict[tuple[int, int], list[DailyPR]] = {}
        for record in daily_prs:
            key = (record.date.year, record.date.month)
            groups.setdefault(key, []).append(record)

        results: list[MonthlyPR] = []
        for (year, month), records in sorted(groups.items()):
            total_actual = sum(r.actual_kwh for r in records)
            total_expected = sum(r.expected_kwh for r in records)
            total_h_poa = sum(r.h_poa_kwh_m2 for r in records)
            days_with_data = len(records)

            results.append(
                MonthlyPR(
                    plant_name=self.plant_name,
                    year=year,
                    month=month,
                    actual_kwh=total_actual,
                    expected_kwh=total_expected,
                    h_poa_kwh_m2=total_h_poa,
                    capacity_kwp=self.capacity_kwp,
                    pr=self._compute_pr(total_expected, total_actual),
                    days_with_data=days_with_data,
                )
            )

        return results

    def flag_anomalies(
        self,
        daily_prs: list[DailyPR],
        pr_low_threshold: float = 0.60,
        pr_high_threshold: float = PR_MAX_PLAUSIBLE,
    ) -> list[DailyPR]:
        """Return daily PR records where PR is outside acceptable range.

        Returns records where PR < pr_low_threshold or PR > pr_high_threshold,
        or where pr is None (insufficient irradiance data to compute PR).
        """
        anomalies: list[DailyPR] = []
        for record in daily_prs:
            if record.pr is None:
                anomalies.append(record)
            elif record.pr < pr_low_threshold or record.pr > pr_high_threshold:
                anomalies.append(record)
        return anomalies
