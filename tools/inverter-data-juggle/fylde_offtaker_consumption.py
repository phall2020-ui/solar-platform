"""
Fylde (BAE Newfold Farm) — Offtaker Consumption since Start of Operations
=========================================================================

Computes how much solar generation was consumed on-site by the offtaker
(BAE Systems) vs exported to the grid since commissioning in June 2025.

Data source:  EMIG API, PV generation meter PV:000771 (type=PV on ERS:00001)
  importEnergy  — cumulative Wh flowing FROM the array INTO the meter (generation)
  exportEnergy  — cumulative Wh flowing FROM the meter OUT to the grid (export)

Formula:
  generation_kwh  = Δ importEnergy per day  (Wh → kWh)
  export_kwh      = Δ exportEnergy per day  (Wh → kWh)
  consumption_kwh = generation_kwh − export_kwh
  consumption_pct = consumption_kwh / generation_kwh × 100

Usage:
    python fylde_offtaker_consumption.py
    python fylde_offtaker_consumption.py --start 20250601 --end 20260330
    python fylde_offtaker_consumption.py --monthly
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("JUGGLE_API_KEY", "380fe299-a626-48f1-8456-e701c7383a23")
BASE_URL = "https://www.emig.co.uk/p/api"
PLANT_UID = "ERS:00001"
PV_METER_ID = "PV:000771"          # type=PV — generation meter (importEnergy = solar generation)
IE_METER_IDS = ["MET:002099", "MET:002107"]  # Import/Export meters — exportEnergy = grid export
COMMISSION_DATE = date(2025, 6, 1)  # Start of operations


# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------

class C:
    BOLD  = "\033[1m"
    GREEN = "\033[92m"
    YELLOW= "\033[93m"
    RED   = "\033[91m"
    CYAN  = "\033[96m"
    END   = "\033[0m"


# ---------------------------------------------------------------------------
# EMIG API helpers
# ---------------------------------------------------------------------------

def _headers() -> Dict[str, str]:
    return {"Authorization": f"token {API_KEY}"}


def fetch_meter_readings(emig_id: str, start: date, end: date) -> List[Dict]:
    """Fetch half-hourly readings for a meter over the given date range."""
    # The EMIG API 413s on large ranges; keep chunks to 30 days.
    MAX_CHUNK = 30
    all_readings: List[Dict] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=MAX_CHUNK - 1), end)
        url = (
            f"{BASE_URL}/meter/{emig_id}/readings"
            f"?startDate={cursor.strftime('%Y%m%d')}"
            f"&endDate={chunk_end.strftime('%Y%m%d')}"
        )
        try:
            resp = requests.get(url, headers=_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            chunk = data.get("readings", []) if isinstance(data, dict) else data
            all_readings.extend(chunk)
            print(
                f"  Fetched {cursor} → {chunk_end}: {len(chunk)} readings",
                flush=True,
            )
        except Exception as exc:
            print(f"  WARNING: chunk {cursor} → {chunk_end} failed: {exc}", flush=True)
        cursor = chunk_end + timedelta(days=1)
        time.sleep(0.3)  # be gentle with the API

    return all_readings


# ---------------------------------------------------------------------------
# Energy calculation helpers
# ---------------------------------------------------------------------------

def _extract_value(field_val) -> float:
    """Unwrap {value, unit} dicts returned by the API."""
    if isinstance(field_val, dict):
        return float(field_val.get("value", 0) or 0)
    try:
        return float(field_val or 0)
    except (TypeError, ValueError):
        return 0.0


def daily_delta_kwh(readings: List[Dict], energy_field: str) -> Dict[date, float]:
    """
    Per-day energy (kWh) from a cumulative Wh counter.
    Daily energy = max(counter) − min(counter) within each calendar day.
    """
    points: List[Tuple[datetime, float]] = []
    for r in readings:
        ts_raw = r.get("ts") or r.get("timestamp")
        val = r.get(energy_field)
        if not ts_raw or val is None:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            wh = _extract_value(val)
            points.append((ts, wh))
        except Exception:
            continue

    if not points:
        return {}

    points.sort(key=lambda x: x[0])

    day_values: Dict[date, List[float]] = defaultdict(list)
    for ts, wh in points:
        day_values[ts.date()].append(wh)

    result: Dict[date, float] = {}
    for d, values in day_values.items():
        delta_wh = max(values) - min(values)
        result[d] = max(0.0, delta_wh) / 1000.0  # Wh → kWh
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _colour_pct(pct: float) -> str:
    s = f"{pct:.1f}%"
    if pct < 15:
        return f"{C.YELLOW}{s}{C.END}"
    elif pct < 30:
        return f"{C.GREEN}{s}{C.END}"
    else:
        return f"{C.CYAN}{s}{C.END}"


def print_monthly_report(daily_gen: Dict[date, float], daily_exp: Dict[date, float]) -> None:
    """Print monthly breakdown of generation, export and offtaker consumption."""
    all_days = sorted(set(list(daily_gen.keys()) + list(daily_exp.keys())))
    if not all_days:
        print("  No data found.")
        return

    # Group by month
    monthly: Dict[str, Dict] = {}
    for d in all_days:
        key = d.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"gen": 0.0, "exp": 0.0, "days": 0}
        gen = daily_gen.get(d, 0.0)
        exp = daily_exp.get(d, 0.0)
        monthly[key]["gen"] += gen
        monthly[key]["exp"] += exp
        if gen > 0 or exp > 0:
            monthly[key]["days"] += 1

    print(f"\n{C.BOLD}{'='*82}{C.END}")
    print(f"{C.BOLD}  BAE Fylde (Newfold Farm) — Monthly Offtaker Consumption vs Grid Export{C.END}")
    print(f"{C.BOLD}{'='*82}{C.END}")
    print(
        f"  {'Month':<10}  {'Gen (kWh)':>11}  {'Export (kWh)':>13}  "
        f"{'Consumed (kWh)':>15}  {'Consumed %':>11}"
    )
    print(f"  {'-'*10}  {'-'*11}  {'-'*13}  {'-'*15}  {'-'*11}")

    total_gen = total_exp = 0.0
    for month, vals in sorted(monthly.items()):
        gen = vals["gen"]
        exp = vals["exp"]
        cons = max(0.0, gen - exp)
        pct = (cons / gen * 100) if gen > 0 else 0.0
        total_gen += gen
        total_exp += exp
        print(
            f"  {month:<10}  {gen:>11,.1f}  {exp:>13,.1f}  "
            f"{cons:>15,.1f}  {_colour_pct(pct):>11}"
        )

    # Totals
    total_cons = max(0.0, total_gen - total_exp)
    total_pct  = (total_cons / total_gen * 100) if total_gen > 0 else 0.0
    print(f"  {'-'*10}  {'-'*11}  {'-'*13}  {'-'*15}  {'-'*11}")
    print(
        f"  {C.BOLD}{'TOTAL':<10}{C.END}  "
        f"{C.BOLD}{total_gen:>11,.1f}{C.END}  "
        f"{C.BOLD}{total_exp:>13,.1f}{C.END}  "
        f"{C.BOLD}{total_cons:>15,.1f}{C.END}  "
        f"{C.BOLD}{_colour_pct(total_pct):>11}{C.END}"
    )
    print()
    print(
        f"  {C.BOLD}Summary since commissioning:{C.END}  "
        f"{total_gen:,.0f} kWh generated  |  "
        f"{total_exp:,.0f} kWh exported  |  "
        f"{total_cons:,.0f} kWh consumed by offtaker  "
        f"({_colour_pct(total_pct)} of generation)"
    )
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offtaker consumption vs grid export for BAE Fylde (ERS:00001)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--start",
        default=COMMISSION_DATE.strftime("%Y%m%d"),
        help="Start date YYYYMMDD (default: %(default)s — commissioning date)",
    )
    parser.add_argument(
        "--end",
        default=date.today().strftime("%Y%m%d"),
        help="End date YYYYMMDD (default: today)",
    )
    parser.add_argument(
        "--pv-meter",
        default=PV_METER_ID,
        help=f"PV generation meter EMIG ID (default: {PV_METER_ID})",
    )
    parser.add_argument(
        "--api-key",
        default=API_KEY,
        help="Juggle/EMIG API key",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        start = datetime.strptime(args.start, "%Y%m%d").date()
        end   = datetime.strptime(args.end,   "%Y%m%d").date()
    except ValueError:
        print("Error: dates must be YYYYMMDD")
        sys.exit(1)

    global API_KEY
    API_KEY = args.api_key

    print(f"\n{C.BOLD}Fylde Offtaker Consumption Analysis{C.END}")
    print(f"  Plant:    {PLANT_UID}  (BAE Newfold Farm)")
    print(f"  PV Meter: {args.pv_meter}")
    print(f"  Period:   {start}  →  {end}")
    print(f"  ({(end - start).days + 1} days)\n")

    print(f"Fetching generation meter readings ({args.pv_meter})...")
    pv_readings = fetch_meter_readings(args.pv_meter, start, end)

    if not pv_readings:
        print("\nERROR: No readings returned from generation meter. Check API key and meter ID.")
        sys.exit(1)

    print(f"  Total: {len(pv_readings)} readings\n")

    # Fetch grid export from the two Import/Export meters (processed separately, then summed)
    daily_exp: Dict[date, float] = {}
    for ie_id in IE_METER_IDS:
        print(f"Fetching I/E meter readings ({ie_id})...")
        ie_readings = fetch_meter_readings(ie_id, start, end)
        print(f"  Total: {len(ie_readings)} readings\n")
        for d, kwh in daily_delta_kwh(ie_readings, "exportEnergy").items():
            daily_exp[d] = daily_exp.get(d, 0.0) + kwh

    # Generation = importEnergy on the PV generation meter
    daily_gen = daily_delta_kwh(pv_readings, "importEnergy")

    if not daily_gen:
        print("\nWARNING: importEnergy field not found in PV meter readings.")
        print("Available fields:", list(pv_readings[0].keys()) if pv_readings else "N/A")
        sys.exit(1)

    print_monthly_report(daily_gen, daily_exp)


if __name__ == "__main__":
    main()
