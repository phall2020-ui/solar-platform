"""
Inverter vs Generation Meter Comparison Script
================================================

Compares the sum of all inverter energy readings against the PV generation
meter reading from the Juggle/EMIG API for a given plant.

Produces daily and monthly comparison tables showing:
  - Inverter total (kWh)
  - Meter total (kWh)
  - Difference (kWh and %)

Usage:
    python inverter_meter_check.py                       # Interactive mode
    python inverter_meter_check.py --last-month          # Previous calendar month
    python inverter_meter_check.py --start 20260101 --end 20260131
    python inverter_meter_check.py --yesterday           # Quick daily check
"""

import argparse
import io
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import requests

# Reuse existing infrastructure
from fetch_inverter_data import (
    BASE_URL,
    Config,
    NEWFOLD_INVERTER_IDS,
    fetch_all_readings,
    get_plant_devices,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Newfold Farm defaults
DEFAULT_API_KEY = os.environ.get(
    "JUGGLE_API_KEY",
    "380fe299-a626-48f1-8456-e701c7383a23",
)
DEFAULT_PLANT_UID = "ERS:00001"
DEFAULT_PV_METER_ID = "PV:000771"

# Colour codes for terminal output
class C:
    """ANSI colour helpers (degrade gracefully on Windows without VT)."""
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def fetch_device_readings(
    api_key: str,
    emig_id: str,
    start_date: str,
    end_date: str,
    min_interval_s: int = 1800,
) -> List[Dict]:
    """Fetch readings for a single device across the date range."""
    cfg = Config(
        api_key=api_key,
        plant_uid=DEFAULT_PLANT_UID,
        start_date=start_date,
        end_date=end_date,
        min_interval_s=min_interval_s,
    )
    readings = fetch_all_readings(cfg, emig_id)
    for r in readings:
        r["emigId"] = emig_id
    return readings


def _extract_value(val):
    """Unwrap nested {value, unit} dicts returned by the API."""
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def discover_all_plants(api_key: str) -> List[Dict]:
    """
    Discover all plants available to the API key.
    Tries API endpoints first, then falls back to a brute-force scan
    of common ID prefixes if discovery is blocked.
    """
    headers = {"Authorization": f"token {api_key}"}
    urls = [
        f"{BASE_URL}/plants",
        f"{BASE_URL}/plants/list",
        f"{BASE_URL}/plant/list",
    ]
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "plants" in data:
                    data = data["plants"]
                if isinstance(data, list):
                    normalized = []
                    for p in data:
                        uid = p.get("uid") or p.get("plantUid") or p.get("id") or p.get("emigId")
                        name = p.get("name") or p.get("plantName") or p.get("title") or uid
                        if uid:
                            normalized.append({"uid": uid, "name": name})
                    return normalized
        except Exception:
            continue
    
    # Fallback brute-force scan for ERS and AMP prefixes (common in this account)
    # Scan up to 100 for each as a reasonable balance between discovery and speed.
    found = []
    for prefix in ["ERS", "AMP"]:
        for i in range(1, 101):
            uid = f"{prefix}:{i:05d}"
            try:
                resp = requests.get(f"{BASE_URL}/plant/{uid}", headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("name") or uid
                    found.append({"uid": uid, "name": name})
            except Exception:
                continue
    return found



def get_site_devices(api_key: str, plant_uid: str) -> Tuple[List[str], List[str]]:
    """
    Fetch all devices for a plant and identify inverters vs PV meters.
    """
    headers = {"Authorization": f"token {api_key}"}
    try:
        resp = requests.get(f"{BASE_URL}/plant/{plant_uid}", headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        devices = data.get("meters", [])
        
        inverter_ids = [d["emigId"] for d in devices if d.get("type") == "INVERTER"]
        pv_meter_ids = [d["emigId"] for d in devices if d.get("type") == "PV"]
        
        return inverter_ids, pv_meter_ids
    except Exception:
        return [], []



# ---------------------------------------------------------------------------
# Energy calculation
# ---------------------------------------------------------------------------

def readings_to_dataframe(readings: List[Dict]) -> pd.DataFrame:
    """Convert raw API readings into a tidy DataFrame."""
    if not readings:
        return pd.DataFrame()
    df = pd.DataFrame(readings)
    # Flatten nested value dicts
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(_extract_value)
    # Parse timestamp
    if "ts" in df.columns:
        df["timestamp"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp")
    return df


def compute_daily_energy(df: pd.DataFrame, energy_col: str = "exportEnergy") -> pd.DataFrame:
    """
    Compute daily energy generation (kWh) from cumulative Wh readings.
    
    For each device (emigId), the daily yield = max(exportEnergy) - min(exportEnergy)
    within each calendar day, converted from Wh to kWh.
    """
    if df.empty or energy_col not in df.columns:
        return pd.DataFrame(columns=["date", "energy_kwh"])

    df = df.copy()
    df[energy_col] = pd.to_numeric(df[energy_col], errors="coerce")
    df = df.dropna(subset=[energy_col])
    df["date"] = df["timestamp"].dt.date

    # Per-device, per-day: delta of cumulative counter
    daily = (
        df.groupby(["emigId", "date"])[energy_col]
        .agg(["min", "max"])
        .reset_index()
    )
    daily["energy_wh"] = daily["max"] - daily["min"]
    # Negative deltas (counter resets) – treat as zero
    daily.loc[daily["energy_wh"] < 0, "energy_wh"] = 0.0

    # Sum across all devices per day
    daily_total = (
        daily.groupby("date")["energy_wh"]
        .sum()
        .reset_index()
    )
    daily_total["energy_kwh"] = daily_total["energy_wh"] / 1000.0
    return daily_total[["date", "energy_kwh"]]


def compute_daily_energy_from_power(
    df: pd.DataFrame,
    power_col: str = "importActivePower",
    only_positive: bool = False,
) -> pd.DataFrame:
    """
    Fallback: estimate daily energy from instantaneous power readings (W).
    Assumes half-hourly readings -> multiply by 0.5 h and convert W->kWh.

    If only_positive is True, only positive power values are summed (used for
    the PV meter where positive importActivePower = generation).
    """
    if df.empty or power_col not in df.columns:
        return pd.DataFrame(columns=["date", "energy_kwh"])

    df = df.copy()
    df[power_col] = pd.to_numeric(df[power_col], errors="coerce")
    df = df.dropna(subset=[power_col])
    if only_positive:
        df = df[df[power_col] > 0]
    df["date"] = df["timestamp"].dt.date

    # Each reading represents ~0.5 h of energy:  power(W) x 0.5h / 1000 = kWh
    daily = (
        df.groupby(["emigId", "date"])[power_col]
        .sum()
        .reset_index()
    )
    daily["energy_kwh"] = daily[power_col] * 0.5 / 1000.0

    daily_total = (
        daily.groupby("date")["energy_kwh"]
        .sum()
        .reset_index()
    )
    return daily_total[["date", "energy_kwh"]]


def pick_inverter_energy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily energy for inverters.

    Inverters record cumulative generation — field varies by site:
      - Newfold Farm uses exportEnergy
      - Cromwell Tools uses importEnergy
    """
    # Try exportEnergy first (Newfold-style)
    if "exportEnergy" in df.columns:
        result = compute_daily_energy(df, "exportEnergy")
        if not result.empty and result["energy_kwh"].sum() > 0:
            return result
    # Try importEnergy (Cromwell-style)
    if "importEnergy" in df.columns:
        result = compute_daily_energy(df, "importEnergy")
        if not result.empty and result["energy_kwh"].sum() > 0:
            return result
    # Fallback to importActivePower
    if "importActivePower" in df.columns:
        result = compute_daily_energy_from_power(df, "importActivePower")

        if not result.empty and result["energy_kwh"].sum() > 0:
            return result
    return pd.DataFrame(columns=["date", "energy_kwh"])


def pick_meter_energy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate daily energy for the PV generation meter.

    The PV meter (type=PV) records total solar generation in importEnergy
    (energy flowing INTO the meter from the array). exportEnergy on this
    meter is grid export only, which is a subset of total generation.

    Fallback: sum positive importActivePower readings (positive = generation
    from the array).
    """
    # Primary: importEnergy cumulative counter
    if "importEnergy" in df.columns:
        result = compute_daily_energy(df, "importEnergy")
        if not result.empty and result["energy_kwh"].sum() > 0:
            return result
    # Fallback: integrate positive importActivePower (generation direction)
    if "importActivePower" in df.columns:
        result = compute_daily_energy_from_power(
            df, "importActivePower", only_positive=True
        )
        if not result.empty and result["energy_kwh"].sum() > 0:
            return result
    # Last resort: exportEnergy
    if "exportEnergy" in df.columns:
        return compute_daily_energy(df, "exportEnergy")
    return pd.DataFrame(columns=["date", "energy_kwh"])


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

def build_comparison(inv_daily: pd.DataFrame, meter_daily: pd.DataFrame) -> pd.DataFrame:
    """Merge inverter and meter daily totals and compute differences."""
    merged = pd.merge(
        inv_daily.rename(columns={"energy_kwh": "inverter_kwh"}),
        meter_daily.rename(columns={"energy_kwh": "meter_kwh"}),
        on="date",
        how="outer",
    ).fillna(0.0)
    merged = merged.sort_values("date").reset_index(drop=True)
    merged["diff_kwh"] = merged["inverter_kwh"] - merged["meter_kwh"]
    # Percentage difference relative to meter (avoid div-by-zero)
    merged["diff_pct"] = merged.apply(
        lambda row: (
            (row["diff_kwh"] / row["meter_kwh"] * 100)
            if row["meter_kwh"] != 0
            else 0.0
        ),
        axis=1,
    )
    return merged


def monthly_summary(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily comparison into monthly totals."""
    if daily.empty:
        return pd.DataFrame()
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    monthly = (
        df.groupby("month")
        .agg(
            inverter_kwh=("inverter_kwh", "sum"),
            meter_kwh=("meter_kwh", "sum"),
            days=("date", "count"),
        )
        .reset_index()
    )
    monthly["diff_kwh"] = monthly["inverter_kwh"] - monthly["meter_kwh"]
    monthly["diff_pct"] = monthly.apply(
        lambda row: (
            (row["diff_kwh"] / row["meter_kwh"] * 100)
            if row["meter_kwh"] != 0
            else 0.0
        ),
        axis=1,
    )
    monthly["month"] = monthly["month"].astype(str)
    return monthly


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _colour_pct(pct: float) -> str:
    """Colour-code a percentage for terminal display."""
    s = f"{pct:+.2f}%"
    if abs(pct) < 2:
        return f"{C.GREEN}{s}{C.END}"
    elif abs(pct) < 5:
        return f"{C.YELLOW}{s}{C.END}"
    else:
        return f"{C.RED}{s}{C.END}"


def print_daily_report(daily: pd.DataFrame) -> None:
    """Pretty-print the daily comparison table."""
    if daily.empty:
        print("No daily data to display.")
        return

    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}  DAILY COMPARISON: Inverter Total vs PV Generation Meter{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")
    print(
        f"  {'Date':<14}  {'Inverter (kWh)':>15}  {'Meter (kWh)':>13}  "
        f"{'Diff (kWh)':>12}  {'Diff (%)':>10}"
    )
    print(f"  {'-'*14}  {'-'*15}  {'-'*13}  {'-'*12}  {'-'*10}")

    for _, row in daily.iterrows():
        pct_str = _colour_pct(row["diff_pct"])
        print(
            f"  {str(row['date']):<14}  {row['inverter_kwh']:>15,.1f}  "
            f"{row['meter_kwh']:>13,.1f}  {row['diff_kwh']:>+12,.1f}  {pct_str}"
        )

    # Totals
    total_inv = daily["inverter_kwh"].sum()
    total_meter = daily["meter_kwh"].sum()
    total_diff = total_inv - total_meter
    total_pct = (total_diff / total_meter * 100) if total_meter != 0 else 0
    print(f"  {'-'*14}  {'-'*15}  {'-'*13}  {'-'*12}  {'-'*10}")
    pct_str = _colour_pct(total_pct)
    print(
        f"  {'TOTAL':<14}  {total_inv:>15,.1f}  {total_meter:>13,.1f}  "
        f"{total_diff:>+12,.1f}  {pct_str}"
    )
    print()


def print_monthly_report(monthly: pd.DataFrame) -> None:
    """Pretty-print the monthly comparison table."""
    if monthly.empty:
        print("No monthly data to display.")
        return

    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}  MONTHLY COMPARISON: Inverter Total vs PV Generation Meter{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")
    print(
        f"  {'Month':<10}  {'Days':>5}  {'Inverter (kWh)':>15}  {'Meter (kWh)':>13}  "
        f"{'Diff (kWh)':>12}  {'Diff (%)':>10}"
    )
    print(f"  {'-'*10}  {'-'*5}  {'-'*15}  {'-'*13}  {'-'*12}  {'-'*10}")

    for _, row in monthly.iterrows():
        pct_str = _colour_pct(row["diff_pct"])
        print(
            f"  {row['month']:<10}  {row['days']:>5}  {row['inverter_kwh']:>15,.1f}  "
            f"{row['meter_kwh']:>13,.1f}  {row['diff_kwh']:>+12,.1f}  {pct_str}"
        )

    # Totals
    total_inv = monthly["inverter_kwh"].sum()
    total_meter = monthly["meter_kwh"].sum()
    total_diff = total_inv - total_meter
    total_pct = (total_diff / total_meter * 100) if total_meter != 0 else 0
    total_days = monthly["days"].sum()
    print(f"  {'-'*10}  {'-'*5}  {'-'*15}  {'-'*13}  {'-'*12}  {'-'*10}")
    pct_str = _colour_pct(total_pct)
    print(
        f"  {'TOTAL':<10}  {total_days:>5}  {total_inv:>15,.1f}  {total_meter:>13,.1f}  "
        f"{total_diff:>+12,.1f}  {pct_str}"
    )
    print()


def save_to_excel(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    output_path: str,
) -> None:
    """Save both reports to a formatted Excel workbook."""
    try:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            if not daily.empty:
                daily_out = daily.copy()
                daily_out["date"] = pd.to_datetime(daily_out["date"])
                daily_out.to_excel(writer, sheet_name="Daily", index=False)
                ws = writer.sheets["Daily"]
                # Format number columns
                for col_idx in [2, 3, 4]:  # B, C, D (kwh columns)
                    for row in range(2, len(daily_out) + 2):
                        cell = ws.cell(row=row, column=col_idx)
                        cell.number_format = "#,##0.0"
                for row in range(2, len(daily_out) + 2):
                    cell = ws.cell(row=row, column=5)  # diff_pct
                    cell.number_format = "+0.00%;-0.00%"
                    # Convert to actual fraction for Excel percentage
                    if cell.value is not None:
                        cell.value = cell.value / 100.0

            if not monthly.empty:
                monthly.to_excel(writer, sheet_name="Monthly", index=False)
                ws = writer.sheets["Monthly"]
                for col_idx in [3, 4, 5]:
                    for row in range(2, len(monthly) + 2):
                        cell = ws.cell(row=row, column=col_idx)
                        cell.number_format = "#,##0.0"
                for row in range(2, len(monthly) + 2):
                    cell = ws.cell(row=row, column=6)
                    cell.number_format = "+0.00%;-0.00%"
                    if cell.value is not None:
                        cell.value = cell.value / 100.0

        print(f"  📊 Saved report to: {output_path}")
    except Exception as exc:
        print(f"  ⚠️  Could not save Excel: {exc}")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_check(
    api_key: str,
    plant_uid: str,
    inverter_ids: List[str],
    pv_meter_ids: List[str],
    start_date: str,
    end_date: str,
    output_excel: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the full inverter vs meter comparison.

    pv_meter_ids can contain one or more PV meter EMIG IDs.
    When multiple are given their readings are combined (summed per day).

    Returns (daily_comparison, monthly_comparison) DataFrames.
    """
    meter_label = ", ".join(pv_meter_ids)
    print(f"\n{C.BOLD}Inverter vs Meter Check{C.END}")
    print(f"  Plant:     {plant_uid}")
    print(f"  PV Meter:  {meter_label}")
    print(f"  Period:    {start_date} -> {end_date}")
    print(f"  Inverters: {len(inverter_ids)}")
    print()

    # --- Fetch PV generation meter(s) ---
    meter_readings: List[Dict] = []
    for pv_id in pv_meter_ids:
        print(f"  Fetching PV meter ({pv_id})...", end=" ", flush=True)
        try:
            readings = fetch_device_readings(api_key, pv_id, start_date, end_date)
            meter_readings.extend(readings)
            print(f"ok {len(readings)} readings")
        except Exception as exc:
            print(f"FAILED {exc}")
        time.sleep(0.5)


    # --- Fetch all inverters ---
    all_inv_readings = []
    for i, inv_id in enumerate(inverter_ids, 1):
        print(f"  Fetching inverter {i}/{len(inverter_ids)} ({inv_id})...", end=" ", flush=True)
        try:
            readings = fetch_device_readings(api_key, inv_id, start_date, end_date)
            all_inv_readings.extend(readings)
            print(f"✓ {len(readings)} readings")
        except Exception as exc:
            print(f"✗ {exc}")
        time.sleep(0.5)  # Be gentle with the API

    # --- Process ---
    print(f"\n  Processing data...")

    inv_df = readings_to_dataframe(all_inv_readings)
    meter_df = readings_to_dataframe(meter_readings)

    if inv_df.empty:
        print("  ⚠️  No inverter data retrieved. Check date range and API key.")
        return pd.DataFrame(), pd.DataFrame()
    if meter_df.empty:
        print("  ⚠️  No meter data retrieved. Check PV meter ID and date range.")
        return pd.DataFrame(), pd.DataFrame()

    # Compute daily energy using appropriate fields per device type
    #   Inverters: exportEnergy = cumulative total generation (Wh)
    #   PV meter:  importEnergy = cumulative energy from array (Wh)
    inv_daily = pick_inverter_energy(inv_df)
    meter_daily = pick_meter_energy(meter_df)

    if inv_daily.empty:
        print("  Warning: Could not compute inverter energy. No suitable column found.")
        return pd.DataFrame(), pd.DataFrame()
    if meter_daily.empty:
        print("  Warning: Could not compute meter energy. No suitable column found.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"  Inverter: {len(inv_daily)} days, {inv_daily['energy_kwh'].sum():,.1f} kWh total (from exportEnergy)")
    print(f"  Meter:    {len(meter_daily)} days, {meter_daily['energy_kwh'].sum():,.1f} kWh total (from importEnergy)")

    # Build comparison
    daily = build_comparison(inv_daily, meter_daily)
    monthly = monthly_summary(daily)

    # Print reports
    print_daily_report(daily)
    print_monthly_report(monthly)

    # Save Excel
    if output_excel:
        save_to_excel(daily, monthly, output_excel)

    return daily, monthly


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare inverter totals vs PV generation meter in Juggle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Juggle API key (default: env or hardcoded)",
    )
    parser.add_argument(
        "--plant-uid",
        default=DEFAULT_PLANT_UID,
        help="Plant UID (default: ERS:00001 = Newfold Farm)",
    )
    parser.add_argument(
        "--pv-meter",
        default=DEFAULT_PV_METER_ID,
        help="PV generation meter EMIG ID(s), comma-separated (default: PV:000771)",
    )
    parser.add_argument(
        "--start",
        dest="start_date",
        help="Start date YYYYMMDD",
    )
    parser.add_argument(
        "--end",
        dest="end_date",
        help="End date YYYYMMDD",
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Quick check for yesterday only",
    )
    parser.add_argument(
        "--last-month",
        action="store_true",
        help="Check the previous calendar month",
    )
    parser.add_argument(
        "--last-7-days",
        action="store_true",
        help="Check the last 7 days",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output Excel file path (auto-generated if not specified)",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Skip Excel output, only print to console",
    )
    parser.add_argument(
        "--inverter-ids",
        help="Comma-separated inverter EMIG IDs (default: Newfold Farm list)",
    )
    parser.add_argument(
        "--all-sites",
        action="store_true",
        help="Automatically process all plants found via API discovery",
    )
    return parser.parse_args()



def main() -> None:
    args = parse_args()

    # Determine date range
    today = datetime.today()
    if args.yesterday:
        yesterday = today - timedelta(days=1)
        start_date = yesterday.strftime("%Y%m%d")
        end_date = start_date
    elif args.last_month:
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        start_date = last_month_start.strftime("%Y%m%d")
        end_date = last_month_end.strftime("%Y%m%d")
    elif args.last_7_days:
        start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
        end_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        # Interactive: prompt for dates
        print("\n=== Inverter vs Meter Check ===\n")
        print("Quick options:")
        print("  1) Yesterday")
        print("  2) Last 7 days")
        print("  3) Last month")
        print("  4) Custom date range")
        choice = input("\nSelect [1-4]: ").strip()
        if choice == "1":
            yesterday = today - timedelta(days=1)
            start_date = yesterday.strftime("%Y%m%d")
            end_date = start_date
        elif choice == "2":
            start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
            end_date = (today - timedelta(days=1)).strftime("%Y%m%d")
        elif choice == "3":
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            start_date = last_month_start.strftime("%Y%m%d")
            end_date = last_month_end.strftime("%Y%m%d")
        else:
            start_date = input("Start date (YYYYMMDD): ").strip()
            end_date = input("End date (YYYYMMDD): ").strip()

    # Validate dates
    try:
        datetime.strptime(start_date, "%Y%m%d")
        datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        print("Error: Invalid date format. Use YYYYMMDD.")
        sys.exit(1)

    # Plants to process
    plants_to_process = []
    if args.all_sites:
        print(f"Discovering plants...")
        all_plants = discover_all_plants(args.api_key)
        for p in all_plants:
            inv_ids, pv_ids = get_site_devices(args.api_key, p["uid"])
            if inv_ids and pv_ids:
                plants_to_process.append({
                    "uid": p["uid"],
                    "name": p["name"],
                    "inv_ids": inv_ids,
                    "pv_ids": pv_ids
                })
        print(f"Found {len(plants_to_process)} sites with both inverters and PV meters.")
    else:
        # Single site (provided via args or defaulted)
        inv_ids = [x.strip() for x in args.inverter_ids.split(",")] if args.inverter_ids else NEWFOLD_INVERTER_IDS
        pv_ids = [x.strip() for x in args.pv_meter.split(",") if x.strip()]
        plants_to_process.append({
            "uid": args.plant_uid,
            "name": "User-specified site",
            "inv_ids": inv_ids,
            "pv_ids": pv_ids
        })

    summary_rows = []
    daily_frames = []

    for site in plants_to_process:
        print(f"\n{'#'*80}")
        print(f"Processing site: {site['name']} ({site['uid']})")
        print(f"{'#'*80}")
        
        site_excel = None if len(plants_to_process) > 1 else (args.output or f"inverter_vs_meter_{site['uid']}_{start_date}_{end_date}.xlsx")
        if args.no_excel:
            site_excel = None

        try:
            daily, monthly = run_check(
                api_key=args.api_key,
                plant_uid=site["uid"],
                inverter_ids=site["inv_ids"],
                pv_meter_ids=site["pv_ids"],
                start_date=start_date,
                end_date=end_date,
                output_excel=site_excel,
            )

            if not daily.empty:
                total_inv = daily["inverter_kwh"].sum()
                total_meter = daily["meter_kwh"].sum()
                diff_kwh = total_inv - total_meter
                diff_pct = (diff_kwh / total_meter * 100) if total_meter != 0 else 0
                
                summary_rows.append({
                    "Plant UID": site["uid"],
                    "Plant Name": site["name"],
                    "Inverters": len(site["inv_ids"]),
                    "PV Meters": len(site["pv_ids"]),
                    "Inv Total (kWh)": total_inv,
                    "Meter Total (kWh)": total_meter,
                    "Diff (kWh)": diff_kwh,
                    "Diff (%)": diff_pct
                })
                
                daily["Plant UID"] = site["uid"]
                daily_frames.append(daily)

        except Exception as e:
            print(f"FAILED to process {site['uid']}: {e}")

    # Final summary for multiple sites
    if len(summary_rows) > 1:
        summary_df = pd.DataFrame(summary_rows)
        print(f"\n{C.BOLD}{'='*100}{C.END}")
        print(f"{C.BOLD}  OVERALL SUMMARY REPORT{C.END}")
        print(f"{C.BOLD}{'='*100}{C.END}")
        print(summary_df.to_string(index=False))
        
        if not args.no_excel:
            summary_file = args.output or f"comparison_summary_{start_date}_{end_date}.xlsx"
            all_daily = pd.concat(daily_frames, ignore_index=True)
            try:
                with pd.ExcelWriter(summary_file, engine="openpyxl") as writer:
                    summary_df.to_excel(writer, sheet_name="Summary", index=False)
                    all_daily.to_excel(writer, sheet_name="All Daily", index=False)
                print(f"\n📊 Bulk report saved to: {summary_file}")
            except Exception as e:
                print(f"⚠️ Could not save summary Excel: {e}")



if __name__ == "__main__":
    main()
