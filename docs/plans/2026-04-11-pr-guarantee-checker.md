# PR Guarantee Checker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python script that fetches EPC contract data and actual generation from Juggle, calculates monthly PR, and compares it against the contractual PR guarantee.

**Architecture:** Single-file script at `tools/pr-guarantee/pr_checker.py`. Pulls EPC data from the Notion Contract Register, asset metadata (capacity, lat/lon, Juggle name) from the Notion Asset Register, generation from the Juggle EMIG API, and irradiance from PVGIS. Outputs a monthly PR vs guarantee table to the terminal (and optionally CSV).

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`, `notion-client`, `pandas`, `tabulate`. PVGIS API (no key required). Juggle EMIG API (token auth).

---

## Context

### Notion data sources

| Resource | ID |
|---|---|
| Contract Register | `collection://44a09b06-83ab-4d3d-a2db-dc2fd4de3557` (DB: `0af3766706524aa595e6219ed064a64a`) |
| Asset Register | `collection://2d01773a-96c0-8032-aa8e-000be7d21637` (DB: `2d01773a96c0807bb964ce1aff762997`) |

**Contract Register fields used:** `Contract Name`, `Contract Type` (filter: EPC), `Key Risks` (contains PR guarantee % in free text, e.g. "PR guarantee 84%"), `Linked Asset` (relation to asset register rows).

**Asset Register fields used:** `Project Name`, `TIC kWp`, `Long/Lat`, `Data Source Match` (Juggle plant name, e.g. "Metrocentre"), `EPC Contractor`.

**Metro Centre asset register entry:**
- TIC kWp: 738
- Lat/Lon: 54.958512517141635, -1.6703782180021882
- Data Source Match: `Metrocentre`
- The EPC contract entry has no explicit PR % in Key Risks — store as config override (see `.env.example`)

### Juggle API

- Base URL: `https://www.emig.co.uk/p/api`
- Auth: `Authorization: token {EMIG_API_KEY}`
- Key endpoints:
  - `GET /plant-list` → `[{plantUID, name, ...}]`
  - `GET /plant/{uid}` → plant details + meters list
  - `GET /meter/{emig_id}/readings?startDate=YYYYMMDD&endDate=YYYYMMDD` → `{readings: [{ts, importActivePower: {value}, exportActivePower: {value}, ...}]}`
- Plant UID format: `AMP:00XXX`. Match by name using `Data Source Match` from asset register.
- API key: `EMIG_API_KEY` env var (same key used in solar-platform and Solar-Monitoring)

### PR calculation

```
Daily PR = sum(actual_energy_kwh) / sum(expected_energy_kwh)
Expected daily energy (kWh) = TIC_kWp × daily_irradiation_kWh_m²
```

- Generation: sum of all inverter meters for the plant, 30-min intervals
- Irradiance: PVGIS hourly GHI → sum to daily kWh/m²
- Filter days with < 0.5 kWh/m² daily irradiation (insufficient sunlight)
- Monthly PR = total monthly energy / total monthly expected energy

### PVGIS API

```
GET https://re.jrc.ec.europa.eu/api/v5_2/seriescalc
  ?lat=54.958&lon=-1.670&startyear=YYYY&endyear=YYYY
  &outputformat=json&pvcalculation=0&components=1
```
Returns hourly `G(h)` (GHI in W/m²). Convert to kWh/m² per hour by dividing by 1000.

---

## File structure

```
tools/pr-guarantee/
├── pr_checker.py         # Main script — all logic in one file
├── requirements.txt
├── .env.example
└── tests/
    └── test_pr_calc.py   # Unit tests for PR calculation only (no API calls)
```

---

## Task 1: Scaffold project

**Files:**
- Create: `tools/pr-guarantee/requirements.txt`
- Create: `tools/pr-guarantee/.env.example`
- Create: `tools/pr-guarantee/pr_checker.py` (skeleton)
- Create: `tools/pr-guarantee/tests/test_pr_calc.py` (skeleton)

- [ ] **Step 1: Create requirements.txt**

```
requests==2.31.0
python-dotenv==1.0.1
notion-client==2.2.1
pandas==2.1.4
tabulate==0.9.0
```

- [ ] **Step 2: Create .env.example**

```
# Juggle EMIG API key (same as used in Solar-Monitoring and solar-platform)
EMIG_API_KEY=your_key_here

# Notion integration token
NOTION_TOKEN=your_notion_token_here

# Override PR guarantee % for sites where it is not in the contract text
# Format: comma-separated "SiteName=XX.X" pairs
PR_GUARANTEE_OVERRIDES=Metrocentre=80.0
```

- [ ] **Step 3: Create pr_checker.py skeleton**

```python
"""
PR Guarantee Checker
====================
Compares actual monthly PR against the EPC contractual PR guarantee.

Usage:
    python pr_checker.py [--site SITE_NAME] [--months N] [--csv output.csv]

Examples:
    python pr_checker.py --site Metrocentre --months 12
    python pr_checker.py  # all EPC sites with PR guarantee data
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv
from notion_client import Client as NotionClient
from tabulate import tabulate

load_dotenv()

EMIG_BASE_URL = "https://www.emig.co.uk/p/api"
PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"

CONTRACT_DB_ID = "0af3766706524aa595e6219ed064a64a"
ASSET_DB_ID = "2d01773a96c0807bb964ce1aff762997"


def main():
    pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create tests/test_pr_calc.py skeleton**

```python
"""Tests for PR calculation logic (no API calls)."""
import pytest
import pandas as pd
```

- [ ] **Step 5: Commit**

```bash
cd /Users/peterhall/Projects/solar-platform
git add tools/pr-guarantee/
git commit -m "feat: scaffold pr-guarantee checker tool"
```

---

## Task 2: PR calculation function (TDD)

**Files:**
- Modify: `tools/pr-guarantee/pr_checker.py` — add `calculate_monthly_pr()`
- Modify: `tools/pr-guarantee/tests/test_pr_calc.py`

- [ ] **Step 1: Write failing tests**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pr_checker import calculate_monthly_pr
import pandas as pd

def test_monthly_pr_basic():
    """Perfect system: actual == expected → PR 1.0"""
    dates = pd.date_range("2024-06-01", periods=30, freq="D")
    gen = pd.Series([100.0] * 30, index=dates)   # kWh/day
    irr = pd.Series([0.5] * 30, index=dates)      # kWh/m²/day
    capacity_kwp = 200.0
    # expected = 200 * 0.5 = 100 kWh/day → PR = 1.0
    result = calculate_monthly_pr(gen, irr, capacity_kwp)
    assert len(result) == 1
    assert abs(result.iloc[0]["pr"] - 1.0) < 0.001

def test_monthly_pr_filters_low_irradiance():
    """Days with irradiance < 0.5 kWh/m² are excluded."""
    dates = pd.date_range("2024-12-01", periods=31, freq="D")
    gen = pd.Series([50.0] * 31, index=dates)
    # Half days below threshold
    irr_values = [0.1] * 15 + [1.0] * 16
    irr = pd.Series(irr_values, index=dates)
    capacity_kwp = 100.0
    result = calculate_monthly_pr(gen, irr, capacity_kwp)
    # Only 16 days included; expected = 100 * 1.0 = 100 kWh, actual = 50 kWh → PR 0.5
    assert abs(result.iloc[0]["pr"] - 0.5) < 0.001

def test_monthly_pr_groups_by_month():
    """Returns one row per calendar month."""
    dates = pd.date_range("2024-06-01", periods=60, freq="D")
    gen = pd.Series([100.0] * 60, index=dates)
    irr = pd.Series([0.5] * 60, index=dates)
    result = calculate_monthly_pr(gen, irr, 200.0)
    assert len(result) == 2  # June + July
    assert list(result["month"]) == ["2024-06", "2024-07"]

def test_monthly_pr_empty_after_filter():
    """All days below irradiance threshold → empty result."""
    dates = pd.date_range("2024-12-01", periods=31, freq="D")
    gen = pd.Series([10.0] * 31, index=dates)
    irr = pd.Series([0.1] * 31, index=dates)
    result = calculate_monthly_pr(gen, irr, 100.0)
    assert result.empty
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/peterhall/Projects/solar-platform/tools/pr-guarantee
python -m pytest tests/test_pr_calc.py -v
```
Expected: `ImportError` or `AttributeError` (function not yet defined)

- [ ] **Step 3: Implement `calculate_monthly_pr()`**

Add to `pr_checker.py` above `main()`:

```python
MIN_DAILY_IRRADIANCE_KWH_M2 = 0.5  # filter days with insufficient sun


def calculate_monthly_pr(
    daily_gen_kwh: pd.Series,
    daily_irr_kwh_m2: pd.Series,
    capacity_kwp: float,
) -> pd.DataFrame:
    """
    Calculate monthly PR from daily generation and irradiance series.

    Args:
        daily_gen_kwh: DatetimeIndex series of daily generation (kWh).
        daily_irr_kwh_m2: DatetimeIndex series of daily GHI (kWh/m²).
        capacity_kwp: DC capacity of the system (kWp).

    Returns:
        DataFrame with columns: month (YYYY-MM), actual_kwh, expected_kwh, pr.
    """
    df = pd.DataFrame({"gen": daily_gen_kwh, "irr": daily_irr_kwh_m2}).dropna()
    df = df[df["irr"] >= MIN_DAILY_IRRADIANCE_KWH_M2]
    if df.empty:
        return pd.DataFrame(columns=["month", "actual_kwh", "expected_kwh", "pr"])

    df["expected"] = capacity_kwp * df["irr"]
    df["month"] = df.index.to_period("M").astype(str)

    monthly = df.groupby("month").agg(
        actual_kwh=("gen", "sum"),
        expected_kwh=("expected", "sum"),
    ).reset_index()
    monthly["pr"] = monthly["actual_kwh"] / monthly["expected_kwh"]
    return monthly
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_pr_calc.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/pr-guarantee/pr_checker.py tools/pr-guarantee/tests/test_pr_calc.py
git commit -m "feat: add PR calculation function with tests"
```

---

## Task 3: Notion data fetcher

**Files:**
- Modify: `tools/pr-guarantee/pr_checker.py` — add `load_epc_sites()` and `load_asset_metadata()`

- [ ] **Step 1: Add `load_epc_sites()` and `load_asset_metadata()`**

```python
import json


def load_epc_sites(notion: NotionClient) -> list[dict]:
    """
    Query Contract Register for EPC contracts and extract PR guarantee.

    Returns list of dicts:
      {contract_name, counterparty, linked_asset_ids, pr_guarantee_pct (float|None)}
    """
    results = []
    cursor = None
    while True:
        kwargs = {
            "database_id": CONTRACT_DB_ID,
            "filter": {"property": "Contract Type", "select": {"equals": "EPC"}},
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name = _rich_text(props.get("Contract Name", {}))
            counterparty = _rich_text(props.get("Counterparty", {}))
            key_risks = _rich_text(props.get("Key Risks", {}))
            linked = [
                r["id"].replace("-", "")
                for r in props.get("Linked Asset", {}).get("relation", [])
            ]
            pr_pct = _extract_pr_guarantee(key_risks)
            results.append({
                "contract_name": name,
                "counterparty": counterparty,
                "linked_asset_ids": linked,
                "pr_guarantee_pct": pr_pct,
            })
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return results


def load_asset_metadata(notion: NotionClient, page_ids: list[str]) -> dict[str, dict]:
    """
    Fetch asset register entries by page ID.

    Returns dict keyed by page_id:
      {project_name, capacity_kwp, lat, lon, juggle_name}
    """
    assets = {}
    for pid in page_ids:
        try:
            page = notion.pages.retrieve(pid)
            props = page["properties"]
            name = _rich_text(props.get("Project Name", {}))
            kwp = _number(props.get("TIC kWp", {}))
            latlon = _rich_text(props.get("Long/Lat", {}))
            juggle_name = _rich_text(props.get("Data Source Match", {}))
            lat, lon = _parse_latlon(latlon)
            assets[pid] = {
                "project_name": name,
                "capacity_kwp": kwp,
                "lat": lat,
                "lon": lon,
                "juggle_name": juggle_name,
            }
        except Exception as e:
            print(f"  Warning: could not fetch asset {pid}: {e}", file=sys.stderr)
    return assets


# ── Notion helpers ────────────────────────────────────────────────────

def _rich_text(prop: dict) -> str:
    """Extract plain text from a title or rich_text property."""
    for key in ("title", "rich_text"):
        parts = prop.get(key, [])
        if parts:
            return "".join(p.get("plain_text", "") for p in parts)
    return prop.get("text", {}).get("content", "") if prop.get("type") == "text" else ""


def _number(prop: dict) -> Optional[float]:
    return prop.get("number")


def _parse_latlon(latlon_str: str) -> tuple[Optional[float], Optional[float]]:
    """Parse '54.958, -1.670' into (lat, lon)."""
    if not latlon_str:
        return None, None
    parts = latlon_str.split(",")
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None, None


def _extract_pr_guarantee(text: str) -> Optional[float]:
    """
    Extract PR guarantee percentage from contract Key Risks free text.

    Matches patterns like:
      - "PR guarantee 84%"
      - "PR guarantee: 84%"
      - "performance ratio guarantee of 80%"
    """
    if not text:
        return None
    patterns = [
        r"PR guarantee[:\s]+(\d+(?:\.\d+)?)\s*%",
        r"performance ratio guarantee[:\s]+(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
        r"PR\s+guarantee\s+(\d+(?:\.\d+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None
```

- [ ] **Step 2: Add tests for `_extract_pr_guarantee()` and `_parse_latlon()`**

In `tests/test_pr_calc.py`:

```python
from pr_checker import _extract_pr_guarantee, _parse_latlon

def test_extract_pr_guarantee_standard():
    assert _extract_pr_guarantee("PR guarantee 84%; EUR 800/0.1%") == 84.0

def test_extract_pr_guarantee_with_colon():
    assert _extract_pr_guarantee("PR guarantee: 80%") == 80.0

def test_extract_pr_guarantee_none():
    assert _extract_pr_guarantee("Performance LDs capped at 10%") is None

def test_extract_pr_guarantee_decimal():
    assert _extract_pr_guarantee("PR guarantee 79.5%") == 79.5

def test_parse_latlon_valid():
    lat, lon = _parse_latlon("54.958512517141635, -1.6703782180021882")
    assert abs(lat - 54.9585) < 0.001
    assert abs(lon - (-1.6704)) < 0.001

def test_parse_latlon_empty():
    assert _parse_latlon("") == (None, None)
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_pr_calc.py -v
```
Expected: all 10 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/pr-guarantee/pr_checker.py tools/pr-guarantee/tests/test_pr_calc.py
git commit -m "feat: add Notion data fetcher and helper functions"
```

---

## Task 4: Juggle generation fetcher

**Files:**
- Modify: `tools/pr-guarantee/pr_checker.py` — add `find_juggle_plant_uid()` and `fetch_juggle_daily_generation()`

- [ ] **Step 1: Add Juggle functions**

```python
def find_juggle_plant_uid(api_key: str, plant_name: str) -> Optional[str]:
    """
    Look up a plant UID from the Juggle /plant-list endpoint by matching name.

    plant_name is the value from the asset register's 'Data Source Match' field,
    e.g. "Metrocentre". Matching is case-insensitive.
    """
    url = f"{EMIG_BASE_URL}/plant-list"
    headers = {"Authorization": f"token {api_key}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    plants = resp.json()
    target = plant_name.strip().lower()
    for p in plants:
        if p.get("name", "").strip().lower() == target:
            return p["plantUID"]
    # Partial match fallback
    for p in plants:
        if target in p.get("name", "").strip().lower():
            return p["plantUID"]
    return None


def fetch_juggle_daily_generation(
    api_key: str,
    plant_uid: str,
    start: date,
    end: date,
) -> pd.Series:
    """
    Fetch daily generation (kWh) from Juggle for a plant.

    Calls /plant/{uid} to list meters, then /meter/{id}/readings for each meter
    in the date range. Sums across all inverter-type meters per day.

    Returns a pd.Series with DatetimeIndex (daily).
    """
    headers = {"Authorization": f"token {api_key}"}

    # Get plant meters
    plant_resp = requests.get(
        f"{EMIG_BASE_URL}/plant/{plant_uid}", headers=headers, timeout=30
    )
    plant_resp.raise_for_status()
    meters = plant_resp.json().get("meters", [])

    all_readings: list[dict] = []

    # Fetch month-by-month to stay within API limits
    current = date(start.year, start.month, 1)
    while current <= end:
        month_end = _last_day_of_month(current)
        fetch_end = min(month_end, end)
        start_str = current.strftime("%Y%m%d")
        end_str = fetch_end.strftime("%Y%m%d")

        for meter in meters:
            emig_id = meter.get("emigId")
            if not emig_id:
                continue
            url = f"{EMIG_BASE_URL}/meter/{emig_id}/readings?startDate={start_str}&endDate={end_str}"
            try:
                r = requests.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                for reading in r.json().get("readings", []):
                    reading["_emig_id"] = emig_id
                    all_readings.append(reading)
            except Exception as e:
                print(f"  Warning: meter {emig_id} {start_str}: {e}", file=sys.stderr)

        # Advance to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if not all_readings:
        return pd.Series(dtype=float)

    df = pd.DataFrame(all_readings)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)

    # Extract power: exportActivePower (negative = export) or importActivePower
    def extract_power_kw(row) -> float:
        for field in ("exportActivePower", "importActivePower"):
            val = row.get(field)
            if isinstance(val, dict):
                v = val.get("value")
                if v is not None:
                    return abs(float(v)) / 1000.0
        return 0.0

    df["power_kw"] = df.apply(extract_power_kw, axis=1)

    # Resample to 30-min, sum across meters, then integrate to kWh
    df = df.set_index("ts").sort_index()
    df_site = df.groupby(level=0)["power_kw"].sum()
    df_30min = df_site.resample("30min").mean()
    df_30min_kwh = df_30min * 0.5  # kW * 0.5h = kWh per interval
    daily = df_30min_kwh.resample("D").sum()

    return daily


def _last_day_of_month(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)
```

- [ ] **Step 2: Commit**

```bash
git add tools/pr-guarantee/pr_checker.py
git commit -m "feat: add Juggle generation fetcher"
```

---

## Task 5: PVGIS irradiance fetcher

**Files:**
- Modify: `tools/pr-guarantee/pr_checker.py` — add `fetch_pvgis_daily_irradiance()`

- [ ] **Step 1: Add PVGIS function**

```python
def fetch_pvgis_daily_irradiance(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
) -> pd.Series:
    """
    Fetch hourly GHI from PVGIS and aggregate to daily kWh/m².

    Uses PVGIS ERA5 hourly data (pvcalculation=0, components=1).
    G(h) is in W/m² per hour → divide by 1000 for kWh/m².
    """
    params = {
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "startyear": start_year,
        "endyear": end_year,
        "outputformat": "json",
        "pvcalculation": 0,
        "components": 1,
    }
    resp = requests.get(PVGIS_BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("outputs", {}).get("irradiance", {}).get("hourly", [])
    if not hourly:
        raise ValueError("PVGIS returned no hourly irradiance data")

    records = [
        {
            "ts": pd.to_datetime(h["time"], format="%Y%m%d:%H%M"),
            "ghi_kwh_m2": float(h.get("G(h)", 0)) / 1000.0,
        }
        for h in hourly
    ]
    df = pd.DataFrame(records).set_index("ts").sort_index()
    daily = df["ghi_kwh_m2"].resample("D").sum()
    return daily
```

- [ ] **Step 2: Commit**

```bash
git add tools/pr-guarantee/pr_checker.py
git commit -m "feat: add PVGIS irradiance fetcher"
```

---

## Task 6: Wire up main() and CLI

**Files:**
- Modify: `tools/pr-guarantee/pr_checker.py` — complete `main()`

- [ ] **Step 1: Complete main()**

```python
def main():
    parser = argparse.ArgumentParser(description="Compare actual PR vs EPC guarantee")
    parser.add_argument("--site", help="Site name to check (default: all EPC sites)")
    parser.add_argument("--months", type=int, default=12, help="Number of months to analyse (default: 12)")
    parser.add_argument("--csv", help="Optional path to write results CSV")
    args = parser.parse_args()

    api_key = os.environ.get("EMIG_API_KEY", "")
    notion_token = os.environ.get("NOTION_TOKEN", "")
    if not api_key:
        sys.exit("Error: EMIG_API_KEY not set in environment")
    if not notion_token:
        sys.exit("Error: NOTION_TOKEN not set in environment")

    # Parse PR guarantee overrides from env
    overrides: dict[str, float] = {}
    for pair in os.environ.get("PR_GUARANTEE_OVERRIDES", "").split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            try:
                overrides[k.strip().lower()] = float(v.strip())
            except ValueError:
                pass

    notion = NotionClient(auth=notion_token)

    print("Loading EPC contracts from Notion...")
    contracts = load_epc_sites(notion)
    print(f"  Found {len(contracts)} EPC contracts")

    # Calculate date range
    end_date = date.today() - timedelta(days=1)
    start_date = date(end_date.year, end_date.month, 1)
    for _ in range(args.months - 1):
        start_date = (start_date - timedelta(days=1)).replace(day=1)

    all_rows = []

    for contract in contracts:
        site_name = contract["contract_name"]

        # Filter by --site if given
        if args.site and args.site.lower() not in site_name.lower():
            continue

        # Resolve PR guarantee
        pr_guarantee = contract["pr_guarantee_pct"]
        juggle_key = None

        # Load asset metadata
        if not contract["linked_asset_ids"]:
            print(f"  {site_name}: no linked asset — skipping")
            continue

        asset_id = contract["linked_asset_ids"][0]
        assets = load_asset_metadata(notion, [asset_id])
        asset = assets.get(asset_id)
        if not asset:
            print(f"  {site_name}: could not load asset — skipping")
            continue

        juggle_key = (asset.get("juggle_name") or "").lower()
        if not pr_guarantee and juggle_key in overrides:
            pr_guarantee = overrides[juggle_key]

        if not pr_guarantee:
            print(f"  {site_name}: no PR guarantee found — skipping")
            continue

        capacity_kwp = asset.get("capacity_kwp")
        lat = asset.get("lat")
        lon = asset.get("lon")

        if not capacity_kwp or not lat or not lon:
            print(f"  {site_name}: missing capacity or location — skipping")
            continue

        juggle_name = asset.get("juggle_name", "")
        print(f"\n{site_name} (Juggle: {juggle_name}, {capacity_kwp} kWp, PR guarantee: {pr_guarantee}%)")

        # Find Juggle plant UID
        print("  Finding Juggle plant...")
        plant_uid = find_juggle_plant_uid(api_key, juggle_name)
        if not plant_uid:
            print(f"  Could not find Juggle plant for '{juggle_name}' — skipping")
            continue
        print(f"  Plant UID: {plant_uid}")

        # Fetch generation
        print(f"  Fetching generation {start_date} → {end_date}...")
        try:
            gen = fetch_juggle_daily_generation(api_key, plant_uid, start_date, end_date)
        except Exception as e:
            print(f"  Error fetching generation: {e} — skipping")
            continue
        print(f"  {len(gen)} days of generation data")

        # Fetch irradiance from PVGIS
        years = sorted({start_date.year, end_date.year})
        print(f"  Fetching PVGIS irradiance for {years}...")
        irr_parts = []
        for yr in years:
            try:
                part = fetch_pvgis_daily_irradiance(lat, lon, yr, yr)
                irr_parts.append(part)
            except Exception as e:
                print(f"  PVGIS error for {yr}: {e}")
        if not irr_parts:
            print("  No irradiance data — skipping")
            continue
        irr = pd.concat(irr_parts).sort_index()
        irr = irr[~irr.index.duplicated()]

        # Calculate monthly PR
        monthly = calculate_monthly_pr(gen, irr, capacity_kwp)
        if monthly.empty:
            print("  No valid PR data after filtering")
            continue

        monthly["site"] = site_name
        monthly["capacity_kwp"] = capacity_kwp
        monthly["pr_guarantee_pct"] = pr_guarantee
        monthly["pr_pct"] = (monthly["pr"] * 100).round(1)
        monthly["guarantee_met"] = monthly["pr_pct"] >= pr_guarantee
        all_rows.append(monthly)

    if not all_rows:
        print("\nNo results.")
        return

    results = pd.concat(all_rows, ignore_index=True)

    # Print table
    display_cols = ["site", "month", "actual_kwh", "expected_kwh", "pr_pct", "pr_guarantee_pct", "guarantee_met"]
    display = results[display_cols].copy()
    display["actual_kwh"] = display["actual_kwh"].round(0).astype(int)
    display["expected_kwh"] = display["expected_kwh"].round(0).astype(int)
    print("\n" + tabulate(display, headers="keys", tablefmt="rounded_outline", showindex=False))

    # Summary
    met = results["guarantee_met"].sum()
    total = len(results)
    print(f"\n{met}/{total} months met the PR guarantee")

    if args.csv:
        results.to_csv(args.csv, index=False)
        print(f"Results saved to {args.csv}")
```

- [ ] **Step 2: Install dependencies and do a smoke test**

```bash
cd /Users/peterhall/Projects/solar-platform/tools/pr-guarantee
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Copy .env from solar-platform root (which has EMIG_API_KEY and NOTION_TOKEN)
cp /Users/peterhall/Projects/solar-platform/.env .env
python pr_checker.py --site Metrocentre --months 3
```
Expected: script runs, finds Metrocentre in Juggle, prints a monthly PR table.

- [ ] **Step 3: Run tests one final time**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/pr-guarantee/
git commit -m "feat: complete PR guarantee checker — Notion + Juggle + PVGIS"
```

---

## Known gaps / follow-on work

1. **PR guarantee not in Notion for Metrocentre** — needs to be added to the EPC contract entry's `Key Risks` field or a new structured field added to the Contract Register schema. Use `PR_GUARANTEE_OVERRIDES` env var as a workaround for now.

2. **Juggle 30-min vs daily data** — the script fetches sub-daily readings and integrates to kWh. If the API returns daily totals instead, the integration step is a no-op. Verify the meter reading format for Metrocentre on first run.

3. **PVGIS data is TMY (typical year)** — for long-term guarantee assessment this is fine. For monthly comparison, site-specific measured irradiance (e.g. from Metris or a pyranometer) would be more accurate.

4. **DLP period tracking** — the Metrocentre DLP may have expired (~28 Mar 2026). Consider adding a flag to only show months within the DLP window.

5. **Multi-MPAN sites** — Metrocentre has two MPANs (~1 MW total). Confirm the Juggle plant aggregates both or add a second plant lookup.
