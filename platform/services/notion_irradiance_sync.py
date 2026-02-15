"""Notion Monthly Irradiance Sync Service.

Reads monthly generation and irradiance data from the DuckDB ``solar_data``
table, then creates/updates a Notion database with one row per site per month.

Usage (CLI)::

    python -m services.notion_irradiance_sync          # sync all available data
    python -m services.notion_irradiance_sync --dry-run  # preview without writing

The Notion database is auto-created on first run under the configured parent
page (``NOTION_PAGE_ID``).  The created DB ID is cached in ``Settings`` so
subsequent runs update in-place.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import httpx

from services.config import get_settings

# ── Notion API constants ────────────────────────────────────────────────

_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"
_PAGE_SIZE = 100

# ── Database schema definition ──────────────────────────────────────────

DB_TITLE = "Monthly Irradiance by Site"

DB_PROPERTIES: dict[str, dict] = {
    "Site":                         {"title": {}},
    "Month":                        {"rich_text": {}},
    "kWp":                          {"number": {"format": "number"}},
    "Actual Irradiance (kWh/m²)":   {"number": {"format": "number"}},
    "Forecast Irradiance (kWh/m²)": {"number": {"format": "number"}},
    "SolarGIS GTI (kWh/m²)":        {"number": {"format": "number"}},
    "SolarGIS GHI (kWh/m²)":        {"number": {"format": "number"}},
    "SG vs Actual (%)":             {"number": {"format": "percent"}},
    "Irr Variance (%)":             {"number": {"format": "percent"}},
    "Actual Gen (kWh)":             {"number": {"format": "number"}},
    "Forecast Gen (kWh)":           {"number": {"format": "number"}},
    "Gen Variance (%)":             {"number": {"format": "percent"}},
    "kWh/kWp":                      {"number": {"format": "number"}},
    "Actual PR (%)":                {"number": {"format": "percent"}},
    "Availability (%)":             {"number": {"format": "percent"}},
}


# ── HTTP helpers ────────────────────────────────────────────────────────

def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    url: str,
    token: str,
    *,
    json_body: dict | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    """HTTP request with retry, rate-limit, and error handling."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.request(
                method, url, headers=_headers(token), json=json_body, timeout=30.0
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
                print(f"  Rate limited — waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    raise last_exc or RuntimeError(f"Request failed: {method} {url}")


# ── Notion CRUD ─────────────────────────────────────────────────────────

def find_database(token: str, title: str = DB_TITLE) -> str | None:
    """Search for an existing database by title."""
    body = _request(
        "POST",
        f"{_API}/search",
        token,
        json_body={
            "query": title,
            "filter": {"value": "database", "property": "object"},
        },
    )
    for result in body.get("results", []):
        titles = result.get("title", [])
        if titles and titles[0].get("plain_text") == title:
            return result["id"]
    return None


def create_database(token: str, parent_page_id: str) -> str:
    """Create the Monthly Irradiance database under the given page."""
    body = _request(
        "POST",
        f"{_API}/databases",
        token,
        json_body={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": DB_TITLE}}],
            "properties": DB_PROPERTIES,
        },
    )
    db_id = body["id"]
    print(f"  Created Notion DB: {db_id}")
    return db_id


def ensure_schema(token: str, db_id: str) -> None:
    """Ensure the Notion database has all required columns (adds missing ones)."""
    body = _request("GET", f"{_API}/databases/{db_id}", token)
    existing = set(body.get("properties", {}).keys())
    missing = {k: v for k, v in DB_PROPERTIES.items() if k not in existing}
    if missing:
        print(f"  Adding {len(missing)} new columns: {', '.join(missing.keys())}")
        _request(
            "PATCH", f"{_API}/databases/{db_id}", token,
            json_body={"properties": missing},
        )


def query_existing_rows(token: str, db_id: str) -> dict[tuple[str, str], str]:
    """Return {(site, month): page_id} for all existing rows."""
    index: dict[tuple[str, str], str] = {}
    cursor: str | None = None

    while True:
        payload: dict[str, Any] = {"page_size": _PAGE_SIZE}
        if cursor:
            payload["start_cursor"] = cursor

        body = _request(
            "POST", f"{_API}/databases/{db_id}/query", token, json_body=payload
        )

        for page in body.get("results", []):
            props = page.get("properties", {})
            site_parts = props.get("Site", {}).get("title", [])
            site = site_parts[0].get("plain_text", "") if site_parts else ""
            month_parts = props.get("Month", {}).get("rich_text", [])
            month = month_parts[0].get("plain_text", "") if month_parts else ""
            if site and month:
                index[(site, month)] = page["id"]

        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
        if not cursor:
            break

    return index


def upsert_page(
    token: str,
    db_id: str,
    page_id: str | None,
    row: dict[str, Any],
) -> str:
    """Create or update a Notion page with the given row data."""
    properties = _build_properties(row)

    if page_id:
        body = _request(
            "PATCH",
            f"{_API}/pages/{page_id}",
            token,
            json_body={"properties": properties},
        )
        return body["id"]
    else:
        body = _request(
            "POST",
            f"{_API}/pages",
            token,
            json_body={
                "parent": {"database_id": db_id},
                "properties": properties,
            },
        )
        return body["id"]


def _build_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a flat data dict to Notion property format."""
    props: dict[str, Any] = {}

    # Title (Site)
    props["Site"] = {
        "title": [{"text": {"content": str(row.get("Site", ""))}}]
    }

    # Rich text (Month)
    props["Month"] = {
        "rich_text": [{"text": {"content": str(row.get("Month", ""))}}]
    }

    # Number fields
    number_map = {
        "kWp":                          "kWp",
        "Actual Irradiance (kWh/m²)":   "actual_irr",
        "Forecast Irradiance (kWh/m²)": "forecast_irr",
        "Irr Variance (%)":             "irr_variance_pct",
        "Actual Gen (kWh)":             "actual_gen",
        "Forecast Gen (kWh)":           "forecast_gen",
        "Gen Variance (%)":             "gen_variance_pct",
        "kWh/kWp":                      "kwh_per_kwp",
        "SolarGIS GTI (kWh/m²)":        "solargis_gti",
        "SolarGIS GHI (kWh/m²)":        "solargis_ghi",
        "SG vs Actual (%)":             "sg_vs_actual_pct",
        "Actual PR (%)":                "actual_pr",
        "Availability (%)":             "availability",
    }

    for notion_col, data_key in number_map.items():
        val = row.get(data_key)
        if val is not None and val == val:  # skip NaN
            props[notion_col] = {"number": round(float(val), 4)}
        else:
            props[notion_col] = {"number": None}

    return props


# ── Data extraction from DuckDB ─────────────────────────────────────────

def load_irradiance_data() -> list[dict[str, Any]]:
    """Query solar_data from DuckDB, merge SolarGIS aggregates, and compute derived metrics."""
    import pandas as pd
    from services.solargis_monthly_aggregator import aggregate_solargis_monthly

    settings = get_settings()
    db_path = str(settings.db_path)

    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute("""
            SELECT
                Site,
                Date,
                kWp,
                "Actual Irr (kWh/m2)"  AS actual_irr,
                "Forecast Irr"         AS forecast_irr,
                "Actual Gen (kWh)"     AS actual_gen,
                "Forecast Gen (kWh)"   AS forecast_gen,
                "kWh/kWp"              AS kwh_per_kwp,
                "Actual PR (%)"        AS actual_pr,
                "Availability (%)"     AS availability
            FROM solar_data
            ORDER BY Site, Date
        """).fetchdf()
    finally:
        conn.close()

    # Load SolarGIS 15-min aggregated data
    try:
        sg_df = aggregate_solargis_monthly()
        sg_lookup: dict[tuple[str, str], dict] = {}
        for _, sg in sg_df.iterrows():
            sg_lookup[(sg["Site"], sg["Month"])] = {
                "solargis_gti": sg["SolarGIS GTI (kWh/m²)"],
                "solargis_ghi": sg["SolarGIS GHI (kWh/m²)"],
            }
        print(f"  Loaded {len(sg_lookup)} SolarGIS site-months")
    except Exception as exc:
        print(f"  WARN: SolarGIS data unavailable: {exc}")
        sg_lookup = {}

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        actual_irr = r["actual_irr"] if r["actual_irr"] == r["actual_irr"] else None
        forecast_irr = r["forecast_irr"] if r["forecast_irr"] == r["forecast_irr"] else None

        # Irradiance variance %
        irr_var = None
        if actual_irr and forecast_irr and forecast_irr > 0:
            irr_var = (actual_irr - forecast_irr) / forecast_irr

        actual_gen = r["actual_gen"] if r["actual_gen"] == r["actual_gen"] else None
        forecast_gen = r["forecast_gen"] if r["forecast_gen"] == r["forecast_gen"] else None

        # Gen variance %
        gen_var = None
        if actual_gen and forecast_gen and forecast_gen > 0:
            gen_var = (actual_gen - forecast_gen) / forecast_gen

        # PR and availability are stored as 0-1 in some rows and 0-100 in others
        pr = r["actual_pr"] if r["actual_pr"] == r["actual_pr"] else None
        if pr is not None and pr > 1:
            pr = pr / 100.0  # normalise to fraction for Notion percent format

        avail = r["availability"] if r["availability"] == r["availability"] else None
        if avail is not None and avail > 1:
            avail = avail / 100.0

        # Merge SolarGIS data
        sg = sg_lookup.get((r["Site"], r["Date"]), {})
        sg_gti = sg.get("solargis_gti")
        sg_ghi = sg.get("solargis_ghi")

        # SolarGIS vs Actual variance
        sg_vs_actual = None
        if sg_gti and actual_irr and actual_irr > 0:
            sg_vs_actual = (sg_gti - actual_irr) / actual_irr

        rows.append({
            "Site": r["Site"],
            "Month": r["Date"],  # e.g. "Apr-25"
            "kWp": r["kWp"] if r["kWp"] == r["kWp"] else None,
            "actual_irr": actual_irr,
            "forecast_irr": forecast_irr,
            "solargis_gti": sg_gti,
            "solargis_ghi": sg_ghi,
            "sg_vs_actual_pct": sg_vs_actual,
            "irr_variance_pct": irr_var,
            "actual_gen": actual_gen,
            "forecast_gen": forecast_gen,
            "gen_variance_pct": gen_var,
            "kwh_per_kwp": r["kwh_per_kwp"] if r["kwh_per_kwp"] == r["kwh_per_kwp"] else None,
            "actual_pr": pr,
            "availability": avail,
        })

    return rows


# ── Orchestrator ─────────────────────────────────────────────────────────

def sync_irradiance_to_notion(*, dry_run: bool = False) -> dict[str, int]:
    """Main entry point: sync solar_data irradiance rows to Notion.

    Returns dict with counts: created, updated, skipped, total.
    """
    settings = get_settings()
    token = settings.notion_integration_token
    parent_page = settings.notion_page_id

    if not token:
        print("ERROR: NOTION_INTEGRATION_TOKEN not set")
        return {"error": "no token"}
    if not parent_page:
        print("ERROR: NOTION_PAGE_ID not set")
        return {"error": "no parent page"}

    # 1. Load data from DuckDB
    print("Loading irradiance data from DuckDB...")
    rows = load_irradiance_data()
    print(f"  {len(rows)} rows across {len(set(r['Site'] for r in rows))} sites")

    if not rows:
        print("  No data to sync.")
        return {"total": 0, "created": 0, "updated": 0, "skipped": 0}

    if dry_run:
        print("\n[DRY RUN] Would sync these rows:")
        for r in rows:
            irr = f"{r['actual_irr']:.1f}" if r["actual_irr"] else "N/A"
            print(f"  {r['Site']:40s} {r['Month']:8s}  kWp={r['kWp']:<10}  Irr={irr} kWh/m²")
        return {"total": len(rows), "created": 0, "updated": 0, "skipped": 0}

    # 2. Find or create Notion database
    db_id = settings.notion_irradiance_database_id
    if db_id:
        print(f"Using configured DB: {db_id}")
    else:
        print("Searching for existing Notion database...")
        db_id = find_database(token)

    if not db_id:
        print("Creating new Notion database...")
        db_id = create_database(token, parent_page)
        # Persist the new DB ID to .env for future runs
        _append_env("NOTION_IRRADIANCE_DATABASE_ID", db_id)
        print(f"  Saved DB ID to .env")
    else:
        # Ensure schema is up to date (adds any new columns like SolarGIS)
        ensure_schema(token, db_id)
        _append_env("NOTION_IRRADIANCE_DATABASE_ID", db_id)
        print(f"  Saved DB ID to .env")

    # 3. Build index of existing rows
    print("Indexing existing Notion rows...")
    existing = query_existing_rows(token, db_id)
    print(f"  {len(existing)} existing rows")

    # 4. Upsert each row
    created = 0
    updated = 0
    skipped = 0

    for i, row in enumerate(rows, 1):
        key = (row["Site"], row["Month"])
        page_id = existing.get(key)

        action = "update" if page_id else "create"
        try:
            upsert_page(token, db_id, page_id, row)
            if page_id:
                updated += 1
            else:
                created += 1
            irr_str = f"{row['actual_irr']:.1f}" if row["actual_irr"] else "N/A"
            print(f"  [{i}/{len(rows)}] {action:6s} {row['Site']:40s} {row['Month']:8s}  Irr={irr_str}")
        except Exception as exc:
            print(f"  [{i}/{len(rows)}] FAILED {row['Site']} {row['Month']}: {exc}")
            skipped += 1

        # Light rate-limit: Notion allows ~3 req/s
        if i % 3 == 0:
            time.sleep(0.4)

    result = {"total": len(rows), "created": created, "updated": updated, "skipped": skipped}
    print(f"\nDone: {created} created, {updated} updated, {skipped} skipped")
    return result


def _append_env(key: str, value: str) -> None:
    """Append a key=value to the local .env file."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    with open(env_path, "a") as f:
        f.write(f"\n{key}={value}\n")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync monthly irradiance data to Notion")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Notion")
    args = parser.parse_args()

    result = sync_irradiance_to_notion(dry_run=args.dry_run)
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
