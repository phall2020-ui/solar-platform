"""
Weekly Email Queue Page Generator (Notion)
==========================================

Creates a weekly portfolio alert summary page in the "Energy Monthly Email Queue"
Notion database.  Runs every Monday at 04:00 UK time and covers the previous
Mon-Sun period.

**Only queues an email when at least one Warning/Critical/Meter-Only/Inverter-Only
alert exists in the week.**  If every site is OK for every day there's nothing to
report and no email is queued.

Content (plain text):
- Per-site, per-day alert lines for any day with a non-OK Alert (Daily) value
- Coverage stats
"""

from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


# ---------------------------------------------------------------------------
# Helpers / Config
# ---------------------------------------------------------------------------

def _env(key: str, default: str) -> str:
    val = os.environ.get(key)
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    return val


SYNC_TIMEZONE = _env("SYNC_TIMEZONE", "Europe/London")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_INTEGRATION_TOKEN") or ""

DEFAULT_COMPARISON_DB_TITLE = "Meter / inverter comparison"
DEFAULT_EMAIL_QUEUE_DB_TITLE = "Energy Monthly Email Queue"

# Alert threshold — must match notion_sync.py compute_daily_alert.
ALERT_CRITICAL_PCT = 5.0


def _today_in_sync_timezone() -> date:
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo(SYNC_TIMEZONE)).date()
        except Exception:
            return date.today()
    return date.today()


def _previous_week_range(ref_date: date) -> Tuple[date, date]:
    """Return (monday, sunday) of the week **before** *ref_date*.

    *ref_date* is expected to be a Monday (the day the job runs).
    """
    monday = ref_date - timedelta(days=ref_date.weekday())  # this Monday
    prev_monday = monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _normalize_uuid(raw: str) -> str:
    raw = (raw or "").strip().replace("-", "")
    if len(raw) != 32:
        return raw
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


# ---------------------------------------------------------------------------
# Notion helpers
# ---------------------------------------------------------------------------

def _notion_headers() -> Dict[str, str]:
    if not NOTION_TOKEN:
        raise SystemExit("Missing NOTION_TOKEN (or NOTION_INTEGRATION_TOKEN)")
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    json_payload: Optional[dict] = None,
    timeout_s: float = 30.0,
    retries: int = 3,
    backoff_s: float = 1.5,
) -> requests.Response:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = requests.request(
                method=method, url=url, headers=headers,
                json=json_payload, timeout=timeout_s,
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


def search_database_id(title: str) -> str:
    url = "https://api.notion.com/v1/search"
    payload = {"query": title, "filter": {"value": "database", "property": "object"}, "page_size": 20}
    resp = request_with_retry("POST", url, headers=_notion_headers(), json_payload=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Notion search failed: {resp.status_code}: {resp.text[:500]}")
    for db in resp.json().get("results", []):
        db_title = "".join([t.get("plain_text", "") for t in db.get("title", [])])
        if db_title.strip() == title.strip():
            return db.get("id") or ""
    raise SystemExit(f"Could not find Notion database titled {title!r}. Provide --*-db-id.")


def _notion_page_url(page_id: str) -> str:
    pid = (page_id or "").replace("-", "")
    return f"https://www.notion.so/{pid}" if pid else ""


# ---------------------------------------------------------------------------
# Query the comparison DB
# ---------------------------------------------------------------------------

def _extract_title(page: Dict[str, Any], prop: str) -> str:
    arr = page.get("properties", {}).get(prop, {}).get("title", [])
    if not arr:
        return ""
    return arr[0].get("plain_text") or arr[0].get("text", {}).get("content", "")


def _extract_date(page: Dict[str, Any], prop: str) -> str:
    dt_obj = page.get("properties", {}).get(prop, {}).get("date") or {}
    return (dt_obj or {}).get("start") or ""


def _extract_number(page: Dict[str, Any], prop: str) -> float:
    try:
        n = page.get("properties", {}).get(prop, {}).get("number")
        return float(n) if n is not None else 0.0
    except Exception:
        return 0.0


def _extract_select(page: Dict[str, Any], prop: str) -> str:
    sel = page.get("properties", {}).get(prop, {}).get("select")
    if isinstance(sel, dict):
        return sel.get("name") or ""
    return ""


def query_comparison_pages_for_range(
    comparison_db_id: str, start: date, end: date,
) -> List[Dict[str, Any]]:
    """Paginated Notion DB query for all rows between *start* and *end* inclusive."""
    url = f"https://api.notion.com/v1/databases/{comparison_db_id}/query"
    payload: Dict[str, Any] = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after": start.isoformat()}},
                {"property": "Date", "date": {"on_or_before": end.isoformat()}},
            ]
        },
        "page_size": 100,
    }
    out: List[Dict[str, Any]] = []
    while True:
        resp = request_with_retry("POST", url, headers=_notion_headers(), json_payload=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Notion DB query failed: {resp.status_code}: {resp.text[:1000]}")
        data = resp.json()
        out.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data.get("next_cursor")
    return out


# ---------------------------------------------------------------------------
# Alert computation (mirrors notion_sync.compute_daily_alert)
# ---------------------------------------------------------------------------

def _compute_alert(inv: float, meter: float) -> str:
    """Recompute alert from raw numbers (fallback when Alert column is empty)."""
    has_inv = inv > 0
    has_meter = meter > 0
    if has_meter and not has_inv:
        return "Meter Only"
    if has_inv and not has_meter:
        return "Inverter Only"
    if not has_inv and not has_meter:
        return "OK"
    diff = abs((inv - meter) / meter) * 100.0
    if diff > ALERT_CRITICAL_PCT:
        return "Critical"
    return "OK"


def _is_alert(label: str) -> bool:
    """True for any non-OK alert label."""
    return label not in ("OK", "")


# ---------------------------------------------------------------------------
# Build the email body
# ---------------------------------------------------------------------------

def build_subject(run_type: str, week_start: date, week_end: date) -> str:
    base = f"Weekly Solar Portfolio Alerts - {week_start.isoformat()} to {week_end.isoformat()}"
    return f"[TEST] {base}" if run_type.upper() == "TEST" else base


def build_body(
    run_type: str,
    week_start: date,
    week_end: date,
    # { site: [(day_iso, alert_label, inv_kwh, meter_kwh, diff_pct_str), ...] }
    site_alerts: Dict[str, List[Tuple[str, str, float, float, str]]],
    synced_sites: int,
    inverter_only_sites: int,
    no_comparison_sites: int,
    site_errors: int,
) -> str:
    total = synced_sites + inverter_only_sites + no_comparison_sites + site_errors
    lines: List[str] = []

    if run_type.upper() == "TEST":
        lines.append("[TEST DRAFT] Do not forward to production recipients.")
        lines.append("")

    lines.append("Hi team,")
    lines.append("")
    lines.append(f"Weekly Solar Portfolio Alerts - {week_start.isoformat()} to {week_end.isoformat()}")
    lines.append("")

    # Group by site, sorted alphabetically
    for site in sorted(site_alerts):
        day_lines = site_alerts[site]
        if not day_lines:
            continue
        lines.append(f"{site}")
        for day_iso, label, inv, meter, diff_str in sorted(day_lines, key=lambda x: x[0]):
            lines.append(f"  {day_iso} [{label}] Inv: {inv:,.1f} kWh | Meter: {meter:,.1f} kWh | {diff_str}")
        lines.append("")

    lines.append("Coverage")
    lines.append(f"- Synced Sites: {synced_sites} / {total}")
    lines.append(f"- Inverter-only Sites: {inverter_only_sites}")
    lines.append(f"- No-comparison Sites: {no_comparison_sites}")
    lines.append(f"- Site Errors: {site_errors}")
    lines.append("")
    lines.append("Thanks,")
    lines.append("Solar Platform Bot")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Notion queue page helpers
# ---------------------------------------------------------------------------

def _rich_text(value: str) -> Dict[str, Any]:
    value = value or ""
    chunks = [value[i : i + 2000] for i in range(0, len(value), 2000)] or [""]
    return {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]}


def load_sites_list() -> List[str]:
    import json as _json
    path = os.path.join(os.path.dirname(__file__), "sites_mapping.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return list(data.keys())
    except FileNotFoundError:
        raise SystemExit(f"sites_mapping.json not found at {path}")


def create_or_update_queue_page(
    queue_db_id: str,
    *,
    name: str,
    run_type: str,
    month_start: date,
    range_start: date,
    range_end: date,
    subject: str,
    body: str,
    recipients: str,
    synced_sites: int,
    inverter_only_sites: int,
    no_comparison_sites: int,
    site_errors: int,
    overwrite_existing: bool,
) -> str:
    headers = _notion_headers()
    query_url = f"https://api.notion.com/v1/databases/{queue_db_id}/query"
    query_payload = {
        "filter": {
            "and": [
                {"property": "Name", "title": {"equals": name}},
                {"property": "Run Type", "select": {"equals": run_type}},
            ]
        },
        "page_size": 1,
    }
    q = request_with_retry("POST", query_url, headers=headers, json_payload=query_payload)
    if q.status_code != 200:
        raise RuntimeError(f"Notion queue DB query failed: {q.status_code}: {q.text[:1000]}")

    existing = (q.json().get("results") or [])
    existing_id = existing[0].get("id") if existing else None

    props: Dict[str, Any] = {
        "Name": {"title": [{"type": "text", "text": {"content": name}}]},
        "Run Type": {"select": {"name": run_type}},
        "Status": {"select": {"name": "Ready to send"}},
        "Month": {"date": {"start": month_start.isoformat()}},
        "Range Start": {"date": {"start": range_start.isoformat()}},
        "Range End": {"date": {"start": range_end.isoformat()}},
        "Subject": _rich_text(subject),
        "Body": _rich_text(body),
        "Recipients": _rich_text(recipients),
        "Synced Sites": {"number": int(synced_sites)},
        "Inverter-only Sites": {"number": int(inverter_only_sites)},
        "No-comparison Sites": {"number": int(no_comparison_sites)},
        "Site Errors": {"number": int(site_errors)},
    }

    if existing_id and not overwrite_existing:
        print(f"Queue page already exists for {name!r}. Skipping update.")
        return existing_id

    if existing_id:
        url = f"https://api.notion.com/v1/pages/{existing_id}"
        resp = request_with_retry("PATCH", url, headers=headers, json_payload={"properties": props}, retries=4)
        if resp.status_code != 200:
            raise RuntimeError(f"Notion page update failed: {resp.status_code}: {resp.text[:1000]}")
        return existing_id

    create_url = "https://api.notion.com/v1/pages"
    payload = {"parent": {"database_id": queue_db_id}, "properties": props}
    resp = request_with_retry("POST", create_url, headers=headers, json_payload=payload, retries=4)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Notion page create failed: {resp.status_code}: {resp.text[:1000]}")
    return resp.json().get("id") or ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a Notion weekly alert email queue page.")
    p.add_argument("--run-type", choices=["PROD", "TEST"], default="TEST")
    p.add_argument(
        "--week-start",
        help="Monday of the target week (YYYY-MM-DD). Defaults to previous Monday.",
    )
    p.add_argument(
        "--recipients",
        help="Comma-separated recipients. Falls back to env WEEKLY_EMAIL_RECIPIENTS, "
             "DAILY_EMAIL_RECIPIENTS, then MONTHLY_EMAIL_RECIPIENTS.",
    )
    p.add_argument("--comparison-db-id", help="Meter/inverter comparison DB ID.")
    p.add_argument("--queue-db-id", help="Email queue DB ID.")
    p.add_argument("--overwrite-existing", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_type = args.run_type.upper()

    # Determine week range
    if args.week_start:
        week_monday = datetime.strptime(args.week_start, "%Y-%m-%d").date()
        week_sunday = week_monday + timedelta(days=6)
    else:
        today = _today_in_sync_timezone()
        week_monday, week_sunday = _previous_week_range(today)

    month_start = date(week_monday.year, week_monday.month, 1)

    print(f"Weekly alert email for {week_monday.isoformat()} to {week_sunday.isoformat()}")

    # Resolve DB IDs
    comparison_db_id = _normalize_uuid(args.comparison_db_id or _env("NOTION_DB_ID", ""))
    if not comparison_db_id:
        comparison_db_id = search_database_id(DEFAULT_COMPARISON_DB_TITLE)

    queue_db_id = _normalize_uuid(args.queue_db_id or _env("NOTION_EMAIL_QUEUE_DB_ID", ""))
    if not queue_db_id:
        queue_db_id = search_database_id(DEFAULT_EMAIL_QUEUE_DB_TITLE)

    # Recipients
    recipients = (args.recipients or "").strip()
    if not recipients:
        recipients = _env("WEEKLY_EMAIL_RECIPIENTS", "").strip()
    if not recipients:
        recipients = _env("DAILY_EMAIL_RECIPIENTS", "").strip()
    if not recipients:
        recipients = _env("MONTHLY_EMAIL_RECIPIENTS", "").strip()
    if not recipients:
        raise SystemExit(
            "Missing recipients. Provide --recipients or env "
            "WEEKLY_EMAIL_RECIPIENTS / DAILY_EMAIL_RECIPIENTS / MONTHLY_EMAIL_RECIPIENTS."
        )

    sites = load_sites_list()
    pages = query_comparison_pages_for_range(comparison_db_id, week_monday, week_sunday)
    print(f"Fetched {len(pages)} Notion rows for the week.")

    # Build per-site alert map
    # site_alerts: { site_name: [(day_iso, alert_label, inv, meter, diff_str), ...] }
    site_alerts: Dict[str, List[Tuple[str, str, float, float, str]]] = defaultdict(list)
    seen_sites: set = set()

    for page in pages:
        site = _extract_title(page, "Site")
        day_iso = _extract_date(page, "Date")
        if not site or not day_iso:
            continue
        seen_sites.add(site)

        inv = _extract_number(page, "Juggle Inv (Daily)")
        meter = _extract_number(page, "Juggle Meter (Daily)")

        # Prefer the stored Alert column; fall back to recomputing.
        alert_label = _extract_select(page, "Alert (Daily)")
        if not alert_label:
            alert_label = _compute_alert(inv, meter)

        if not _is_alert(alert_label):
            continue

        if meter > 0 and inv > 0:
            diff_pct = (inv - meter) / meter * 100.0
            diff_str = f"Diff: {diff_pct:+.1f}%"
        elif meter > 0 and inv == 0:
            diff_str = "No inverter reading"
        elif inv > 0 and meter == 0:
            diff_str = "No meter reading"
        else:
            diff_str = "No data"

        site_alerts[site].append((day_iso, alert_label, inv, meter, diff_str))

    # Coverage counts
    synced = 0
    inverter_only = 0
    no_comparison = 0
    site_errors = 0
    for site in sites:
        if site in seen_sites:
            synced += 1
        else:
            no_comparison += 1

    total_alert_days = sum(len(v) for v in site_alerts.values())

    # ── Gate: only send if there are alerts ──
    if total_alert_days == 0:
        print("No alerts for the week. Skipping email queue page creation.")
        return

    print(f"Alerts found for {len(site_alerts)} site(s) across {total_alert_days} site-days.")

    subject = build_subject(run_type, week_monday, week_sunday)
    body = build_body(
        run_type,
        week_monday,
        week_sunday,
        site_alerts=dict(site_alerts),
        synced_sites=synced,
        inverter_only_sites=inverter_only,
        no_comparison_sites=no_comparison,
        site_errors=site_errors,
    )

    name = f"{run_type} Weekly Alerts {week_monday.isoformat()}"
    page_id = create_or_update_queue_page(
        queue_db_id,
        name=name,
        run_type=run_type,
        month_start=month_start,
        range_start=week_monday,
        range_end=week_sunday,
        subject=subject,
        body=body,
        recipients=recipients,
        synced_sites=synced,
        inverter_only_sites=inverter_only,
        no_comparison_sites=no_comparison,
        site_errors=site_errors,
        overwrite_existing=args.overwrite_existing,
    )

    print(f"Queued weekly email page: {name}")
    if page_id:
        print(f"Page URL: {_notion_page_url(page_id)}")


if __name__ == "__main__":
    main()
