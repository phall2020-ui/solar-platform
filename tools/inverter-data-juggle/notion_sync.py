"""
Notion Sync Tool for Energy Data
================================
Daily sync of Juggle & Inverter Platform (Solis, SolarEdge) data to Notion.
- Fetches full month-to-date data for all sites.
- Calculates Daily & Cumulative MTD totals for each day.
- Updates/Creates rows in Notion "Energy Comparison Portfolio" database.
- uses EXACT matching for User/Site names.
- Designed to run daily via GitHub Actions.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

# Ensure imports work
sys.path.insert(0, '.')
from fetch_inverter_data import BASE_URL, Config, fetch_all_readings
from solis_api import list_stations, get_station_month
import solaredge_api

# Configuration
JUGGLE_API_KEY = os.environ.get('JUGGLE_API_KEY')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_PAGE_ID = os.environ.get('NOTION_PAGE_ID')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')
REQUEST_TIMEOUT_S = float(os.environ.get("SYNC_REQUEST_TIMEOUT_S", "30"))
SYNC_TIMEZONE = os.environ.get("SYNC_TIMEZONE", "Europe/London")
SYNC_LAG_DAYS = int(os.environ.get("SYNC_LAG_DAYS", "1"))

# Load SolarEdge Keys
SOLAREDGE_KEYS_JSON = os.environ.get('SOLAREDGE_KEYS_JSON', '{}')
try:
    SOLAREDGE_KEYS = json.loads(SOLAREDGE_KEYS_JSON)
except json.JSONDecodeError:
    print("Warning: SOLAREDGE_KEYS_JSON is not valid JSON.")
    SOLAREDGE_KEYS = {}

def val(x):
    return x.get('value') if isinstance(x, dict) else x

def get_days_in_month_until_yesterday():
    # Use a stable timezone so scheduled jobs are consistent year-round.
    if ZoneInfo:
        try:
            today = datetime.now(ZoneInfo(SYNC_TIMEZONE)).date()
        except Exception:
            today = date.today()
    else:
        today = date.today()

    yesterday = today - timedelta(days=max(1, SYNC_LAG_DAYS))
    
    year = yesterday.year
    month = yesterday.month
    
    num_days = yesterday.day
    days = []
    for d in range(1, num_days + 1):
        dt = date(year, month, d)
        days.append(dt.strftime("%Y-%m-%d"))
    return days

def request_with_retry(method: str, url: str, *, headers=None, params=None, json_payload=None,
                       timeout: float = REQUEST_TIMEOUT_S, retries: int = 3,
                       backoff_s: float = 1.5) -> requests.Response:
    """
    HTTP helper with retry and timeout protection.
    Retries transient network errors, 429, and 5xx responses.
    """
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_payload,
                timeout=timeout,
            )
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else backoff_s * (attempt + 1)
                time.sleep(sleep_s)
                continue
            if 500 <= resp.status_code < 600:
                time.sleep(backoff_s * (attempt + 1))
                continue
            return resp
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(backoff_s * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError(f"HTTP request failed after retries: {method} {url}")

def get_juggle_monthly_data(plant_uid, emig_id, start_date, end_date):
    if not JUGGLE_API_KEY:
        return {}
        
    cfg = Config(api_key=JUGGLE_API_KEY, plant_uid=plant_uid, start_date=start_date.replace("-", ""), end_date=end_date.replace("-", ""), min_interval_s=1800)
    try:
        readings = fetch_all_readings(cfg, emig_id)
    except Exception as e:
        return {}

    if not readings: return {}

    daily_map = {}
    grouped = {}
    for r in readings:
        ts = r.get('ts') or r.get('timestamp')
        if not ts: continue
        
        val_ = val(r.get('importEnergy'))
        if val_ is None: val_ = val(r.get('exportEnergy'))
        if val_ is None: continue
        
        dt_str = ts.split("T")[0]
        if dt_str not in grouped: grouped[dt_str] = []
        grouped[dt_str].append(float(val_))
        
    for dt, vals in grouped.items():
        if vals:
            daily_kwh = (max(vals) - min(vals)) / 1000.0
            daily_map[dt] = daily_kwh
            
    return daily_map

def get_notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

def get_or_create_notion_db():
    headers = get_notion_headers()
    search_url = "https://api.notion.com/v1/search"
    search_payload = {"query": "Meter / inverter comparison", "filter": {"value": "database", "property": "object"}}

    resp = request_with_retry("POST", search_url, headers=headers, json_payload=search_payload)
    results = resp.json().get("results", [])
    
    for db in results:
        try:
            title_obj = db.get("title", [])
            if title_obj and title_obj[0].get("plain_text") == "Meter / inverter comparison":
                print(f"Found existing DB: {db['id']}")
                return db["id"]
        except: continue
    
    print("Creating new Notion database...")
    create_url = "https://api.notion.com/v1/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": NOTION_PAGE_ID},
        "title": [{"type": "text", "text": {"content": "Meter / inverter comparison"}}],
        "properties": {
            "Site": {"title": {}},
            "Date": {"date": {}},
            "Platform": {"select": {}}, 
            "Juggle Inv (Daily)": {"number": {"format": "number"}},
            "Juggle Meter (Daily)": {"number": {"format": "number"}},
            "Platform (Daily)": {"number": {"format": "number"}},
            "Diff (Daily) %": {"number": {"format": "percent"}},
            "Juggle Inv (MTD)": {"number": {"format": "number"}},
            "Juggle Meter (MTD)": {"number": {"format": "number"}},
            "Platform (MTD)": {"number": {"format": "number"}},
            "Diff (MTD) %": {"number": {"format": "percent"}}
        }
    }
    resp = request_with_retry("POST", create_url, headers=headers, json_payload=payload)
    if resp.status_code != 200:
        print(f"Error creating DB: {resp.text}")
        sys.exit(1)
    return resp.json()["id"]

def query_notion_page(db_id, site, date_str):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Site", "title": {"equals": site}},
                {"property": "Date", "date": {"equals": date_str}}
            ]
        }
    }
    resp = request_with_retry("POST", url, headers=get_notion_headers(), json_payload=payload)
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None

def _extract_site(page: Dict[str, Any]) -> str:
    props = page.get("properties", {})
    site_title = props.get("Site", {}).get("title", [])
    if not site_title:
        return ""
    # Prefer plain_text when available.
    return site_title[0].get("plain_text") or site_title[0].get("text", {}).get("content", "")

def _extract_date(page: Dict[str, Any]) -> str:
    props = page.get("properties", {})
    date_obj = props.get("Date", {}).get("date", {})
    return (date_obj or {}).get("start") or ""

def _safe_num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def build_row_fingerprint(platform: str, di: float, dp: float, ds: float,
                          mi: float, mp: float, ms: float) -> Tuple[Any, ...]:
    platform_norm = (platform or "").strip().lower()
    platform_name = platform if platform_norm in ("solis", "solaredge") else ""
    diff_d = (di - dp) / dp if dp > 0 else 0.0
    diff_m = (mi - mp) / mp if mp > 0 else 0.0
    return (
        platform_name,
        round(di, 2),
        round(dp, 2),
        round(ds, 2),
        round(diff_d, 4),
        round(mi, 2),
        round(mp, 2),
        round(ms, 2),
        round(diff_m, 4),
    )

def _page_fingerprint(page: Dict[str, Any]) -> Tuple[Any, ...]:
    props = page.get("properties", {})
    platform_sel = props.get("Platform", {}).get("select")
    platform_name = platform_sel.get("name") if isinstance(platform_sel, dict) else ""
    return (
        platform_name or "",
        round(_safe_num(props.get("Juggle Inv (Daily)", {}).get("number")), 2),
        round(_safe_num(props.get("Juggle Meter (Daily)", {}).get("number")), 2),
        round(_safe_num(props.get("Platform (Daily)", {}).get("number")), 2),
        round(_safe_num(props.get("Diff (Daily) %", {}).get("number")), 4),
        round(_safe_num(props.get("Juggle Inv (MTD)", {}).get("number")), 2),
        round(_safe_num(props.get("Juggle Meter (MTD)", {}).get("number")), 2),
        round(_safe_num(props.get("Platform (MTD)", {}).get("number")), 2),
        round(_safe_num(props.get("Diff (MTD) %", {}).get("number")), 4),
    )

def build_existing_page_index(db_id: str, start_date_str: str, end_date_str: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Load existing rows for target date range once to avoid per-row Notion queries.
    """
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after": start_date_str}},
                {"property": "Date", "date": {"on_or_before": end_date_str}},
            ]
        },
        "page_size": 100,
    }

    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    while True:
        resp = request_with_retry("POST", url, headers=get_notion_headers(), json_payload=payload)
        if resp.status_code != 200:
            print(f"Warning: failed to index existing Notion rows ({resp.status_code}).")
            return index

        data = resp.json()
        for page in data.get("results", []):
            site = _extract_site(page)
            dt = _extract_date(page)
            pid = page.get("id")
            if site and dt and pid:
                index[(site, dt)] = {"id": pid, "fingerprint": _page_fingerprint(page)}

        if not data.get("has_more"):
            break
        payload["start_cursor"] = data.get("next_cursor")

    return index

def load_sites_mapping():
    try:
        with open('sites_mapping.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("sites_mapping.json not found.")
        return {}

def fetch_platform_data(mapping_info, start_date, end_date):
    platform = mapping_info.get('platform')
    site_id = mapping_info.get('site_id')
    
    if platform == 'solaredge':
        api_key = SOLAREDGE_KEYS.get(str(site_id))
        if not api_key:
            print(f"  No SolarEdge API Key found for {site_id}")
            return {}
        return solaredge_api.get_energy(site_id, api_key, start_date, end_date)

    elif platform == 'solis':
        month_str = start_date[0:7] 
        try:
            resp = get_station_month(site_id, month_str)
            data = resp.get("data", [])
            result = {}
            for d in data:
                dt = d.get("dateStr")
                e = float(d.get("energy") or d.get("eToday") or 0.0)
                result[dt] = e
            return result
        except Exception as e:
            print(f"  Error fetching Solis data: {e}")
            return {}

    return {}

def sync_row(db_id, site, date_str, platform, di, dp, ds, mi, mp, ms, page_id=None):
    diff_d = (di - dp)/dp if dp > 0 else 0
    diff_m = (mi - mp)/mp if mp > 0 else 0
    
    props = {
        "Site": {"title": [{"text": {"content": site}}]},
        "Date": {"date": {"start": date_str}},
        "Juggle Inv (Daily)": {"number": round(di, 2)},
        "Juggle Meter (Daily)": {"number": round(dp, 2)},
        "Platform (Daily)": {"number": round(ds, 2)},
        "Diff (Daily) %": {"number": round(diff_d, 4)},
        "Juggle Inv (MTD)": {"number": round(mi, 2)},
        "Juggle Meter (MTD)": {"number": round(mp, 2)},
        "Platform (MTD)": {"number": round(ms, 2)},
        "Diff (MTD) %": {"number": round(diff_m, 4)}
    }

    # Keep Platform blank for Juggle-only entries.
    platform_norm = (platform or "").strip().lower()
    if platform_norm in ("solis", "solaredge"):
        props["Platform"] = {"select": {"name": platform}}
    
    # Retry logic
    for attempt in range(3):
        try:
            if page_id:
                url = f"https://api.notion.com/v1/pages/{page_id}"
                resp = request_with_retry(
                    "PATCH",
                    url,
                    headers=get_notion_headers(),
                    json_payload={"properties": props},
                    retries=4,
                )
            else:
                url = "https://api.notion.com/v1/pages"
                resp = request_with_retry(
                    "POST",
                    url,
                    headers=get_notion_headers(),
                    json_payload={"parent": {"database_id": db_id}, "properties": props},
                    retries=4,
                )
                
            if resp.status_code in [200, 201]:
                print(f"    Synced {date_str}: {site}")
                created_page_id = page_id
                if not created_page_id and resp.status_code == 200:
                    created_page_id = resp.json().get("id")
                if not created_page_id and resp.status_code == 201:
                    created_page_id = resp.json().get("id")
                return True, created_page_id
            else:
                print(f"    Notion Error {resp.status_code}: {resp.text}")
                return False, page_id
        except Exception as e:
            print(f"    Exception syncing {site} {date_str}: {e}")
            time.sleep(1.0)
    return False, page_id

def has_any_data(day_maps):
    """Return True if any daily-map in the list contains at least one day."""
    return any(bool(day_map) for day_map in day_maps)

def main():
    if not NOTION_TOKEN:
        print("Missing NOTION_TOKEN")
        sys.exit(1)
            
    mapping = load_sites_mapping()

    target_days = get_days_in_month_until_yesterday()
    if not target_days:
        print("No days to sync")
        return

    start_date_str = target_days[0]
    end_date_str = target_days[-1]
    
    print(f"Syncing data for range: {start_date_str} to {end_date_str}")
    
    if NOTION_DB_ID:
        print(f"Using provided DB ID: {NOTION_DB_ID}")
        db_id = NOTION_DB_ID
    else:
        db_id = get_or_create_notion_db()

    headers_juggle = {'Authorization': f'token {JUGGLE_API_KEY}'} if JUGGLE_API_KEY else {}
    existing_page_index = build_existing_page_index(db_id, start_date_str, end_date_str)
    print(f"Indexed existing Notion rows in range: {len(existing_page_index)}")

    synced_sites = 0
    skipped_no_juggle_mapping = []
    skipped_inverter_only = []
    skipped_no_comparison_data = []
    site_errors = []
    
    # Iterate ALL sites in mapping
    for name, info in mapping.items():
        uid = info.get('juggle_uid')
        platform = info.get('platform', 'Unknown')
        
        print(f"Processing {name} ({platform})...")

        # This workflow is for Juggle vs platform comparison.
        # Skip any site that has no Juggle plant UID.
        if not uid or uid == "?":
            skipped_no_juggle_mapping.append(name)
            print(f"  Skipping {name}: no Juggle mapping (juggle_uid is missing).")
            continue
        
        inv_ids = []
        pv_ids = []
        if JUGGLE_API_KEY:
            try:
                resp = request_with_retry(
                    "GET",
                    f"{BASE_URL}/plant/{uid}",
                    headers=headers_juggle,
                    timeout=20,
                    retries=3,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    devices = data.get('meters', [])
                    inv_ids = [d['emigId'] for d in devices if d.get('type') == 'INVERTER']
                    pv_ids = [d['emigId'] for d in devices if d.get('type') == 'PV']
                else:
                    site_errors.append(f"{name}: Juggle plant lookup failed for {uid} (HTTP {resp.status_code})")
                    print(f"  Warning: Juggle plant lookup failed for {uid} (HTTP {resp.status_code})")
            except Exception as e:
                site_errors.append(f"{name}: Juggle plant lookup exception for {uid}: {e}")
                print(f"  Warning: Juggle plant lookup exception for {uid}: {e}")

        inv_day_maps = []
        for i, eid in enumerate(inv_ids):
            data = get_juggle_monthly_data(uid, eid, start_date_str, end_date_str)
            inv_day_maps.append(data)

        pv_day_maps = []
        for i, eid in enumerate(pv_ids):
            data = get_juggle_monthly_data(uid, eid, start_date_str, end_date_str)
            pv_day_maps.append(data)

        platform_data = fetch_platform_data(info, start_date_str, end_date_str)

        # Skip sites where we only have inverter data and nothing else.
        # Requested behavior: do not include "inverter-only" sites in Notion.
        # Also skip sites with no usable comparison data at all.
        has_inv_data = has_any_data(inv_day_maps)
        has_pv_data = has_any_data(pv_day_maps)
        has_platform_data = bool(platform_data)
        if not has_pv_data and not has_platform_data:
            if has_inv_data:
                skipped_inverter_only.append(name)
                print(f"  Skipping {name}: inverter-only data (no Juggle meter data and no platform data).")
            else:
                skipped_no_comparison_data.append(name)
                print(f"  Skipping {name}: no PV meter/platform data available for comparison.")
            continue
        
        cum_inv = 0.0
        cum_pv = 0.0
        cum_platform = 0.0
        wrote_any_rows = False
        
        for day_str in target_days:
            d_inv = sum(m.get(day_str, 0.0) for m in inv_day_maps)
            d_pv = sum(m.get(day_str, 0.0) for m in pv_day_maps)
            d_platform = platform_data.get(day_str, 0.0)
            
            cum_inv += d_inv
            cum_pv += d_pv
            cum_platform += d_platform

            page_key = (name, day_str)
            existing_record = existing_page_index.get(page_key)
            new_fingerprint = build_row_fingerprint(
                platform,
                d_inv,
                d_pv,
                d_platform,
                cum_inv,
                cum_pv,
                cum_platform,
            )

            if existing_record and existing_record.get("fingerprint") == new_fingerprint:
                print(f"    Unchanged {day_str}: {name}")
                wrote_any_rows = True
                continue

            page_id = existing_record.get("id") if existing_record else None
            ok, new_page_id = sync_row(
                db_id,
                name,
                day_str,
                platform,
                d_inv,
                d_pv,
                d_platform,
                cum_inv,
                cum_pv,
                cum_platform,
                page_id=page_id,
            )
            if ok:
                existing_page_index[page_key] = {
                    "id": page_id or new_page_id,
                    "fingerprint": new_fingerprint,
                }
            wrote_any_rows = wrote_any_rows or ok

        if wrote_any_rows:
            synced_sites += 1

    print("Sync complete.")
    print(f"Summary: synced_sites={synced_sites}, skipped_no_juggle_mapping={len(skipped_no_juggle_mapping)}, skipped_inverter_only={len(skipped_inverter_only)}, skipped_no_comparison_data={len(skipped_no_comparison_data)}, site_errors={len(site_errors)}")
    if skipped_no_juggle_mapping:
        print("  No-Juggle-mapping skipped sites:")
        for site in skipped_no_juggle_mapping:
            print(f"    - {site}")
    if skipped_inverter_only:
        print("  Inverter-only skipped sites:")
        for site in skipped_inverter_only:
            print(f"    - {site}")
    if skipped_no_comparison_data:
        print("  No-comparison-data skipped sites:")
        for site in skipped_no_comparison_data:
            print(f"    - {site}")
    if site_errors:
        print("  Site errors:")
        for err in site_errors:
            print(f"    - {err}")

if __name__ == "__main__":
    main()
