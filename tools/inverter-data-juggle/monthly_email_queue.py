"""
Monthly Email Queue Page Generator (Notion)
==========================================

Builds a monthly portfolio summary from the existing "Meter / inverter comparison"
Notion database and creates (or updates) a single page in the "Energy Monthly Email Queue"
database with Status="Ready to send" (or another configured status).

This is designed to work with a downstream Notion automation that:
  - polls for pages where Status == "Ready to send"
  - sends the email using Recipients, Subject, and Body
  - flips Status to "Sent"
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


# Support both env var names used across this repo/tooling.
NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_INTEGRATION_TOKEN") or ""

# Default DB lookup strings (can be overridden with args/env vars).
DEFAULT_COMPARISON_DB_TITLE = "Meter / inverter comparison"
DEFAULT_EMAIL_QUEUE_DB_TITLE = "Energy Monthly Email Queue"


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
    """
    Find a Notion database by exact title match via /v1/search.
    """
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


def month_range(target_month: Optional[str]) -> Tuple[date, date]:
    """
    Return (month_start, month_end) for YYYY-MM.
    If target_month is None, use previous month in SYNC_TIMEZONE.
    """
    if target_month:
        year_s, month_s = target_month.split("-", 1)
        year = int(year_s)
        month = int(month_s)
        start = date(year, month, 1)
    else:
        today = _today_in_sync_timezone()
        first = date(today.year, today.month, 1)
        prev_end = first - timedelta(days=1)
        start = date(prev_end.year, prev_end.month, 1)

    _, last_day = calendar.monthrange(start.year, start.month)
    end = date(start.year, start.month, last_day)
    return start, end


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


def query_comparison_pages(
    comparison_db_id: str,
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
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


def load_sites_list() -> List[str]:
    path = os.path.join(os.path.dirname(__file__), "sites_mapping.json")
    try:
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data.keys())
    except FileNotFoundError:
        raise SystemExit(f"sites_mapping.json not found at {path}")


def build_monthly_stats(
    sites: List[str],
    pages: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Returns:
      - totals per site: {site: {inv_kwh, meter_kwh, portal_kwh, diff_frac}}
      - representative page URL per site (latest date in range)
    """
    totals: Dict[str, Dict[str, Any]] = {s: {"inv_kwh": 0.0, "meter_kwh": 0.0, "portal_kwh": 0.0} for s in sites}
    latest: Dict[str, Tuple[str, str]] = {}  # site -> (date_str, page_id)

    for page in pages:
        site = _extract_title(page, "Site")
        if not site:
            continue
        if site not in totals:
            # Keep going; the database may contain rows for sites not in mapping.
            totals[site] = {"inv_kwh": 0.0, "meter_kwh": 0.0, "portal_kwh": 0.0}

        dt = _extract_date(page, "Date")
        inv = _extract_number(page, "Juggle Inv (Daily)")
        meter = _extract_number(page, "Juggle Meter (Daily)")
        portal = _extract_number(page, "Platform (Daily)")

        totals[site]["inv_kwh"] += inv
        totals[site]["meter_kwh"] += meter
        totals[site]["portal_kwh"] += portal

        pid = page.get("id") or ""
        if dt and pid:
            prev = latest.get(site)
            if not prev or dt > prev[0]:
                latest[site] = (dt, pid)

    page_urls: Dict[str, str] = {site: _notion_page_url(pid) for site, (_, pid) in latest.items()}

    for site, t in totals.items():
        inv = float(t.get("inv_kwh") or 0.0)
        meter = float(t.get("meter_kwh") or 0.0)
        diff = (inv - meter) / meter if meter > 0 else 0.0
        t["diff_frac"] = diff

    return totals, page_urls


def build_email_subject(run_type: str, month_start: date) -> str:
    month_name = calendar.month_name[month_start.month]
    base = f"Monthly Solar Portfolio Summary - {month_name} {month_start.year}"
    if run_type.upper() == "TEST":
        return f"[TEST] {base}"
    return base


def _table_html(
    rows: List[Tuple[str, float, float, float, float, str]],
) -> str:
    """Build a professionally styled HTML table for email rendering."""
    parts: List[str] = []
    parts.append(
        '<table style="border-collapse:collapse;width:100%;font-family:Arial,Helvetica,sans-serif;font-size:13px;margin:12px 0;">'
    )
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
        site_cell = (
            f'<a href="{url}" style="color:#2563eb;text-decoration:none;">{site}</a>'
            if url else site
        )
        portal_cell = f"{portal_kwh:,.1f}" if portal_kwh > 0 else "\u2014"
        if meter_kwh > 0 and inv_kwh > 0:
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


def build_email_body(
    run_type: str,
    month_start: date,
    month_end: date,
    synced_sites: int,
    inverter_only_sites: int,
    no_comparison_sites: int,
    site_errors: int,
    top_outliers: List[Tuple[str, float, str]],
    site_rows: List[Tuple[str, float, float, float, float, str]],
    *,
    omitted_no_data_sites: int = 0,
) -> str:
    """
    Build a professionally formatted HTML email body.

    Body is stored as rich_text in Notion; downstream automation treats it
    as HTML.  All styles are inlined for maximum email-client compatibility.
    """
    month_name = calendar.month_name[month_start.month]
    total_sites = synced_sites + inverter_only_sites + no_comparison_sites + site_errors

    # Outlier list
    outlier_items: List[str] = []
    for site, diff, link in top_outliers:
        pct = diff * 100.0
        colour = "#dc2626" if abs(pct) > 5.0 else ("#f59e0b" if abs(pct) > 2.0 else "#16a34a")
        site_label = (
            f'<a href="{link}" style="color:#2563eb;text-decoration:none;">{site}</a>'
            if link else site
        )
        outlier_items.append(
            f'<li style="margin:3px 0;">{site_label}: '
            f'<span style="color:{colour};font-weight:600;">{pct:+.1f}%</span></li>'
        )
    outlier_html = (
        f'<ul style="margin:6px 0 6px 20px;padding:0;">{"".join(outlier_items)}</ul>'
        if outlier_items else '<p style="color:#6b7280;font-style:italic;">No outlier data available.</p>'
    )

    # Table
    table_html = _table_html(site_rows) if site_rows else (
        '<p style="color:#6b7280;font-style:italic;">No sites with data for this month.</p>'
    )

    # Omission note
    omission = ""
    if omitted_no_data_sites:
        omission = (
            f'<p style="font-size:12px;color:#6b7280;margin:4px 0 12px;">'
            f'({omitted_no_data_sites} site{"s" if omitted_no_data_sites != 1 else ""} '
            f'omitted — no meter/inverter/portal data for the month)</p>'
        )

    # Test banner
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
  Monthly Solar Portfolio Summary &mdash; {month_name} {month_start.year}
</h2>
<p style="color:#6b7280;font-size:13px;margin:0 0 14px;">
  Reporting period: {month_start.isoformat()} to {month_end.isoformat()}
</p>

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Top {len(top_outliers)} Outliers by Absolute % Deviation (Inv vs Meter)</h3>
{outlier_html}

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Monthly Totals by Site</h3>
{omission}\
{table_html}

<h3 style="color:#374151;font-size:15px;margin:18px 0 4px;">Coverage</h3>
<table style="font-family:Arial,Helvetica,sans-serif;font-size:13px;border-collapse:collapse;margin-bottom:16px;">
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Synced Sites</td><td style="font-weight:600;">{synced_sites} / {total_sites}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Inverter-only Sites</td><td style="font-weight:600;">{inverter_only_sites}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">No-comparison Sites</td><td style="font-weight:600;">{no_comparison_sites}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#6b7280;">Site Errors</td><td style="font-weight:600;{' color:#dc2626;' if site_errors > 0 else ''}">{site_errors}</td></tr>
</table>

<p style="margin:16px 0 0;font-size:12px;color:#9ca3af;">
  Thanks,<br>Solar Platform Bot
</p>
</div>"""
    return html


def _rich_text(value: str) -> Dict[str, Any]:
    """
    Notion has a ~2000 char limit per text object; chunk large strings.
    """
    value = value or ""
    chunks = [value[i : i + 2000] for i in range(0, len(value), 2000)] or [""]
    return {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]}


def create_or_update_queue_page(
    queue_db_id: str,
    *,
    name: str,
    run_type: str,
    status: str,
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
    """
    Returns the page id.
    """
    headers = _notion_headers()

    # Try to find an existing page for this month+run_type+name.
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
        "Status": {"select": {"name": status}},
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a Notion monthly email queue page.")
    p.add_argument("--run-type", choices=["PROD", "TEST"], default="TEST")
    p.add_argument("--month", help="Target month YYYY-MM. Defaults to previous month in SYNC_TIMEZONE.")
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--recipients", help="Comma-separated email recipients. Falls back to env MONTHLY_EMAIL_RECIPIENTS.")
    p.add_argument("--comparison-db-id", help="Meter/inverter comparison database ID. Falls back to env NOTION_DB_ID.")
    p.add_argument("--queue-db-id", help="Email queue database ID. Falls back to env NOTION_EMAIL_QUEUE_DB_ID.")
    p.add_argument("--overwrite-existing", action="store_true", help="Update existing page if present.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    month_start, month_end = month_range(args.month)
    ym = f"{month_start.year:04d}-{month_start.month:02d}"

    run_type = args.run_type.upper()
    # Always set to "Ready to send" so the downstream automation picks it up.
    status = "Ready to send"

    comparison_db_id = _normalize_uuid(args.comparison_db_id or _env("NOTION_DB_ID", ""))
    if not comparison_db_id:
        comparison_db_id = search_database_id(DEFAULT_COMPARISON_DB_TITLE)

    queue_db_id = _normalize_uuid(args.queue_db_id or _env("NOTION_EMAIL_QUEUE_DB_ID", ""))
    if not queue_db_id:
        queue_db_id = search_database_id(DEFAULT_EMAIL_QUEUE_DB_TITLE)

    recipients = (args.recipients or _env("MONTHLY_EMAIL_RECIPIENTS", "")).strip()
    if not recipients:
        raise SystemExit("Missing recipients. Provide --recipients or env MONTHLY_EMAIL_RECIPIENTS.")

    sites = load_sites_list()
    pages = query_comparison_pages(comparison_db_id, month_start, month_end)
    totals, page_urls = build_monthly_stats(sites, pages)

    synced = 0
    inverter_only = 0
    no_comparison = 0
    site_errors = 0  # Reserved for future: pulling from APIs; currently summarizing Notion DB only.

    outlier_candidates: List[Tuple[float, str, float, str]] = []
    site_rows_all: List[Tuple[str, float, float, float, float, str]] = []
    for site in sites:
        t = totals.get(site) or {"inv_kwh": 0.0, "meter_kwh": 0.0, "portal_kwh": 0.0, "diff_frac": 0.0}
        inv = float(t.get("inv_kwh") or 0.0)
        meter = float(t.get("meter_kwh") or 0.0)
        portal = float(t.get("portal_kwh") or 0.0)
        diff = float(t.get("diff_frac") or 0.0)
        url = page_urls.get(site, "")

        site_rows_all.append((site, meter, inv, portal, diff, url))

        if inv > 0 and meter > 0:
            synced += 1
            outlier_candidates.append((abs(diff), site, diff, url))
        elif inv > 0 and meter == 0:
            inverter_only += 1
        else:
            no_comparison += 1

    # Filter the rendered table to only rows with any non-zero data.
    site_rows = [r for r in site_rows_all if (r[1] > 0 or r[2] > 0 or r[3] > 0)]
    omitted_no_data_sites = len(site_rows_all) - len(site_rows)
    site_rows.sort(key=lambda x: x[0])
    print(f"Monthly table rows included: {len(site_rows)} (of {len(site_rows_all)} mapped sites); omitted={omitted_no_data_sites}")

    outlier_candidates.sort(reverse=True)
    top = outlier_candidates[: max(0, int(args.top_n))]
    top_outliers = [(site, diff, link) for _, site, diff, link in top]

    subject = build_email_subject(run_type, month_start)
    body = build_email_body(
        run_type,
        month_start,
        month_end,
        synced_sites=synced,
        inverter_only_sites=inverter_only,
        no_comparison_sites=no_comparison,
        site_errors=site_errors,
        top_outliers=top_outliers,
        site_rows=site_rows,
        omitted_no_data_sites=omitted_no_data_sites,
    )

    name = f"{run_type} Monthly Summary {ym}"
    page_id = create_or_update_queue_page(
        queue_db_id,
        name=name,
        run_type=run_type,
        status=status,
        month_start=month_start,
        range_start=month_start,
        range_end=month_end,
        subject=subject,
        body=body,
        recipients=recipients,
        synced_sites=synced,
        inverter_only_sites=inverter_only,
        no_comparison_sites=no_comparison,
        site_errors=site_errors,
        overwrite_existing=args.overwrite_existing,
    )

    print(f"Queued monthly email page: {name}")
    if page_id:
        print(f"Page URL: {_notion_page_url(page_id)}")


if __name__ == "__main__":
    main()
