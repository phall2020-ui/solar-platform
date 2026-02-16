"""Sync newly onboarded sites into O&M contracts and monthly billing rows."""

from __future__ import annotations

import argparse
import os
import time
from calendar import monthrange
from collections.abc import Iterator
from datetime import date
from typing import Any

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Notion API expects database IDs (page IDs), not collection:// data-source IDs.
DEFAULT_ONBOARDING_DB_ID = "bd47f0ec-8aa7-4f45-9908-accdf882e4eb"
DEFAULT_OM_CONTRACTS_DB_ID = "7dc7ccc4-5c5a-43d7-a75b-2e97818089dc"
DEFAULT_OM_BILLING_DB_ID = "39212e37-c38b-4c79-b1cd-8e54c976f7ea"

CONTRACT_TERM_YEARS_FIELDS = (
    "Contract Term (Years)",
    "Contract Term Years",
    "Contract Years",
)

SPV_MAP: dict[str, str] = {
    "Olympus Solar 2 Ltd": "OS2",
    "Ultravolt SPV1 Limited": "UV1",
    "Eden Sustainable Investments 10 Ltd": "ESI10",
    "Fylde Solar Ltd": "FS",
    "Shawton Energy Point Lane Limited": "SE-PL",
    "Ampyr Distributed Energy 1 Ltd": "AD1",
    "Shawton Energy SPV Ltd": "SE-SPV",
    "Eden Sustainable Investments 8 Ltd": "ESI8",
}


def _env(key: str, default: str) -> str:
    val = os.environ.get(key)
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    return val


def _normalize_notion_id(raw: str) -> str:
    value = (raw or "").strip().replace("-", "")
    if len(value) != 32:
        return (raw or "").strip()
    return f"{value[0:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:32]}"


def notion_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_payload: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
    retries: int = 4,
    backoff_s: float = 1.5,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_payload,
                timeout=timeout_s,
            )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else backoff_s * (attempt + 1)
                time.sleep(sleep_s)
                continue
            if 500 <= response.status_code < 600:
                time.sleep(backoff_s * (attempt + 1))
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(backoff_s * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError(f"HTTP request failed after retries: {method} {url}")


class NotionClient:
    def __init__(self, token: str, *, retries: int = 4, timeout_s: float = 30.0) -> None:
        self._headers = notion_headers(token)
        self._retries = retries
        self._timeout_s = timeout_s

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{NOTION_API_BASE}{path}"
        response = request_with_retry(
            method,
            url,
            headers=self._headers,
            json_payload=payload,
            retries=self._retries,
            timeout_s=self._timeout_s,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Notion API failed ({method} {path}) status={response.status_code} body={response.text[:800]}"
            )
        return response.json()

    def get_database(self, database_id: str) -> dict[str, Any]:
        db_id = _normalize_notion_id(database_id)
        return self._request("GET", f"/databases/{db_id}")

    def get_page(self, page_id: str) -> dict[str, Any]:
        pid = _normalize_notion_id(page_id)
        return self._request("GET", f"/pages/{pid}")

    def query_database(
        self,
        database_id: str,
        *,
        filter_payload: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        db_id = _normalize_notion_id(database_id)
        payload: dict[str, Any] = {"page_size": page_size}
        if filter_payload is not None:
            payload["filter"] = filter_payload

        results: list[dict[str, Any]] = []
        while True:
            body = self._request("POST", f"/databases/{db_id}/query", payload=payload)
            results.extend(body.get("results", []))
            if not body.get("has_more"):
                break
            next_cursor = body.get("next_cursor")
            if not next_cursor:
                break
            payload["start_cursor"] = next_cursor
        return results

    def create_page(self, database_id: str, properties: dict[str, Any]) -> str:
        db_id = _normalize_notion_id(database_id)
        body = self._request(
            "POST",
            "/pages",
            payload={"parent": {"database_id": db_id}, "properties": properties},
        )
        return str(body.get("id") or "")

    def update_page(self, page_id: str, properties: dict[str, Any]) -> None:
        pid = _normalize_notion_id(page_id)
        self._request("PATCH", f"/pages/{pid}", payload={"properties": properties})


def _extract_title(props: dict[str, Any], prop_name: str) -> str:
    title_items = props.get(prop_name, {}).get("title", [])
    if not title_items:
        return ""
    item = title_items[0]
    return str(item.get("plain_text") or item.get("text", {}).get("content") or "").strip()


def _extract_number(props: dict[str, Any], prop_name: str, default: float = 0.0) -> float:
    value = props.get(prop_name, {}).get("number")
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _extract_rich_text(props: dict[str, Any], prop_name: str) -> list[dict[str, Any]]:
    value = props.get(prop_name, {}).get("rich_text")
    if isinstance(value, list):
        return value
    return []


def _extract_select_name(props: dict[str, Any], prop_name: str) -> str | None:
    select_obj = props.get(prop_name, {}).get("select")
    if not isinstance(select_obj, dict):
        return None
    name = select_obj.get("name")
    if not isinstance(name, str):
        return None
    return name.strip() or None


def _extract_relation(props: dict[str, Any], prop_name: str) -> list[dict[str, str]]:
    relations = props.get(prop_name, {}).get("relation") or []
    out: list[dict[str, str]] = []
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        rel_id = rel.get("id")
        if isinstance(rel_id, str) and rel_id.strip():
            out.append({"id": rel_id})
    return out


def _extract_contract_term(props: dict[str, Any], *, fallback_start: str = "") -> tuple[str, str]:
    term = props.get("Contract Term", {}).get("date") or {}
    start = str(term.get("start") or "").strip()
    end = str(term.get("end") or "").strip()
    if start and end:
        return start, end
    if start:
        return start, start
    if end:
        return end, end
    if fallback_start:
        return fallback_start, fallback_start
    today = date.today().isoformat()
    return today, today


def _extract_status_name(props: dict[str, Any], prop_name: str) -> str:
    status_obj = props.get(prop_name, {}).get("status")
    if not isinstance(status_obj, dict):
        return ""
    name = status_obj.get("name")
    if not isinstance(name, str):
        return ""
    return name.strip()


def _extract_positive_int_number(props: dict[str, Any], prop_names: tuple[str, ...]) -> int:
    for prop_name in prop_names:
        value = props.get(prop_name, {}).get("number")
        try:
            if value is None:
                continue
            number = int(float(value))
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0


def _add_years(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        # Handle leap day rollover by moving to Feb 28 in non-leap years.
        return start.replace(year=start.year + years, month=2, day=28)


def get_unlinked_sites(
    notion: NotionClient,
    onboarding_db_id: str,
    *,
    onboarded_status: str = "",
) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = [
        {
            "property": "Portfolio Contract",
            "relation": {"is_empty": True},
        }
    ]
    if onboarded_status:
        filters.insert(
            0,
            {
                "property": "Onboarding Status",
                "status": {"equals": onboarded_status},
            },
        )

    return notion.query_database(
        onboarding_db_id,
        filter_payload={
            "and": filters
        },
    )


def build_contract_properties(
    site_props: dict[str, Any],
    *,
    provider_name: str = "ClearSol",
    spv_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str, str, str, str | None]:
    mapping = spv_map or SPV_MAP

    site_name = _extract_title(site_props, "Site Name")
    if not site_name:
        raise ValueError("Site Name is missing")

    system_size = _extract_number(site_props, "System Size (kWp)")
    variable_rate = _extract_number(site_props, "Variable Rate (£/kWp)")
    cctv_cost = _extract_number(site_props, "CCTV Cost (£/yr)")
    cleaning_cost = _extract_number(site_props, "Cleaning Cost (£/yr)")
    onboard_date = str(site_props.get("Onboard Date", {}).get("date", {}).get("start") or "").strip()
    contract_start, contract_end = _extract_contract_term(site_props, fallback_start=onboard_date)
    term_years = _extract_positive_int_number(site_props, CONTRACT_TERM_YEARS_FIELDS)
    if onboard_date and term_years > 0:
        start_date = date.fromisoformat(onboard_date)
        contract_start = onboard_date
        contract_end = _add_years(start_date, term_years).isoformat()
    contract_notes = _extract_rich_text(site_props, "Contract Notes")

    spv_full = _extract_select_name(site_props, "SPV")
    spv_short = mapping.get(spv_full) if spv_full else None

    pm_days = _extract_number(site_props, "PM Days")
    pm_day_rate = _extract_number(site_props, "PM Day Rate (£)")
    pm_cost = round(pm_days * pm_day_rate, 2)

    asset_link = _extract_relation(site_props, "Asset Register Link")

    properties: dict[str, Any] = {
        "Site Name": {"title": [{"text": {"content": site_name}}]},
        "System Size (kWp)": {"number": system_size},
        "O&M Provider": {"select": {"name": provider_name}},
        "Contract Status": {"status": {"name": "Active"}},
        "Variable Rate (£/kWp)": {"number": variable_rate},
        "PM Cost (£/yr)": {"number": pm_cost},
        "CCTV Cost (£/yr)": {"number": cctv_cost},
        "Cleaning Cost (£/yr)": {"number": cleaning_cost},
        "Rate Tier <20MW": {"number": 2.00},
        "Rate Tier 20-30MW": {"number": 1.80},
        "Rate Tier 30-40MW": {"number": 1.70},
        "Contract Notes": {"rich_text": contract_notes},
    }

    if onboard_date:
        properties["Onboard Date"] = {"date": {"start": onboard_date}}
    if spv_short:
        properties["SPV"] = {"select": {"name": spv_short}}
    if asset_link:
        properties["Asset Register Link"] = {"relation": asset_link}

    return properties, site_name, contract_start, contract_end, spv_short


def create_om_contract(
    notion: NotionClient,
    om_contracts_db_id: str,
    site_props: dict[str, Any],
    *,
    provider_name: str,
    dry_run: bool,
) -> tuple[str, str, str, str, str | None]:
    properties, site_name, contract_start, contract_end, spv_short = build_contract_properties(
        site_props,
        provider_name=provider_name,
    )

    if dry_run:
        return "dry-run-contract-id", site_name, contract_start, contract_end, spv_short

    contract_id = notion.create_page(om_contracts_db_id, properties)
    return contract_id, site_name, contract_start, contract_end, spv_short


def set_onboarded_status_if_onboard_date(
    notion: NotionClient,
    *,
    site_id: str,
    site_props: dict[str, Any],
    dry_run: bool,
) -> None:
    onboard_date = str(site_props.get("Onboard Date", {}).get("date", {}).get("start") or "").strip()
    if not onboard_date:
        return

    current_status = _extract_status_name(site_props, "Onboarding Status")
    if current_status == "Onboarded":
        return

    if dry_run:
        print("  dry-run: would set Onboarding Status -> Onboarded")
        return

    notion.update_page(
        site_id,
        properties={
            "Onboarding Status": {
                "status": {"name": "Onboarded"},
            }
        },
    )
    print("  updated Onboarding Status -> Onboarded")


def last_day(year: int, month: int) -> str:
    return f"{year}-{month:02d}-{monthrange(year, month)[1]:02d}"


def pro_rata_factor(year: int, month: int, contract_start: date, contract_end: date) -> float:
    days_in_month = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    effective_start = max(month_start, contract_start)
    effective_end = min(month_end, contract_end)
    active_days = (effective_end - effective_start).days + 1

    if active_days <= 0:
        return 0.0
    if active_days >= days_in_month:
        return 1.0
    return round(active_days / days_in_month, 2)


def months_in_range(start: date, end: date) -> Iterator[tuple[int, int]]:
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def build_billing_properties(
    *,
    contract_page_id: str,
    site_name: str,
    year: int,
    month: int,
    contract_start: date,
    contract_end: date,
    spv_short: str | None,
    provider_name: str,
    default_tier: str,
) -> dict[str, Any]:
    month_name = date(year, month, 1).strftime("%B %Y")
    entry_title = f"{site_name} - {month_name}"
    factor = pro_rata_factor(year, month, contract_start, contract_end)

    properties: dict[str, Any] = {
        "Billing Entry": {"title": [{"text": {"content": entry_title}}]},
        "O&M Contract": {"relation": [{"id": contract_page_id}]},
        "O&M Provider": {"select": {"name": provider_name}},
        "Applied Tier": {"select": {"name": default_tier}},
        "Payment Status": {"status": {"name": "Due"}},
        "Pro-rata Factor": {"number": factor},
        "Billing Period": {
            "date": {
                "start": f"{year}-{month:02d}-01",
                "end": last_day(year, month),
            }
        },
    }

    if spv_short:
        properties["SPV"] = {"select": {"name": spv_short}}

    return properties


def create_billing_entries(
    notion: NotionClient,
    om_billing_db_id: str,
    *,
    contract_page_id: str,
    site_name: str,
    spv_short: str | None,
    contract_start_str: str,
    contract_end_str: str,
    provider_name: str,
    default_tier: str,
    dry_run: bool,
) -> int:
    contract_start = date.fromisoformat(contract_start_str)
    contract_end = date.fromisoformat(contract_end_str)
    if contract_end < contract_start:
        raise ValueError(f"Contract Term end before start ({contract_start_str} -> {contract_end_str})")

    created = 0
    for year, month in months_in_range(contract_start, contract_end):
        properties = build_billing_properties(
            contract_page_id=contract_page_id,
            site_name=site_name,
            year=year,
            month=month,
            contract_start=contract_start,
            contract_end=contract_end,
            spv_short=spv_short,
            provider_name=provider_name,
            default_tier=default_tier,
        )

        if not dry_run:
            notion.create_page(om_billing_db_id, properties)

        created += 1
        factor = properties["Pro-rata Factor"]["number"]
        print(f"    created billing row {year}-{month:02d} (pro-rata={factor})")

    return created


def link_contract_to_onboarding(
    notion: NotionClient,
    onboarding_page_id: str,
    contract_page_id: str,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    notion.update_page(
        onboarding_page_id,
        properties={
            "Portfolio Contract": {
                "relation": [{"id": contract_page_id}],
            }
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create O&M contracts + billing entries from unlinked onboarding sites."
    )
    parser.add_argument(
        "--onboarding-db-id",
        default=_env("ONBOARDING_DB_ID", DEFAULT_ONBOARDING_DB_ID),
        help="Site Onboarding Portal database ID",
    )
    parser.add_argument(
        "--om-contracts-db-id",
        default=_env("OM_CONTRACTS_DB_ID", DEFAULT_OM_CONTRACTS_DB_ID),
        help="O&M Contracts database ID",
    )
    parser.add_argument(
        "--om-billing-db-id",
        default=_env("OM_BILLING_DB_ID", DEFAULT_OM_BILLING_DB_ID),
        help="O&M Billing database ID",
    )
    parser.add_argument(
        "--provider",
        default=_env("OM_PROVIDER", "ClearSol"),
        help="O&M provider name to set on created rows",
    )
    parser.add_argument(
        "--default-tier",
        default=_env("DEFAULT_TIER", "Tier 2 (20-30MW)"),
        help="Applied Tier for new billing rows",
    )
    parser.add_argument(
        "--onboarded-status",
        default=_env("ONBOARDED_STATUS", ""),
        help="Optional status filter. Leave empty to process any status.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of sites to process in this run",
    )
    parser.add_argument(
        "--page-id",
        default=_env("ONBOARDING_PAGE_ID", ""),
        help="Optional onboarding page ID to process (useful for webhook events)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without writing to Notion",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_INTEGRATION_TOKEN") or ""
    if not token:
        print("Missing NOTION_TOKEN (or NOTION_INTEGRATION_TOKEN)")
        return 1

    notion = NotionClient(token)

    for db_id in (args.onboarding_db_id, args.om_contracts_db_id, args.om_billing_db_id):
        notion.get_database(db_id)

    sites: list[dict[str, Any]]
    if args.page_id:
        page = notion.get_page(args.page_id)
        props = page.get("properties", {})
        has_contract_link = bool(_extract_relation(props, "Portfolio Contract"))
        if has_contract_link:
            print("Webhook page already linked to a portfolio contract; nothing to process.")
            return 0
        sites = [page]
    else:
        sites = get_unlinked_sites(
            notion,
            args.onboarding_db_id,
            onboarded_status=args.onboarded_status,
        )

    if args.limit > 0:
        sites = sites[: args.limit]

    if not sites:
        print("No new sites to process.")
        return 0

    if args.onboarded_status:
        print(
            f"Found {len(sites)} site(s) with status '{args.onboarded_status}' without a portfolio contract."
        )
    else:
        print(f"Found {len(sites)} site(s) without a portfolio contract.")

    processed = 0
    skipped = 0
    failed = 0
    total_billing_rows = 0

    for site in sites:
        site_id = str(site.get("id") or "")
        props = site.get("properties", {})
        site_name = _extract_title(props, "Site Name") or f"<unknown:{site_id[:8]}>"

        print(f"\nProcessing {site_name}")

        try:
            set_onboarded_status_if_onboard_date(
                notion,
                site_id=site_id,
                site_props=props,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            failed += 1
            print(f"  failed setting Onboarding Status: {exc}")
            continue

        try:
            contract_id, resolved_site_name, contract_start, contract_end, spv_short = create_om_contract(
                notion,
                args.om_contracts_db_id,
                props,
                provider_name=args.provider,
                dry_run=args.dry_run,
            )
        except ValueError as exc:
            skipped += 1
            print(f"  skipped: {exc}")
            continue
        except Exception as exc:
            failed += 1
            print(f"  failed creating contract: {exc}")
            continue

        if args.dry_run:
            print("  dry-run: would create O&M Contract")
        else:
            print(f"  created O&M Contract {contract_id}")

        try:
            billing_count = create_billing_entries(
                notion,
                args.om_billing_db_id,
                contract_page_id=contract_id,
                site_name=resolved_site_name,
                spv_short=spv_short,
                contract_start_str=contract_start,
                contract_end_str=contract_end,
                provider_name=args.provider,
                default_tier=args.default_tier,
                dry_run=args.dry_run,
            )
            total_billing_rows += billing_count
        except Exception as exc:
            failed += 1
            print(f"  failed creating billing rows: {exc}")
            continue

        try:
            link_contract_to_onboarding(
                notion,
                site_id,
                contract_id,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            failed += 1
            print(f"  failed linking contract back to onboarding: {exc}")
            continue

        if args.dry_run:
            print("  dry-run: would link Portfolio Contract relation")
        else:
            print("  linked contract back to onboarding page")

        processed += 1

    print("\nDone")
    print(f"  processed: {processed}")
    print(f"  skipped:   {skipped}")
    print(f"  failed:    {failed}")
    print(f"  billing rows created: {total_billing_rows}")

    if failed > 0:
        return 1
    return 0


def main() -> int:
    args = parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
