#!/usr/bin/env python3
"""
stark_hh_import.py — Import Stark HH meter CSV data into Notion.

Reads one or more Stark "Meter Sequential - Variable Length - CSV kWh - Electricity"
export files, optionally fetches SSP from Elexon BMRS, and upserts daily rows into
the Notion "Stark HH Daily Data" database.

Usage:
    python stark_hh_import.py <file1.csv> [<file2.csv> ...]
    python stark_hh_import.py <file.csv> --dry-run
    python stark_hh_import.py <file.csv> --no-ssp
    python stark_hh_import.py <file.csv> --date 2026-03-01

Environment:
    NOTION_TOKEN    Notion integration token (required)
    STARK_DB_ID     Override Notion database ID (default: auto-discover by title)
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
STARK_DB_ID_ENV = os.environ.get("STARK_DB_ID", "")
STARK_DB_DEFAULT = "30b1773a96c081d78b4ce17e60883782"
STARK_DB_TITLE = "Stark HH Daily Data"

ELEXON_SSP_BASE = (
    "https://data.elexon.co.uk/bmrs/api/v1/balancing/settlement/system-prices"
)
NOTION_API_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Notion helpers
# ---------------------------------------------------------------------------


def _notion_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, *, payload: dict | None = None, retries: int = 3) -> requests.Response:
    delays = [2, 4, 8]
    for attempt in range(retries):
        try:
            resp = requests.request(
                method,
                url,
                headers=_notion_headers(),
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", delays[min(attempt, len(delays) - 1)]))
                print(f"  Rate-limited; waiting {wait}s …")
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            print(f"  Request error ({exc}); retrying in {delays[attempt]}s …")
            time.sleep(delays[attempt])
    raise RuntimeError(f"All {retries} attempts failed for {url}")


def _query_db_for_date(db_id: str, date_str: str) -> str | None:
    """Return the Notion page_id for an existing row matching Date == date_str, or None."""
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload: dict[str, Any] = {
        "filter": {"property": "Date", "title": {"equals": date_str}},
        "page_size": 1,
    }
    resp = _request("POST", url, payload=payload)
    if resp.status_code != 200:
        print(f"  Warning: Notion query failed ({resp.status_code}): {resp.text[:200]}")
        return None
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


def _build_properties(date_str: str, sp_kwh: dict[int, float], sp_ssp: dict[int, float]) -> dict[str, Any]:
    """Build the Notion page properties payload for a daily row."""
    props: dict[str, Any] = {
        "Date": {"title": [{"text": {"content": date_str}}]},
        "Day": {"date": {"start": date_str}},
    }
    for sp in range(1, 49):
        key = f"SP{sp:02d}"
        if sp in sp_kwh:
            props[f"{key}_kWh"] = {"number": round(sp_kwh[sp], 4)}
        if sp in sp_ssp:
            props[f"{key}_SSP"] = {"number": round(sp_ssp[sp], 4)}

    # Populate native number mirrors for chart aggregation
    total_kwh = sum(sp_kwh.values())
    props["Gen MWh"] = {"number": round(total_kwh / 1000, 0)}

    return props


def upsert_notion_row(
    db_id: str,
    date_str: str,
    sp_kwh: dict[int, float],
    sp_ssp: dict[int, float],
    dry_run: bool = False,
) -> str:
    """Create or update the Notion row for date_str. Returns 'created', 'updated', or 'skipped'."""
    props = _build_properties(date_str, sp_kwh, sp_ssp)

    if dry_run:
        total = sum(sp_kwh.values())
        print(f"  [dry-run] {date_str}: {len(sp_kwh)} SPs, {total:.1f} kWh total")
        return "skipped"

    page_id = _query_db_for_date(db_id, date_str)

    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        resp = _request("PATCH", url, payload={"properties": props})
        if resp.status_code not in (200, 201):
            print(f"  Error updating {date_str} ({resp.status_code}): {resp.text[:300]}")
            return "error"
        return "updated"
    else:
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": db_id},
            "properties": props,
        }
        resp = _request("POST", url, payload=payload)
        if resp.status_code not in (200, 201):
            print(f"  Error creating {date_str} ({resp.status_code}): {resp.text[:300]}")
            return "error"
        return "created"


# ---------------------------------------------------------------------------
# Elexon BMRS SSP fetcher
# ---------------------------------------------------------------------------


def fetch_ssp(settlement_date: str) -> dict[int, float]:
    """
    Fetch SSP (£/MWh) per settlement period from Elexon BMRS.

    Args:
        settlement_date: ISO date string e.g. "2026-03-31"

    Returns:
        dict mapping settlement period (1–48) → SSP £/MWh
    """
    url = f"{ELEXON_SSP_BASE}/{settlement_date}?format=json"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  Warning: Elexon SSP request failed for {settlement_date}: {exc}")
        return {}

    if resp.status_code != 200:
        print(f"  Warning: Elexon SSP {settlement_date} returned {resp.status_code}")
        return {}

    data = resp.json().get("data", [])
    result: dict[int, float] = {}
    for item in data:
        sp = item.get("settlementPeriod")
        price = item.get("systemSellPrice") or item.get("ssp")
        if sp is not None and price is not None:
            try:
                result[int(sp)] = float(price)
            except (ValueError, TypeError):
                pass

    return result


# ---------------------------------------------------------------------------
# Stark CSV parser
# ---------------------------------------------------------------------------

# Patterns to recognise date formats
_DATE_PATTERNS = [
    # DD/MM/YYYY
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "%d/%m/%Y"),
    # DD/MM/YY
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$"), "%d/%m/%y"),
    # MM/DD/YY  (Stark portal sometimes uses US format)
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$"), "%m/%d/%y"),
    # YYYY-MM-DD
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
]


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for _pattern, fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _is_data_row(row: list[str]) -> bool:
    """True if the row looks like a Stark data row: date, SP number, kWh value."""
    if len(row) < 3:
        return False
    return _parse_date(row[0]) is not None and row[1].strip().isdigit()


def parse_stark_csv(filepath: str) -> dict[date, dict[int, float]]:
    """
    Parse a Stark "Meter Sequential - Variable Length - CSV kWh - Electricity" file.

    Expected data row format:
        <settlement_date>, <settlement_period>, <kWh>[, ...]

    Returns:
        dict mapping settlement_date → {settlement_period: kWh}
    """
    result: dict[date, dict[int, float]] = defaultdict(dict)

    with open(filepath, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not _is_data_row(row):
                continue
            raw_date = row[0].strip()
            raw_sp = row[1].strip()
            raw_kwh = row[2].strip().replace(",", "")  # remove thousands separator

            parsed_date = _parse_date(raw_date)
            if parsed_date is None:
                continue

            try:
                sp = int(raw_sp)
                kwh = float(raw_kwh)
            except ValueError:
                continue

            if not (1 <= sp <= 50):  # allow 50 for BST clock-change days
                continue

            result[parsed_date][sp] = kwh

    return dict(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import Stark HH meter CSV data into the Notion Stark HH Daily Data database."
    )
    parser.add_argument("files", nargs="+", help="Stark CSV export file(s) to import")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without writing to Notion")
    parser.add_argument("--no-ssp", action="store_true", help="Skip Elexon SSP fetch (kWh only)")
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Only import rows for this specific date",
    )
    parser.add_argument(
        "--db-id",
        default=STARK_DB_ID_ENV or STARK_DB_DEFAULT,
        help="Notion database ID to write to (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not NOTION_TOKEN:
        print("Error: NOTION_TOKEN environment variable is not set.", file=sys.stderr)
        return 1

    filter_date: date | None = None
    if args.date:
        try:
            filter_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: --date must be YYYY-MM-DD, got: {args.date}", file=sys.stderr)
            return 1

    # ---------------------------------------------------------------------------
    # Parse all input files
    # ---------------------------------------------------------------------------
    all_data: dict[date, dict[int, float]] = {}
    for filepath in args.files:
        if not os.path.isfile(filepath):
            print(f"Warning: file not found: {filepath}")
            continue
        print(f"Parsing {filepath} …")
        file_data = parse_stark_csv(filepath)
        if not file_data:
            print(f"  Warning: no data rows found in {filepath}")
            continue
        for d, sp_map in file_data.items():
            if d in all_data:
                all_data[d].update(sp_map)
            else:
                all_data[d] = sp_map
        print(f"  Parsed {len(file_data)} date(s)")

    if not all_data:
        print("No data to import.")
        return 0

    if filter_date:
        all_data = {d: v for d, v in all_data.items() if d == filter_date}
        if not all_data:
            print(f"No data found for {filter_date}.")
            return 0

    sorted_dates = sorted(all_data)
    print(f"\nDates to import: {sorted_dates[0]} → {sorted_dates[-1]} ({len(sorted_dates)} days)\n")

    # ---------------------------------------------------------------------------
    # Fetch SSP and upsert to Notion
    # ---------------------------------------------------------------------------
    counts = {"created": 0, "updated": 0, "skipped": 0, "error": 0}

    for d in sorted_dates:
        date_str = d.isoformat()
        sp_kwh = all_data[d]
        sp_ssp: dict[int, float] = {}

        if not args.no_ssp:
            print(f"Fetching SSP for {date_str} …", end=" ", flush=True)
            sp_ssp = fetch_ssp(date_str)
            if sp_ssp:
                print(f"{len(sp_ssp)} periods")
            else:
                print("none returned")

        total_kwh = sum(sp_kwh.values())
        print(
            f"{'[dry-run] ' if args.dry_run else ''}Upserting {date_str}: "
            f"{len(sp_kwh)} SPs, {total_kwh:.1f} kWh"
            + (f", {len(sp_ssp)} SSP periods" if sp_ssp else "")
            + " …",
            end=" ",
            flush=True,
        )

        result = upsert_notion_row(args.db_id, date_str, sp_kwh, sp_ssp, dry_run=args.dry_run)
        counts[result] += 1
        print(result)

        # Respect Notion rate limits (3 req/s average)
        if not args.dry_run:
            time.sleep(0.4)

    print(
        f"\nDone. Created: {counts['created']}, Updated: {counts['updated']}, "
        f"Skipped: {counts['skipped']}, Errors: {counts['error']}"
    )
    return 0 if counts["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
