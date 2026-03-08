"""Unit tests for HistoricalPRCalculator (Task 3.2).

All tests use synthetic DataFrames — no network calls.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from solar_platform.weather.pr_calculator import (
    PR_MAX_PLAUSIBLE,
    PR_MIN_EXPECTED,
    DailyPR,
    HistoricalPRCalculator,
    MonthlyPR,
)


# ── fixtures / helpers ─────────────────────────────────────────────────────────

def _make_hourly_df(
    n_days: int = 7,
    gen_kwh: float = 100.0,
    ghi_wm2: float = 1000.0,
    start: date | None = None,
) -> pd.DataFrame:
    """Build a synthetic hourly DataFrame with flat gen + flat GHI during 08–16h.

    Each day has 8 daylight hours (08:00–15:00 inclusive) with the given values;
    night hours carry zero generation and zero GHI.
    """
    if start is None:
        start = date(2025, 6, 1)

    rows = []
    for day_offset in range(n_days):
        day = start + timedelta(days=day_offset)
        for hour in range(24):
            if 8 <= hour < 16:
                rows.append(
                    {
                        "timestamp": pd.Timestamp(day.year, day.month, day.day, hour),
                        "generation_kwh": gen_kwh / 8.0,  # spread evenly over 8 h
                        "ghi_wm2": ghi_wm2,
                    }
                )
            else:
                rows.append(
                    {
                        "timestamp": pd.Timestamp(day.year, day.month, day.day, hour),
                        "generation_kwh": 0.0,
                        "ghi_wm2": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def _make_nasa_df(
    n_days: int = 7,
    gen_kwh: float = 680.0,
    ghi_kwh_m2: float = 8.0,
    start: date | None = None,
) -> pd.DataFrame:
    """Build a synthetic daily NASA-style DataFrame."""
    if start is None:
        start = date(2025, 6, 1)
    rows = [
        {
            "date": start + timedelta(days=i),
            "actual_kwh": gen_kwh,
            "ghi_kwh_m2": ghi_kwh_m2,
        }
        for i in range(n_days)
    ]
    return pd.DataFrame(rows)


# ── Test 1: known-value daily PR (hourly path) ─────────────────────────────────

def test_daily_pr_correct_value() -> None:
    """
    Setup:   capacity = 100 kWp
             GHI = 1000 W/m² for 8 hours → H_poa = 8 * (1000/1000) = 8 kWh/m²
             expected_kwh = 8 * 100 = 800 kWh
             actual_kwh   = 680 kWh (gen_kwh / 8 spread over 8 hours => 680 total)
             PR = 680 / 800 = 0.85
    """
    df = _make_hourly_df(n_days=1, gen_kwh=680.0, ghi_wm2=1000.0)
    calc = HistoricalPRCalculator(capacity_kwp=100.0, plant_name="TestPlant")
    results = calc.daily_pr_from_hourly(df)

    assert len(results) == 1
    r = results[0]
    assert r.capacity_kwp == 100.0
    assert pytest.approx(r.h_poa_kwh_m2, abs=1e-6) == 8.0
    assert pytest.approx(r.expected_kwh, abs=1e-6) == 800.0
    assert pytest.approx(r.actual_kwh, abs=1e-6) == 680.0
    assert r.pr is not None
    assert pytest.approx(r.pr, abs=1e-4) == 0.85


# ── Test 2: zero irradiance gives pr=None ──────────────────────────────────────

def test_zero_irradiance_gives_none_pr() -> None:
    df = _make_hourly_df(n_days=3, gen_kwh=0.0, ghi_wm2=0.0)
    calc = HistoricalPRCalculator(capacity_kwp=50.0)
    results = calc.daily_pr_from_hourly(df)

    assert len(results) == 3
    for r in results:
        assert r.pr is None, f"Expected None PR for zero irradiance, got {r.pr}"
        assert r.expected_kwh < PR_MIN_EXPECTED


# ── Test 3: monthly PR aggregation ────────────────────────────────────────────

def test_monthly_pr_aggregation() -> None:
    """30 days of constant values → monthly PR = sum actual / sum expected."""
    n_days = 30
    gen_kwh = 680.0
    ghi_wm2 = 1000.0
    capacity = 100.0

    df = _make_hourly_df(n_days=n_days, gen_kwh=gen_kwh, ghi_wm2=ghi_wm2)
    calc = HistoricalPRCalculator(capacity_kwp=capacity)
    daily = calc.daily_pr_from_hourly(df)
    monthly = calc.monthly_pr(daily)

    assert len(monthly) >= 1
    # All 30 days may span two months; check the first month
    m = monthly[0]
    total_actual = sum(r.actual_kwh for r in daily if r.date.month == m.month)
    total_expected = sum(r.expected_kwh for r in daily if r.date.month == m.month)

    assert pytest.approx(m.actual_kwh, abs=1e-3) == total_actual
    assert pytest.approx(m.expected_kwh, abs=1e-3) == total_expected
    assert m.pr is not None
    assert pytest.approx(m.pr, abs=1e-4) == total_actual / total_expected


# ── Test 4: flag_anomalies catches low PR ──────────────────────────────────────

def test_flag_anomalies_low_pr() -> None:
    """One day with very low generation should appear in flag_anomalies() results."""
    n_days = 7
    capacity = 100.0

    # Normal days: PR ≈ 0.85
    df = _make_hourly_df(n_days=n_days, gen_kwh=680.0, ghi_wm2=1000.0)
    calc = HistoricalPRCalculator(capacity_kwp=capacity)
    daily = calc.daily_pr_from_hourly(df)

    # Inject one day with rock-bottom generation (PR ~ 0.05)
    bad_day = DailyPR(
        plant_name="",
        date=date(2025, 7, 1),
        actual_kwh=40.0,
        expected_kwh=800.0,
        h_poa_kwh_m2=8.0,
        capacity_kwp=capacity,
        pr=40.0 / 800.0,
    )
    anomalies = calc.flag_anomalies(daily + [bad_day], pr_low_threshold=0.60)

    assert bad_day in anomalies
    # None of the normal days (PR ≈ 0.85) should be flagged as low
    normal_flagged = [a for a in anomalies if a is not bad_day]
    assert all(a.pr is None or a.pr < 0.60 or a.pr > PR_MAX_PLAUSIBLE for a in normal_flagged)


# ── Test 5: flag_anomalies catches high PR ────────────────────────────────────

def test_flag_anomalies_high_pr() -> None:
    """One day with generation exceeding expected should appear in flag_anomalies()."""
    capacity = 100.0
    df = _make_hourly_df(n_days=5, gen_kwh=680.0, ghi_wm2=1000.0)
    calc = HistoricalPRCalculator(capacity_kwp=capacity)
    daily = calc.daily_pr_from_hourly(df)

    # PR > PR_MAX_PLAUSIBLE (e.g. data error: gen reported twice)
    suspicious_pr = PR_MAX_PLAUSIBLE + 0.05
    high_day = DailyPR(
        plant_name="",
        date=date(2025, 8, 1),
        actual_kwh=suspicious_pr * 800.0,
        expected_kwh=800.0,
        h_poa_kwh_m2=8.0,
        capacity_kwp=capacity,
        pr=suspicious_pr,
    )
    anomalies = calc.flag_anomalies(daily + [high_day])

    assert high_day in anomalies
    # Normal days must not appear in anomaly list (PR ≈ 0.85 is fine)
    normal_in_anomalies = [a for a in anomalies if a is not high_day]
    for a in normal_in_anomalies:
        assert a.pr is None or a.pr >= PR_MAX_PLAUSIBLE or a.pr < 0.60


# ── Test 6: NASA daily path ───────────────────────────────────────────────────

def test_nasa_daily_pr() -> None:
    """daily_pr_from_nasa returns correct DailyPR objects from NASA-style DataFrame."""
    capacity = 100.0
    gen = 680.0
    ghi = 8.0  # kWh/m² (already converted for daily NASA data)

    df = _make_nasa_df(n_days=5, gen_kwh=gen, ghi_kwh_m2=ghi)
    calc = HistoricalPRCalculator(capacity_kwp=capacity)
    results = calc.daily_pr_from_nasa(df)

    assert len(results) == 5
    for r in results:
        assert pytest.approx(r.h_poa_kwh_m2, abs=1e-6) == ghi
        assert pytest.approx(r.expected_kwh, abs=1e-6) == ghi * capacity
        assert pytest.approx(r.actual_kwh, abs=1e-6) == gen
        assert r.pr is not None
        assert pytest.approx(r.pr, abs=1e-4) == gen / (ghi * capacity)


# ── Test 7: days_with_data count ──────────────────────────────────────────────

def test_monthly_pr_days_with_data_count() -> None:
    """MonthlyPR.days_with_data equals the number of daily records in that month."""
    # Use a short range entirely within one calendar month
    start = date(2025, 6, 1)
    n_days = 15
    df = _make_hourly_df(n_days=n_days, gen_kwh=680.0, ghi_wm2=1000.0, start=start)
    calc = HistoricalPRCalculator(capacity_kwp=100.0)
    daily = calc.daily_pr_from_hourly(df)
    monthly = calc.monthly_pr(daily)

    assert len(monthly) == 1
    assert monthly[0].days_with_data == n_days
