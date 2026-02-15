#!/usr/bin/env python3
"""
Import "All Sites" monthly summary workbooks into DuckDB `solar_data`.

This script ingests workbooks shaped like:
  - Sheet: "Whole Period Summary"
  - Columns:
      Site name, Site ID, kWp, Start date, End date,
      Actual generation (kWh), Budget generation (kWh), Weather adjusted budget (kWh),
      Total self consumption (kWh), Total export (kWh),
      Actual PR (%), Target PR (%), Actual availability (%), Target availability (%),
      ...

It maps those into the existing DuckDB `solar_data` schema used by the app.
Missing irradiance columns are left NULL (unless you enrich via other pipelines).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd


SOLAR_DATA_COLUMNS_ORDERED = [
    "Site",
    "Type",
    "kWp",
    "Date",
    "Actual Gen (kWh)",
    "Forecast Gen (kWh)",
    "Gen Dev. (%)",
    "kWh/kWp",
    "Calculated Exp (kWh)",
    "Net Usage (kWh)",
    "Actual Irr (kWh/m2)",
    "Forecast Irr",
    "Irradiance-based generation",
    "Irr Variation (kWh)",
    "Actual PR (%)",
    "Forecast PR (%)",
    "Availability (%)",
]


def _month_label(dt: pd.Timestamp) -> str:
    # Match existing `solar_data` month format, e.g. "Jan-26".
    return dt.strftime("%b-%y")


def _to_float(series: pd.Series) -> pd.Series:
    # Handles numeric columns that might arrive as strings with commas.
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def _pct_to_fraction(series: pd.Series) -> pd.Series:
    s = _to_float(series)
    # Values in the source are typically 0-100; convert to 0-1.
    return s.where(s.isna() | (s <= 1), s / 100.0)


def load_all_sites_workbook(
    xlsx_path: Path,
    *,
    sheet: str = "Whole Period Summary",
) -> tuple[pd.DataFrame, str]:
    df = pd.read_excel(xlsx_path, sheet_name=sheet)

    required = {
        "Site name",
        "kWp",
        "Start date",
        "End date",
        "Actual generation (kWh)",
        "Budget generation (kWh)",
        "Weather adjusted budget (kWh)",
        "Total self consumption (kWh)",
        "Total export (kWh)",
        "Actual PR (%)",
        "Target PR (%)",
        "Actual availability (%)",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {xlsx_path.name}: {sorted(missing)}")

    start = pd.to_datetime(df["Start date"], dayfirst=True, errors="coerce")
    end = pd.to_datetime(df["End date"], dayfirst=True, errors="coerce")
    if start.isna().all() or end.isna().all():
        raise ValueError("Could not parse Start date / End date columns")

    # Workbooks are expected to represent a single month (one start/end across all rows).
    start_mode = start.mode(dropna=True)
    end_mode = end.mode(dropna=True)
    month_start = start_mode.iloc[0] if not start_mode.empty else start.dropna().iloc[0]
    month_end = end_mode.iloc[0] if not end_mode.empty else end.dropna().iloc[0]
    if month_start.month != month_end.month or month_start.year != month_end.year:
        raise ValueError(f"Workbook spans multiple months: {month_start.date()} → {month_end.date()}")

    month = _month_label(pd.Timestamp(month_start))

    out = pd.DataFrame()
    out["Site"] = df["Site name"].astype(str).str.strip()
    out["Type"] = None  # Not provided by source workbook; keep NULL.
    out["kWp"] = _to_float(df["kWp"])
    out["Date"] = month
    out["Actual Gen (kWh)"] = _to_float(df["Actual generation (kWh)"])
    out["Forecast Gen (kWh)"] = _to_float(df["Budget generation (kWh)"])
    out["Irradiance-based generation"] = _to_float(df["Weather adjusted budget (kWh)"])
    out["Calculated Exp (kWh)"] = _to_float(df["Total export (kWh)"])
    out["Net Usage (kWh)"] = _to_float(df["Total self consumption (kWh)"])
    out["Actual PR (%)"] = _pct_to_fraction(df["Actual PR (%)"])
    out["Forecast PR (%)"] = _pct_to_fraction(df["Target PR (%)"])
    out["Availability (%)"] = _pct_to_fraction(df["Actual availability (%)"])

    # Derived metrics
    out["Gen Dev. (%)"] = None
    mask = out["Forecast Gen (kWh)"].notna() & (out["Forecast Gen (kWh)"] > 0) & out["Actual Gen (kWh)"].notna()
    out.loc[mask, "Gen Dev. (%)"] = (
        (out.loc[mask, "Actual Gen (kWh)"] - out.loc[mask, "Forecast Gen (kWh)"]) / out.loc[mask, "Forecast Gen (kWh)"]
    )

    out["kWh/kWp"] = None
    mask = out["kWp"].notna() & (out["kWp"] > 0) & out["Actual Gen (kWh)"].notna()
    out.loc[mask, "kWh/kWp"] = out.loc[mask, "Actual Gen (kWh)"] / out.loc[mask, "kWp"]

    out["Irr Variation (kWh)"] = None
    mask = out["Irradiance-based generation"].notna() & out["Forecast Gen (kWh)"].notna()
    out.loc[mask, "Irr Variation (kWh)"] = out.loc[mask, "Irradiance-based generation"] - out.loc[mask, "Forecast Gen (kWh)"]

    # Not present in source workbook.
    out["Actual Irr (kWh/m2)"] = None
    out["Forecast Irr"] = None

    # Final shape/order
    out = out[SOLAR_DATA_COLUMNS_ORDERED]

    # Basic sanity checks
    if out["Site"].isna().any() or (out["Site"].astype(str).str.len() == 0).any():
        raise ValueError("One or more rows have an empty Site name after normalization")

    return out, month


def import_to_duckdb(*, db_path: Path, df: pd.DataFrame, month: str, dry_run: bool) -> None:
    conn = duckdb.connect(str(db_path), config={"access_mode": "automatic"})
    try:
        before_total = conn.execute("SELECT COUNT(*) FROM solar_data").fetchone()[0]
        before_month = conn.execute('SELECT COUNT(*) FROM solar_data WHERE "Date" = ?', [month]).fetchone()[0]

        print(f"DB: {db_path}")
        print(f"Incoming rows: {len(df)} for month={month}")
        print(f"solar_data rows before: total={before_total}, month={before_month}")

        if dry_run:
            print("\n[DRY RUN] Preview (first 5 rows):")
            with pd.option_context("display.max_columns", None):
                print(df.head(5))
            return

        conn.register("__incoming_df", df)
        conn.execute("CREATE TEMP TABLE __incoming AS SELECT * FROM __incoming_df")

        # Idempotent: replace rows for the same month+site.
        conn.execute(
            'DELETE FROM solar_data WHERE "Date" = ? AND "Site" IN (SELECT "Site" FROM __incoming)',
            [month],
        )

        cols_sql = ", ".join(f'"{c}"' for c in SOLAR_DATA_COLUMNS_ORDERED)
        conn.execute(f"INSERT INTO solar_data ({cols_sql}) SELECT {cols_sql} FROM __incoming")

        after_total = conn.execute("SELECT COUNT(*) FROM solar_data").fetchone()[0]
        after_month = conn.execute('SELECT COUNT(*) FROM solar_data WHERE "Date" = ?', [month]).fetchone()[0]
        print(f"\nsolar_data rows after: total={after_total}, month={after_month}")

        # Quick verification: count distinct sites for this month.
        n_sites = conn.execute('SELECT COUNT(DISTINCT "Site") FROM solar_data WHERE "Date" = ?', [month]).fetchone()[0]
        print(f"Distinct sites for {month}: {n_sites}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import All Sites workbook into DuckDB solar_data")
    parser.add_argument("--db-path", type=Path, default=Path.home() / ".solar_toolkit" / "plant_registry.duckdb")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to All Sites .xlsx file")
    parser.add_argument("--sheet", default="Whole Period Summary", help="Sheet name (default: Whole Period Summary)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without writing to DuckDB")
    args = parser.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"XLSX not found: {args.xlsx}")
    if not args.db_path.exists():
        raise SystemExit(f"DuckDB not found: {args.db_path}")

    df, month = load_all_sites_workbook(args.xlsx, sheet=args.sheet)
    import_to_duckdb(db_path=args.db_path, df=df, month=month, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

