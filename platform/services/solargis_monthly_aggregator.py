"""SolarGIS 15-minute data → monthly capacity-weighted irradiance aggregation.

Reads the 15-minute SolarGIS CSV files from
``tools/irradiation-data/{YYYY MM}/`` folders, computes **capacity-weighted
monthly GTI (POA)** for each site, and returns a DataFrame that can be
merged into the Notion irradiance database alongside the existing
``solar_data`` actuals / forecasts.

The capacity-weighted formula is::

    POA_site = Σ(GTI_array_i × Cap_array_i) / Σ(Cap_array_i)

Usage (standalone)::

    python -m services.solargis_monthly_aggregator          # print summary
    python -m services.solargis_monthly_aggregator --csv     # write CSV

Usage (as library)::

    from services.solargis_monthly_aggregator import aggregate_solargis_monthly
    df = aggregate_solargis_monthly()
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from services.config import get_settings

# ── Constants ────────────────────────────────────────────────────────────

# Default data root — relative to repo root
_DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[2] / "tools" / "irradiation-data"

# Month abbreviation map: "2025 04" → "Apr-25" (the format used in solar_data)
_MONTH_FMT = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}

# Site name normalisation: CSV filename → solar_data Site name
# Only list entries that need explicit remapping
_SITE_NAME_OVERRIDES: dict[str, str] = {
    "Smithy's Mushrooms": "Smithys Mushrooms",
    "Smithy's Mushrooms Phase 2": "Smithys Mushrooms Phase 2",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _csv_filename_to_site(filename: str) -> str:
    """Convert a SolarGIS CSV filename back to a human site name.

    ``Cromwell_Tools.csv`` → ``Cromwell Tools``
    """
    name = Path(filename).stem.replace("_", " ")
    return _SITE_NAME_OVERRIDES.get(name, name)


def _folder_to_month_label(folder_name: str) -> str | None:
    """Convert folder name ``2025 08`` → ``Aug-25``."""
    m = re.match(r"(\d{4})\s+(\d{2})", folder_name)
    if not m:
        return None
    year, month = m.group(1), m.group(2)
    abbr = _MONTH_FMT.get(month)
    if not abbr:
        return None
    return f"{abbr}-{year[2:]}"


def _compute_site_monthly_poa(csv_path: Path) -> dict[str, Any]:
    """Read one SolarGIS CSV and compute capacity-weighted monthly GTI.

    The CSV has one row **per inverter per timestamp**.  Multiple inverters
    at the same orientation (azimuth, slope) receive identical irradiance,
    so we must **deduplicate by timestamp** within each orientation group
    before summing to avoid inflating the total.

    Capacity-weighting then averages across *different* orientations using
    each orientation's total installed capacity as the weight.

    Returns dict with keys:
        site, solargis_gti, solargis_ghi, solargis_kwp, n_arrays, arrays
    """
    df = pd.read_csv(csv_path)

    # Discover unique orientations (arrays)
    orientations = df[["azimuth", "slope"]].drop_duplicates()

    if orientations.empty:
        return None

    # For each orientation, compute:
    #   - total installed capacity (sum of all inverters at that orientation)
    #   - monthly GTI (deduplicated — one value per timestamp)
    orientation_data: list[dict[str, Any]] = []

    for _, ori in orientations.iterrows():
        az, sl = ori["azimuth"], ori["slope"]
        mask = (df["azimuth"] == az) & (df["slope"] == sl)
        subset = df.loc[mask]

        # Total capacity for this orientation = sum of unique inverter capacities
        # Since multiple inverters can share the same capacity value, we sum
        # array_capacity once per *row at a given timestamp* (each row = 1 inverter)
        first_ts = subset["time"].iloc[0]
        invs_at_ts = subset[subset["time"] == first_ts]
        orientation_cap = invs_at_ts["array_capacity"].sum()

        # Deduplicate: take ONE GTI value per timestamp (they're identical
        # for the same orientation — it's irradiance per m²)
        deduped = subset.drop_duplicates(subset=["time"])
        arr_gti = deduped["gti"].sum()   # kWh/m² for the month

        orientation_data.append({
            "azimuth": az,
            "slope": sl,
            "capacity_kwp": round(orientation_cap, 2),
            "gti_kwh_m2": round(arr_gti, 2),
        })

    total_cap = sum(o["capacity_kwp"] for o in orientation_data)
    if total_cap == 0:
        return None

    # Capacity-weighted average GTI across orientations
    weighted_gti = sum(
        o["gti_kwh_m2"] * (o["capacity_kwp"] / total_cap)
        for o in orientation_data
    )

    # GHI — same for all orientations at the same location; deduplicate timestamps
    ghi_deduped = df.drop_duplicates(subset=["time"])
    ghi_sum = ghi_deduped["ghi"].sum()

    site_name = _csv_filename_to_site(csv_path.name)

    return {
        "site": site_name,
        "solargis_gti": round(weighted_gti, 2),
        "solargis_ghi": round(ghi_sum, 2),
        "solargis_kwp": round(total_cap, 2),
        "n_arrays": len(orientation_data),
        "arrays": orientation_data,
    }


# ── Main aggregation ─────────────────────────────────────────────────────

def aggregate_solargis_monthly(
    data_root: Path | None = None,
) -> pd.DataFrame:
    """Scan all month folders and return a DataFrame of monthly SolarGIS irradiance.

    Columns: Site, Month, SolarGIS GTI (kWh/m²), SolarGIS GHI (kWh/m²),
             SolarGIS kWp, n_arrays
    """
    root = data_root or _DEFAULT_DATA_ROOT
    if not root.exists():
        raise FileNotFoundError(f"SolarGIS data root not found: {root}")

    records: list[dict[str, Any]] = []

    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        month_label = _folder_to_month_label(folder.name)
        if not month_label:
            continue

        for csv_file in sorted(folder.glob("*.csv")):
            if csv_file.name.lower() in ("combined.csv", "site_summary.csv"):
                continue
            try:
                result = _compute_site_monthly_poa(csv_file)
            except Exception as exc:
                print(f"  WARN: {csv_file}: {exc}")
                continue

            if result is None:
                continue

            records.append({
                "Site": result["site"],
                "Month": month_label,
                "SolarGIS GTI (kWh/m²)": result["solargis_gti"],
                "SolarGIS GHI (kWh/m²)": result["solargis_ghi"],
                "SolarGIS kWp": result["solargis_kwp"],
                "n_arrays": result["n_arrays"],
            })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(["Site", "Month"]).reset_index(drop=True)
    return df


# ── kWp cross-reference ──────────────────────────────────────────────────

def cross_reference_kwp(
    solargis_df: pd.DataFrame,
    site_summary_path: Path | None = None,
) -> pd.DataFrame:
    """Compare kWp across three sources: SolarGIS CSV arrays, site_summary.csv,
    and the DuckDB solar_data table.

    Returns a DataFrame with one row per site showing each source's kWp and
    any discrepancies.
    """
    settings = get_settings()

    # 1. SolarGIS kWp from aggregated data (take max per site since it's constant)
    sg = solargis_df.groupby("Site")["SolarGIS kWp"].max().reset_index()
    sg.columns = ["Site", "SolarGIS_kWp"]

    # 2. site_summary.csv
    ss_path = site_summary_path or (_DEFAULT_DATA_ROOT / "site_summary.csv")
    ss_records: list[dict] = []
    if ss_path.exists():
        ss = pd.read_csv(ss_path)
        for _, r in ss.iterrows():
            name = r["Site Name"]
            name = _SITE_NAME_OVERRIDES.get(name, name)
            ss_records.append({
                "Site": name,
                "SiteSummary_Irr_kWp": r.get("Total Array Capacity (kWp) - Irradiance File"),
                "SiteSummary_ADE_kWp": r.get("Nameplate DC Capacity (kWp) - ADE"),
            })
    ss_df = pd.DataFrame(ss_records).drop_duplicates(subset="Site")

    # 3. DuckDB solar_data kWp
    conn = duckdb.connect(str(settings.db_path), read_only=True)
    db = conn.execute('SELECT DISTINCT Site, kWp as DB_kWp FROM solar_data').fetchdf()
    conn.close()
    # Some sites have varying kWp — take the mode / most common
    db = db.groupby("Site")["DB_kWp"].agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0]).reset_index()

    # Merge
    merged = sg.merge(ss_df, on="Site", how="outer").merge(db, on="Site", how="outer")
    merged = merged.sort_values("Site").reset_index(drop=True)

    # Flag discrepancies
    def _check(row):
        vals = []
        for col in ["SolarGIS_kWp", "SiteSummary_ADE_kWp", "DB_kWp"]:
            v = row.get(col)
            if pd.notna(v) and v > 0:
                vals.append(v)
        if len(vals) <= 1:
            return "OK"
        spread = (max(vals) - min(vals)) / max(vals) * 100
        if spread > 2.0:  # > 2% difference
            return f"MISMATCH ({spread:.1f}%)"
        elif spread > 0:
            return f"minor ({spread:.1f}%)"
        return "OK"

    merged["kWp_Status"] = merged.apply(_check, axis=1)
    return merged


# ── Comparison with solar_data actuals ────────────────────────────────────

def compare_with_solar_data(solargis_df: pd.DataFrame) -> pd.DataFrame:
    """Merge SolarGIS monthly GTI with the existing solar_data Actual Irr column.

    Returns a comparison DataFrame with variance.
    """
    settings = get_settings()
    conn = duckdb.connect(str(settings.db_path), read_only=True)
    db = conn.execute("""
        SELECT Site, Date as Month,
               "Actual Irr (kWh/m2)" as Actual_Irr,
               "Forecast Irr" as Forecast_Irr,
               kWp as DB_kWp
        FROM solar_data
    """).fetchdf()
    conn.close()

    merged = db.merge(
        solargis_df[["Site", "Month", "SolarGIS GTI (kWh/m²)", "SolarGIS kWp"]],
        on=["Site", "Month"],
        how="outer",
    )

    # Variance columns
    merged["SolarGIS vs Actual (%)"] = None
    merged["SolarGIS vs Forecast (%)"] = None

    mask_act = merged["Actual_Irr"].notna() & merged["SolarGIS GTI (kWh/m²)"].notna() & (merged["Actual_Irr"] > 0)
    merged.loc[mask_act, "SolarGIS vs Actual (%)"] = (
        (merged.loc[mask_act, "SolarGIS GTI (kWh/m²)"] - merged.loc[mask_act, "Actual_Irr"])
        / merged.loc[mask_act, "Actual_Irr"] * 100
    ).round(1)

    mask_fc = merged["Forecast_Irr"].notna() & merged["SolarGIS GTI (kWh/m²)"].notna() & (merged["Forecast_Irr"] > 0)
    merged.loc[mask_fc, "SolarGIS vs Forecast (%)"] = (
        (merged.loc[mask_fc, "SolarGIS GTI (kWh/m²)"] - merged.loc[mask_fc, "Forecast_Irr"])
        / merged.loc[mask_fc, "Forecast_Irr"] * 100
    ).round(1)

    return merged.sort_values(["Site", "Month"]).reset_index(drop=True)


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate SolarGIS 15-min data to monthly irradiance")
    parser.add_argument("--csv", action="store_true", help="Write output CSV")
    parser.add_argument("--kwp", action="store_true", help="Run kWp cross-reference check")
    parser.add_argument("--compare", action="store_true", help="Compare SolarGIS vs solar_data actuals")
    parser.add_argument("--data-root", type=Path, help="Override SolarGIS data folder")
    args = parser.parse_args()

    print("Aggregating SolarGIS 15-min data to monthly totals...")
    df = aggregate_solargis_monthly(data_root=args.data_root)
    print(f"  {len(df)} site-months from {df['Site'].nunique()} sites")
    print(f"  Months: {sorted(df['Month'].unique())}")

    if args.csv:
        out = Path("solargis_monthly.csv")
        df.to_csv(out, index=False)
        print(f"\n  Wrote {out}")

    if args.kwp:
        print("\n" + "=" * 80)
        print("kWp Cross-Reference: SolarGIS CSVs vs site_summary.csv vs DuckDB solar_data")
        print("=" * 80)
        kwp_df = cross_reference_kwp(df)
        for _, r in kwp_df.iterrows():
            sg = f"{r['SolarGIS_kWp']:>10.2f}" if pd.notna(r.get("SolarGIS_kWp")) else "         -"
            ss = f"{r['SiteSummary_ADE_kWp']:>10.2f}" if pd.notna(r.get("SiteSummary_ADE_kWp")) else "         -"
            db = f"{r['DB_kWp']:>10.2f}" if pd.notna(r.get("DB_kWp")) else "         -"
            status = r["kWp_Status"]
            flag = " ⚠️" if "MISMATCH" in status else ""
            print(f"  {r['Site']:45s}  SG={sg}  ADE={ss}  DB={db}  {status}{flag}")

    if args.compare:
        print("\n" + "=" * 80)
        print("SolarGIS GTI vs solar_data Actual/Forecast Irradiance")
        print("=" * 80)
        comp = compare_with_solar_data(df)
        # Only show rows that have both SolarGIS and at least one actual/forecast
        mask = comp["SolarGIS GTI (kWh/m²)"].notna() & (comp["Actual_Irr"].notna() | comp["Forecast_Irr"].notna())
        matched = comp[mask]
        for _, r in matched.iterrows():
            sg = f"{r['SolarGIS GTI (kWh/m²)']:>7.1f}"
            act = f"{r['Actual_Irr']:>7.1f}" if pd.notna(r["Actual_Irr"]) else "    N/A"
            fc = f"{r['Forecast_Irr']:>7.1f}" if pd.notna(r["Forecast_Irr"]) else "    N/A"
            va = f"{r['SolarGIS vs Actual (%)']:>+6.1f}%" if pd.notna(r["SolarGIS vs Actual (%)"]) else "    N/A"
            vf = f"{r['SolarGIS vs Forecast (%)']:>+6.1f}%" if pd.notna(r["SolarGIS vs Forecast (%)"]) else "    N/A"
            print(f"  {r['Site']:40s} {r['Month']:8s}  SG={sg}  Act={act} ({va})  Fc={fc} ({vf})")

    if not args.kwp and not args.compare and not args.csv:
        # Default: print summary table
        print("\n" + df.to_string(index=False))


if __name__ == "__main__":
    main()
