"""
Daily Email Queue Page Generator (Notion)
========================================

Creates a daily portfolio summary page in the same Notion email queue database
as the monthly runs ("Energy Monthly Email Queue").

The queued page always uses Status="Ready to send" so downstream automation
can pick it up immediately.

Content:
- Previous-day table (per-site): Juggle Meter, Juggle Inverter, Inverter Portal, % Diff
- Month-to-date table (through previous day): same columns
"""

from __future__ import annotations

import argparse
import calendar
import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


def _env(key: str, default: str) -> str:
    val = os.environ.get(key)
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    return val


SYNC_TIMEZONE = _env("SYNC_TIMEZONE", "Europe/London")


def _today_in_sync_timezone() -> date:
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo(SYNC_TIMEZONE)).date()
        except Exception:
            return date.today()
    return date.today()


NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_INTEGRATION_TOKEN") or ""

# Default DB lookup strings (can be overridden with args/env vars).
DEFAULT_COMPARISON_DB_TITLE = "Meter / inverter comparison"
DEFAULT_EMAIL_QUEUE_DB_TITLE = "Energy Monthly Email Queue"


def _normalize_uuid(raw: str) -> str:
    raw = (raw or "").strip()
    raw = raw.replace("-", "")
    if len(raw) != 32:
        return raw
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


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
                method=method,
                url=url,
                headers=headers,
                json=json_payload,
                timeout=timeout_s,
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


def _extract_title(page: Dict[str, Any], prop: str) -> str:
    props = page.get("properties", {})
    title_arr = props.get(prop, {}).get("title", [])
    if not title_arr:
        return ""
    return title_arr[0].get("plain_text") or title_arr[0].get("text", {}).get("content", "")


def _extract_date(page: Dict[str, Any], prop: str) -> str:
    props = page.get("properties", {})
    dt_obj = props.get(prop, {}).get("date") or {}
    return (dt_obj or {}).get("start") or ""


def _extract_number(page: Dict[str, Any], prop: str) -> float:
    try:
        props = page.get("properties", {})
        n = props.get(prop, {}).get("number")
        return float(n) if n is not None else 0.0
    except Exception:
        return 0.0


def _notion_page_url(page_id: str) -> str:
    pid = (page_id or "").replace("-", "")
    if not pid:
        return ""
    return f"https://www.notion.so/{pid}"


def query_comparison_pages_for_date(comparison_db_id: str, day: date) -> List[Dict[str, Any]]:
    url = f"https://api.notion.com/v1/databases/{comparison_db_id}/query"
    payload: Dict[str, Any] = {
        "filter": {"property": "Date", "date": {"equals": day.isoformat()}},
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


def load_sites_list() -> List[str]:
    path = os.path.join(os.path.dirname(__file__), "sites_mapping.json")
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data.keys())
    except FileNotFoundError:
        raise SystemExit(f"sites_mapping.json not found at {path}")


def _rich_text(value: str) -> Dict[str, Any]:
    value = value or ""
    chunks = [value[i : i + 2000] for i in range(0, len(value), 2000)] or [""]
    return {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]}


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
                {"property": "Month", "date": {"equals": month_start.isoformat()}},
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
        print(f"Queue page already exists for {name} (Run Type={run_type}). Skipping update.")
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


def build_subject(run_type: str, report_day: date) -> str:
    base = f"Daily Solar Portfolio Summary - {report_day.isoformat()}"
    return f"[TEST] {base}" if run_type.upper() == "TEST" else base


def _table_html(rows: List[Tuple[str, float, float, float, Optional[float], str]]) -> str:
    """Build a professionally styled HTML table for email rendering."""
    parts: List[str] = []
    parts.append(
        '<table style="border-collapse:collapse;width:100%;font-family:Arial,Helvetica,sans-serif;font-size:13px;margin:12px 0;">'
    )
    # Header row
    parts.append("<thead>")
    parts.append(
        '<tr style="background-color:#1a3a5c;color:#ffffff;text-align:left;">'
    )
    for hdr in ("Site", "Juggle Meter (kWh)", "Juggle Inverter (kWh)",
                "Inverter Portal (kWh)", "% Diff (Inv vs Meter)"):
        parts.append(
            f'<th style="padding:8px 10px;border:1px solid #dfe3e8;font-weight:600;">{hdr}</th>'
        )
    parts.append("</tr></thead><tbody>")
    for idx, (site, meter_kwh, inv_kwh, portal_kwh, diff_frac, url) in enumerate(rows):
        bg = "#f8f9fb" if idx % 2 == 0 else "#ffffff"
        site_cell = f'<a href="{url}" style="color:#2563eb;text-decoration:none;">{site}</a>' if url else site
        portal_cell = f"{portal_kwh:,.1f}" if portal_kwh > 0 else "\u2014"
        if diff_frac is not None:
            pct = diff_frac * 100.0
            colour = "#dc2626" if abs(pct) > 5.0 else ("#f59e0b" if abs(pct) > 2.0 else "#16a34a")
            diff_cell = f'<span style="color:{colour};font-weight:600;">{pct:+.1f}%</span>'
        else:
            diff_cell = "\u2014"
        td = f'style="padding:7px 10px;border:1px solid #e5e7eb;background:{bg};"'
        parts.append("<tr>")
        parts.append(f"<td {td}>{site_cell}</td>")
        parts.append(f'<td {td} style="padding:7px 10px;border:1px solid #e5e7eb;background:{bg};text-align:right;">{meter_kwh:,.1f}</td>')
        parts.append(f'<td {td} style="padding:7px 10px;border:1px solid #e5e7eb;background:{bg};text-align:right;">{inv_kwh:,.1f}</td>')
        parts.append(f'<td {td} style="padding:7px 10px;border:1px solid #e5e7eb;background:{bg};text-align:right;">{portal_cell}</td>')
        parts.append(f'<td {td} style="padding:7px 10px;border:1px solid #e5e7eb;background:{bg};text-align:center;">{diff_cell}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def build_body(
    run_type: str,
    report_day: date,
    month_start: date,
    synced_daily: int,
    inverter_only_daily: int,
    no_comp_daily: int,
    site_errors: int,
    daily_rows: List[Tuple[str, float, float, float, Optional[float], str]],
    mtd_rows: List[Tuple[str, float, float, float, Optional[float], str]],
) -> str:
    month_name = calendar.month_name[month_start.month]
    total_sites = synced_daily + inverter_only_daily + no_comp_daily + site_errors

    daily_table = _table_html(daily_rows) if daily_rows else (
        '<p style="color:#6b7280;font-style:italic;">No sites with data for previous day.</p>'
    )
    mtd_table = _table_html(mtd_rows) if mtd_rows else (
        '<p style="color:#6b7280;font-style:italic;">No sites with data for month-to-date.</p>'
    )

    test_banner = ""
    if run_type.upper() == "TEST":
        test_banner = (
            '<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;'
            'padding:10px 14px;margin-bottom:16px;font-size:13px;color:#92400e;">'
            "\u26a0\ufe0f <strong>TEST DRAFT</strong> \u2014 Do not forward to production recipients."
            "</div>"
        )

    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;color:#1f2937;max-width:800px;margin:0 auto;line-height:1.5;">
{test_banner}\
<p style="margin:0 0 4px;">Hi team,</p>

<h2 style="color:#1a3a5c;font-size:18px;margin:20px 0 6px;border-bottom:2px solid #e5e7eb;padding-bottom:6px;">
  Daily Solar Portfolio Summary &mdash; {report_day.isoformat()}
</h2>

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Previous Day (per-site)</h3>
{daily_table}

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Month-to-Date: {month_name} {month_start.year} ({month_start.isoformat()} to {report_day.isoformat()})</h3>
{mtd_table}

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Coverage</h3>
<table style="font-family:Arial,Helvetica,sans-serif;font-size:13px;border-collapse:collapse;margin-bottom:16px;">
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Synced Sites (daily)</td><td style="font-weight:600;">{synced_daily} / {total_sites}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Inverter-only Sites</td><td style="font-weight:600;">{inverter_only_daily}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">No-comparison Sites</td><td style="font-weight:600;">{no_comp_daily}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Site Errors</td><td style="font-weight:600;{' color:#dc2626;' if site_errors > 0 else ''}">{site_errors}</td></tr>
</table>

<p style="margin:16px 0 0;font-size:12px;color:#9ca3af;">
  Thanks,<br>Solar Platform Bot
</p>
</div>"""
    return html


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a Notion daily email queue page.")
    p.add_argument("--run-type", choices=["PROD", "TEST"], default="TEST")
    p.add_argument("--date", help="Report date (YYYY-MM-DD). Defaults to previous day in SYNC_TIMEZONE.")
    p.add_argument("--recipients", help="Comma-separated recipients. Falls back to env DAILY_EMAIL_RECIPIENTS then MONTHLY_EMAIL_RECIPIENTS.")
    p.add_argument("--comparison-db-id", help="Meter/inverter comparison database ID. Falls back to env NOTION_DB_ID.")
    p.add_argument("--queue-db-id", help="Email queue database ID. Falls back to env NOTION_EMAIL_QUEUE_DB_ID.")
    p.add_argument("--overwrite-existing", action="store_true", help="Update existing page if present.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.date:
        report_day = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        report_day = _today_in_sync_timezone() - timedelta(days=1)

    month_start = date(report_day.year, report_day.month, 1)
    run_type = args.run_type.upper()

    comparison_db_id = _normalize_uuid(args.comparison_db_id or _env("NOTION_DB_ID", ""))
    if not comparison_db_id:
        comparison_db_id = search_database_id(DEFAULT_COMPARISON_DB_TITLE)

    queue_db_id = _normalize_uuid(args.queue_db_id or _env("NOTION_EMAIL_QUEUE_DB_ID", ""))
    if not queue_db_id:
        queue_db_id = search_database_id(DEFAULT_EMAIL_QUEUE_DB_TITLE)

    recipients = (args.recipients or _env("DAILY_EMAIL_RECIPIENTS", "")).strip()
    if not recipients:
        recipients = _env("MONTHLY_EMAIL_RECIPIENTS", "").strip()
    if not recipients:
        raise SystemExit("Missing recipients. Provide --recipients or env DAILY_EMAIL_RECIPIENTS/MONTHLY_EMAIL_RECIPIENTS.")

    sites = load_sites_list()
    pages = query_comparison_pages_for_date(comparison_db_id, report_day)

    by_site: Dict[str, Dict[str, Any]] = {}
    for page in pages:
        site = _extract_title(page, "Site")
        if not site:
            continue
        by_site[site] = {
            "url": _notion_page_url(page.get("id") or ""),
            "meter_d": _extract_number(page, "Juggle Meter (Daily)"),
            "inv_d": _extract_number(page, "Juggle Inv (Daily)"),
            "portal_d": _extract_number(page, "Platform (Daily)"),
            "meter_m": _extract_number(page, "Juggle Meter (MTD)"),
            "inv_m": _extract_number(page, "Juggle Inv (MTD)"),
            "portal_m": _extract_number(page, "Platform (MTD)"),
        }

    synced = 0
    inverter_only = 0
    no_comparison = 0
    site_errors = 0

    daily_rows_all: List[Tuple[str, float, float, float, Optional[float], str]] = []
    mtd_rows_all: List[Tuple[str, float, float, float, Optional[float], str]] = []

    for site in sites:
        r = by_site.get(site)
        if not r:
            # No Notion row for this site/day (omit from table; still count for coverage).
            no_comparison += 1
            continue

        meter_d = float(r["meter_d"])
        inv_d = float(r["inv_d"])
        portal_d = float(r["portal_d"])
        meter_m = float(r["meter_m"])
        inv_m = float(r["inv_m"])
        portal_m = float(r["portal_m"])
        url = str(r["url"] or "")

        diff_d = (inv_d - meter_d) / meter_d if (meter_d > 0 and inv_d > 0) else None
        diff_m = (inv_m - meter_m) / meter_m if (meter_m > 0 and inv_m > 0) else None

        daily_rows_all.append((site, meter_d, inv_d, portal_d, diff_d, url))
        mtd_rows_all.append((site, meter_m, inv_m, portal_m, diff_m, url))

        if meter_d > 0 and inv_d > 0:
            synced += 1
        elif inv_d > 0 and meter_d == 0:
            inverter_only += 1
        else:
            no_comparison += 1

    # Filter tables to only sites with any meaningful data to avoid giant 0.0 tables.
    daily_rows = [r for r in daily_rows_all if (r[1] > 0 or r[2] > 0 or r[3] > 0)]
    mtd_rows = [r for r in mtd_rows_all if (r[1] > 0 or r[2] > 0 or r[3] > 0)]
    daily_rows.sort(key=lambda x: x[0])
    mtd_rows.sort(key=lambda x: x[0])

    print(f"Daily table rows included: {len(daily_rows)} (of {len(daily_rows_all)} sites with Notion rows)")
    print(f"MTD table rows included: {len(mtd_rows)} (of {len(mtd_rows_all)} sites with Notion rows)")

    subject = build_subject(run_type, report_day)
    body = build_body(
        run_type,
        report_day,
        month_start,
        synced_daily=synced,
        inverter_only_daily=inverter_only,
        no_comp_daily=no_comparison,
        site_errors=site_errors,
        daily_rows=daily_rows,
        mtd_rows=mtd_rows,
    )

    name = f"{run_type} Daily Summary {report_day.isoformat()}"
    page_id = create_or_update_queue_page(
        queue_db_id,
        name=name,
        run_type=run_type,
        month_start=month_start,
        range_start=report_day,
        range_end=report_day,
        subject=subject,
        body=body,
        recipients=recipients,
        synced_sites=synced,
        inverter_only_sites=inverter_only,
        no_comparison_sites=no_comparison,
        site_errors=site_errors,
        overwrite_existing=args.overwrite_existing,
    )

    print(f"Queued daily email page: {name}")
    if page_id:
        print(f"Page URL: {_notion_page_url(page_id)}")


if __name__ == "__main__":
    main()
