#!/usr/bin/env python3
"""
Import ADE Excom monthly spreadsheets into DuckDB `solar_data`.

These workbooks typically contain a sheet like "<Month> - postPAC" with columns
already close to the DuckDB `solar_data` schema.

This script:
1. Detects the best sheet to import (or uses --sheet)
2. Normalizes a few column-name variants to match the `solar_data` table
3. Replaces rows for the same (Date, Site) idempotently
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


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def _pct_to_fraction(series: pd.Series) -> pd.Series:
    s = _to_float(series)
    return s.where(s.isna() | (s <= 1), s / 100.0)


def _score_sheet(df: pd.DataFrame) -> int:
    cols = set(df.columns)
    required = {
        "Site",
        "Date",
        "Actual Gen (kWh)",
        "Forecast Gen (kWh)",
        "Actual PR (%)",
        "Forecast PR (%)",
        "Availability (%)",
    }
    score = len(required & cols)
    # Bonus points for having irradiance columns (prefer richer sheets).
    score += int("Actual Irr (kWh/m2)" in cols)
    score += int(any(c in cols for c in ("Forecast Irr (kWh/m2)", "Forecast Irr")))
    score += int(any(c in cols for c in ("Irr Losses (kWh)", "Irr Variation (kWh)")))
    score += int("Irradiance-based generation" in cols)
    return score


def detect_best_sheet(xlsx_path: Path) -> str:
    xl = pd.ExcelFile(xlsx_path)
    best_sheet = None
    best_score = -1

    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet, nrows=5)  # small sniff
        except Exception:
            continue
        score = _score_sheet(df)
        # Prefer postPAC sheets on tie.
        tie_break = 1 if "postpac" in sheet.lower() else 0
        if (score, tie_break) > (best_score, 1 if (best_sheet and "postpac" in best_sheet.lower()) else 0):
            best_score = score
            best_sheet = sheet

    if not best_sheet or best_score <= 0:
        raise ValueError(f"Could not detect an importable sheet in {xlsx_path.name}")
    return best_sheet


def load_excom_sheet(xlsx_path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=sheet)

    # Drop empty rows and keep rows with a Site value.
    if "Site" not in df.columns:
        raise ValueError(f"Sheet {sheet!r} missing required column 'Site'")
    df = df.dropna(how="all")
    df = df[df["Site"].notna()]

    # Normalize known column variants.
    if "Forecast Irr (kWh/m2)" in df.columns and "Forecast Irr" not in df.columns:
        df = df.rename(columns={"Forecast Irr (kWh/m2)": "Forecast Irr"})
    if "Forecast Irr (kWh/m²)" in df.columns and "Forecast Irr" not in df.columns:
        df = df.rename(columns={"Forecast Irr (kWh/m²)": "Forecast Irr"})

    if "Irr Losses (kWh)" in df.columns and "Irr Variation (kWh)" not in df.columns:
        # In these spreadsheets, "Irr Losses" is typically the delta between irradiance-adjusted and forecast.
        df = df.rename(columns={"Irr Losses (kWh)": "Irr Variation (kWh)"})

    # If the sheet doesn't provide Irr Variation, we can compute it when both columns exist.
    if "Irr Variation (kWh)" not in df.columns and {"Irradiance-based generation", "Forecast Gen (kWh)"} <= set(df.columns):
        df["Irr Variation (kWh)"] = _to_float(df["Irradiance-based generation"]) - _to_float(df["Forecast Gen (kWh)"])

    # Ensure all required columns exist (some may be missing and should become NULL).
    out = pd.DataFrame()
    out["Site"] = df["Site"].astype(str).str.strip()
    out["Type"] = df.get("Type")
    out["kWp"] = _to_float(df.get("kWp", pd.Series([None] * len(df))))
    date_raw = df.get("Date")
    out["Date"] = date_raw

    out["Actual Gen (kWh)"] = _to_float(df.get("Actual Gen (kWh)", pd.Series([None] * len(df))))
    out["Forecast Gen (kWh)"] = _to_float(df.get("Forecast Gen (kWh)", pd.Series([None] * len(df))))
    out["Gen Dev. (%)"] = _to_float(df.get("Gen Dev. (%)", pd.Series([None] * len(df))))
    out["kWh/kWp"] = _to_float(df.get("kWh/kWp", pd.Series([None] * len(df))))

    out["Calculated Exp (kWh)"] = _to_float(df.get("Calculated Exp (kWh)", pd.Series([None] * len(df))))
    out["Net Usage (kWh)"] = _to_float(df.get("Net Usage (kWh)", pd.Series([None] * len(df))))

    out["Actual Irr (kWh/m2)"] = _to_float(df.get("Actual Irr (kWh/m2)", pd.Series([None] * len(df))))
    out["Forecast Irr"] = _to_float(df.get("Forecast Irr", pd.Series([None] * len(df))))

    out["Irradiance-based generation"] = _to_float(df.get("Irradiance-based generation", pd.Series([None] * len(df))))
    out["Irr Variation (kWh)"] = _to_float(df.get("Irr Variation (kWh)", pd.Series([None] * len(df))))

    out["Actual PR (%)"] = _pct_to_fraction(df.get("Actual PR (%)", pd.Series([None] * len(df))))
    out["Forecast PR (%)"] = _pct_to_fraction(df.get("Forecast PR (%)", pd.Series([None] * len(df))))
    out["Availability (%)"] = _pct_to_fraction(df.get("Availability (%)", pd.Series([None] * len(df))))

    out = out[SOLAR_DATA_COLUMNS_ORDERED]

    # Normalize Date into "Mon-YY" labels used by `solar_data`.
    # Some sheets store Date as a timestamp (e.g. 2025-12-01); others already use "Oct-25".
    if pd.api.types.is_datetime64_any_dtype(out["Date"]):
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce").dt.strftime("%b-%y")
    else:
        # Try to parse ISO-like dates; only convert if it looks like most rows are dates.
        parsed = pd.to_datetime(out["Date"], errors="coerce")
        if parsed.notna().mean() > 0.8:
            out["Date"] = parsed.dt.strftime("%b-%y")
        else:
            out["Date"] = out["Date"].astype(str).str.strip()

    out = out[out["Date"].notna() & (out["Date"].astype(str).str.len() > 0) & (out["Date"].astype(str) != "NaT")]

    return out


def import_to_duckdb(*, db_path: Path, df: pd.DataFrame, dry_run: bool) -> None:
    conn = duckdb.connect(str(db_path), config={"access_mode": "automatic"})
    try:
        dates = sorted(set(df["Date"].astype(str)))
        before_total = conn.execute("SELECT COUNT(*) FROM solar_data").fetchone()[0]
        before_dates = conn.execute('SELECT COUNT(*) FROM solar_data WHERE "Date" IN (SELECT * FROM UNNEST(?))', [dates]).fetchone()[0]

        print(f"DB: {db_path}")
        print(f"Incoming rows: {len(df)} across dates={dates}")
        print(f"solar_data rows before: total={before_total}, affected_dates_rows={before_dates}")

        if dry_run:
            print("\n[DRY RUN] Preview (first 5 rows):")
            with pd.option_context("display.max_columns", None):
                print(df.head(5))
            return

        conn.register("__incoming_df", df)
        conn.execute("CREATE TEMP TABLE __incoming AS SELECT * FROM __incoming_df")

        conn.execute(
            'DELETE FROM solar_data WHERE "Date" IN (SELECT DISTINCT "Date" FROM __incoming)'
            ' AND "Site" IN (SELECT "Site" FROM __incoming)',
        )

        cols_sql = ", ".join(f'"{c}"' for c in SOLAR_DATA_COLUMNS_ORDERED)
        conn.execute(f"INSERT INTO solar_data ({cols_sql}) SELECT {cols_sql} FROM __incoming")

        after_total = conn.execute("SELECT COUNT(*) FROM solar_data").fetchone()[0]
        after_dates = conn.execute('SELECT COUNT(*) FROM solar_data WHERE "Date" IN (SELECT DISTINCT "Date" FROM __incoming)').fetchone()[0]
        print(f"\nsolar_data rows after: total={after_total}, affected_dates_rows={after_dates}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Excom workbook sheet(s) into DuckDB solar_data")
    parser.add_argument("--db-path", type=Path, default=Path.home() / ".solar_toolkit" / "plant_registry.duckdb")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to Excom .xlsx file")
    parser.add_argument("--sheet", default="", help="Sheet name override (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without writing to DuckDB")
    args = parser.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"XLSX not found: {args.xlsx}")
    if not args.db_path.exists():
        raise SystemExit(f"DuckDB not found: {args.db_path}")

    sheet = args.sheet.strip() or detect_best_sheet(args.xlsx)
    print(f"Using sheet: {sheet!r}")

    df = load_excom_sheet(args.xlsx, sheet=sheet)
    import_to_duckdb(db_path=args.db_path, df=df, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
