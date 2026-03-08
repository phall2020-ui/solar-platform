"""Asset-register driven yesterday data audit for the performance copilot."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import inspect
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import requests

from solar_platform.config import get_settings
from solar_platform.db.repository import PlantRepository, ReadingsRepository
from solar_platform.integrations.notion_assets import NotionAssetRegisterService
from solar_platform.services.site_locations import SiteLocationService
from solar_platform.weather.open_meteo import OpenMeteoArchiveClient, OpenMeteoClient

logger = logging.getLogger(__name__)


SUPPORTED_SOURCES: tuple[str, ...] = (
    "juggle",
    "solaredge",
    "solis",
    "enphase",
    "huawei",
    "sma",
)

PAC_DATE_FIELD_CANDIDATES: tuple[str, ...] = (
    "PAC Date",
    "Pac Date",
    "PAC",
)

ASSET_NAME_FIELD_CANDIDATES: tuple[str, ...] = (
    "Alias",
    "Site",
    "Asset Name",
    "Name",
    "Project Name",
    "Title",
)

PLATFORM_FIELD_CANDIDATES: tuple[str, ...] = (
    "Platform",
    "Monitoring Platform",
    "Inverter Platform",
    "Data Source",
)

SOURCE_IDENTIFIER_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "juggle": ("Plant UID", "Juggle UID", "Juggle Plant UID"),
    "solaredge": ("SolarEdge Site ID", "SolarEdge ID", "SolarEdge Site"),
    "solis": ("Solis Station ID", "Solis Site ID", "Solis ID"),
    "enphase": ("Enphase System ID", "Enphase ID"),
    "huawei": ("Huawei Station ID", "Huawei Plant ID", "Huawei ID"),
    "sma": ("SMA Plant ID", "SMA Site ID", "SMA ID"),
}

DATA_SOURCE_MATCH_FIELD_CANDIDATES: tuple[str, ...] = ("Data Source Match",)

CAPACITY_FIELD_CANDIDATES: tuple[str, ...] = (
    "TIC kWp",
    "Installed Capacity",
    "Installed Capacity kWp",
    "Capacity kWp",
    "Capacity",
    "DC Size kWp",
    "kWp",
)

PPA_RATE_FIELD_CANDIDATES: tuple[str, ...] = (
    "PPA Rate",
    "PPA Rate (GBP/MWh)",
    "PPA Rate (£/MWh)",
    "PPA Rate (p/kWh)",
    "PPA Rate p/kWh",
    "PPA Tariff",
    "Tariff",
    "Tariff Rate",
    "Export Rate",
)

TARGET_PR_ASSUMPTION = 0.80

DEFAULT_DATA_SOURCE_MATCH_UPDATES: dict[str, str] = {
    "BAE Fylde": "Newfold Farm",
    "Bannatyne's Braintree": "PPA Bannatynes Braintree",
    "Bannatyne's Bury St Edmunds": "PPA Bannatynes Bury St Edmunds",
    "Bannatyne's Colchester Kingsford Park": "PPA Bannatynes Colchester Kingsford Park",
    "Bannatyne's Cookridge Hall": "PPA Bannatynes Cookridge Hall",
    "Bannatyne's Darlington": "PPA Bannatynes Darlington Head Office",
    "Bannatyne's Norwich": "PPA Bannatynes Norwich",
    "Bannatyne's Weybridge": "PPA Bannatynes Weybridge",
    "Bannatyne's Wildmoor": "PPA Bannatynes Wildmoor",
    "Blachford": "Blachford UK",
    "Dunham Forest Golf Club": "PPA Dunham Forest Golf Club",
    "Finlay Beverages": "Finlay Beverages",
    "I&N Fabrications": "PPA I&N Fabrications Ltd",
    "Panorama Kitchens": "PPA Panorama Kitchens",
    "Park Hall": "PPA Park Hall",
    "Shawton Engineering": "PPA Shawton Engineering Ltd",
    "Swift Dental Group": "PPA Swift Dental Group",
    "Uniroyal Global": "PPA Uniroyal Global",
    "Valley Hydraulics": "PPA Valley Hydraulics",
    "WALC Adult Learning Centre": "PPA WALC Adult Learning Centre",
    "WALC Leigh College": "PPA WALC Leigh College",
    "WALC Pagefield": "PPA WALC Pagefield",
    "Wienerberger Floplast": "FloPlast",
}

DEFAULT_CONFIRMED_SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "Newfold Farm": {"platform": "juggle", "site_id": "", "juggle_uid": "ERS:00001"},
    "FloPlast": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00032"},
    "Finlay Beverages": {
        "platform": "solis",
        "site_id": "1298491919450070492",
        "juggle_uid": "AMP:00031",
    },
    "Blachford UK": {
        "platform": "solaredge",
        "site_id": "4466155",
        "juggle_uid": "AMP:00024",
    },
    "PPA Park Hall": {"platform": "solaredge", "site_id": "4667531", "juggle_uid": "?"},
    "PPA Panorama Kitchens": {"platform": "solaredge", "site_id": "4519032", "juggle_uid": "?"},
    "PPA Shawton Engineering Ltd": {"platform": "solaredge", "site_id": "2798969", "juggle_uid": "?"},
    "PPA I&N Fabrications Ltd": {"platform": "solaredge", "site_id": "2688590", "juggle_uid": "?"},
    "PPA Swift Dental Group": {"platform": "solaredge", "site_id": "3656221", "juggle_uid": "?"},
    "PPA Uniroyal Global": {"platform": "solaredge", "site_id": "3933004", "juggle_uid": "?"},
    "PPA Valley Hydraulics": {"platform": "solaredge", "site_id": "2626861", "juggle_uid": "?"},
    "PPA WALC Adult Learning Centre": {"platform": "solaredge", "site_id": "3829329", "juggle_uid": "?"},
    "PPA WALC Leigh College": {"platform": "solaredge", "site_id": "3888537", "juggle_uid": "?"},
    "PPA WALC Pagefield": {"platform": "solaredge", "site_id": "3823337", "juggle_uid": "?"},
    "PPA Dunham Forest Golf Club": {"platform": "solaredge", "site_id": "3490228", "juggle_uid": "?"},
    "PPA Bannatynes Braintree": {"platform": "solaredge", "site_id": "4284090", "juggle_uid": "?"},
    "PPA Bannatynes Bury St Edmunds": {"platform": "solaredge", "site_id": "4309872", "juggle_uid": "?"},
    "PPA Bannatynes Colchester Kingsford Park": {"platform": "solaredge", "site_id": "4320553", "juggle_uid": "?"},
    "PPA Bannatynes Cookridge Hall": {"platform": "solaredge", "site_id": "4361798", "juggle_uid": "?"},
    "PPA Bannatynes Darlington Head Office": {"platform": "solaredge", "site_id": "4307544", "juggle_uid": "?"},
    "PPA Bannatynes Norwich": {"platform": "solaredge", "site_id": "4319038", "juggle_uid": "?"},
    "PPA Bannatynes Weybridge": {"platform": "solaredge", "site_id": "4283465", "juggle_uid": "?"},
    "PPA Bannatynes Wildmoor": {"platform": "solaredge", "site_id": "4338522", "juggle_uid": "?"},
}

TRIAGE_DATABASE_TITLE = "Solar Copilot Daily Triage"

DAILY_JSON_DATABASE_TITLE = "Daily JSON"
STARK_DAILY_DATABASE_TITLE = "Stark HH Daily Data"
STARK_FUSION_VARIANCE_THRESHOLD_PCT = 8.0
INVERTER_METER_ALERT_CRITICAL_PCT = 5.0
SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

TRIAGE_DATABASE_PROPERTIES: dict[str, dict[str, Any]] = {
    "Asset": {"title": {}},
    "Row Key": {"rich_text": {}},
    "Target Date": {"date": {}},
    "Issue Type": {"rich_text": {}},
    "Severity": {"rich_text": {}},
    "Confidence": {"number": {"format": "number"}},
    "Source Coverage": {"rich_text": {}},
    "Evidence Summary": {"rich_text": {}},
    "Recommended Action": {"rich_text": {}},
    "AM Email Subject": {"rich_text": {}},
    "AM Email Draft": {"rich_text": {}},
    "AM Contact": {"rich_text": {}},
    "AM Contact Email": {"email": {}},
    "Project Name": {"rich_text": {}},
    "Customer": {"rich_text": {}},
    "SPV": {"rich_text": {}},
    "Priority": {"rich_text": {}},
    "Asset Register URL": {"url": {}},
    "Preferred Source": {"rich_text": {}},
    "Match Method": {"rich_text": {}},
    "Has Any Data": {"checkbox": {}},
}

DAILY_JSON_DATABASE_PROPERTIES: dict[str, dict[str, Any]] = {
    "Asset": {"title": {}},
    "Row Key": {"rich_text": {}},
    "Target Date": {"date": {}},
    "PAC Date": {"date": {}},
    "PAC Phase": {"rich_text": {}},
    "PAC In Past": {"checkbox": {}},
    "PAC Date Missing": {"checkbox": {}},
    "Has Any Data": {"checkbox": {}},
    "Sources With Data": {"rich_text": {}},
    "Preferred Source": {"rich_text": {}},
    "Checked Sources": {"rich_text": {}},
    "Match Name": {"rich_text": {}},
    "Match Method": {"rich_text": {}},
    "Match Confidence": {"number": {"format": "number"}},
    "Resolved Source Types": {"rich_text": {}},
    "Resolution Notes": {"rich_text": {}},
    "Project Name": {"rich_text": {}},
    "Customer": {"rich_text": {}},
    "SPV": {"rich_text": {}},
    "Priority": {"rich_text": {}},
    "Site Address": {"rich_text": {}},
    "AM Contact": {"rich_text": {}},
    "AM Contact Email": {"email": {}},
    "Notion Page ID": {"rich_text": {}},
    "Asset Register URL": {"url": {}},
    "Capacity kWp": {"number": {"format": "number"}},
    "PPA Rate (GBP/MWh)": {"number": {"format": "number"}},
    "PPA Rate Source": {"rich_text": {}},
    "Target PR Assumption (%)": {"number": {"format": "percent"}},
    "Target Gen Yesterday (kWh)": {"number": {"format": "number"}},
    "Target Revenue Yesterday (£)": {"number": {"format": "number"}},
    "Target Weather Yesterday": {"rich_text": {}},
    "Target Gen Today (kWh)": {"number": {"format": "number"}},
    "Target Revenue Today (£)": {"number": {"format": "number"}},
    "Target Weather Today": {"rich_text": {}},
    "Target Gen Week (kWh)": {"number": {"format": "number"}},
    "Target Revenue Week (£)": {"number": {"format": "number"}},
    "Target Weather Week": {"rich_text": {}},
    "Target Revenue Message": {"rich_text": {}},
    "Curtailment Event Type": {"rich_text": {}},
    "Curtailment Generation Loss (kWh)": {"number": {"format": "number"}},
    "Curtailment Revenue Loss (£)": {"number": {"format": "number"}},
    "Curtailment Confidence": {"number": {"format": "number"}},
    "Curtailment Message": {"rich_text": {}},
    "Irradiance Source": {"rich_text": {}},
    "Irradiance Device ID": {"rich_text": {}},
    "Irradiance Threshold W/m2": {"number": {"format": "number"}},
    "Daylight HH Periods": {"number": {"format": "number"}},
    "Available HH Periods": {"number": {"format": "number"}},
    "Availability (%)": {"number": {"format": "percent"}},
    "Actual Daylight (kWh)": {"number": {"format": "number"}},
    "Expected Daylight (kWh)": {"number": {"format": "number"}},
    "H POA Daylight (kWh/m2)": {"number": {"format": "number"}},
    "PR (%)": {"number": {"format": "percent"}},
    "Irradiance Message": {"rich_text": {}},
    "Inverter Count": {"number": {"format": "number"}},
    "Inverters Reporting": {"number": {"format": "number"}},
    "Best Inverter Availability (%)": {"number": {"format": "percent"}},
    "Worst Inverter Availability (%)": {"number": {"format": "percent"}},
    "Inverter Availability Summary": {"rich_text": {}},
    "Inverter Availability Breakdown": {"rich_text": {}},
    "Juggle Identifier": {"rich_text": {}},
    "Juggle Status": {"rich_text": {}},
    "Juggle Has Data": {"checkbox": {}},
    "Juggle Sample Count": {"number": {"format": "number"}},
    "Juggle Message": {"rich_text": {}},
    "SolarEdge Identifier": {"rich_text": {}},
    "SolarEdge Status": {"rich_text": {}},
    "SolarEdge Has Data": {"checkbox": {}},
    "SolarEdge Sample Count": {"number": {"format": "number"}},
    "SolarEdge Message": {"rich_text": {}},
    "Solis Identifier": {"rich_text": {}},
    "Solis Status": {"rich_text": {}},
    "Solis Has Data": {"checkbox": {}},
    "Solis Sample Count": {"number": {"format": "number"}},
    "Solis Message": {"rich_text": {}},
    "Enphase Identifier": {"rich_text": {}},
    "Enphase Status": {"rich_text": {}},
    "Enphase Has Data": {"checkbox": {}},
    "Enphase Sample Count": {"number": {"format": "number"}},
    "Enphase Message": {"rich_text": {}},
    "Huawei Identifier": {"rich_text": {}},
    "Huawei Status": {"rich_text": {}},
    "Huawei Has Data": {"checkbox": {}},
    "Huawei Sample Count": {"number": {"format": "number"}},
    "Huawei Message": {"rich_text": {}},
    "SMA Identifier": {"rich_text": {}},
    "SMA Status": {"rich_text": {}},
    "SMA Has Data": {"checkbox": {}},
    "SMA Sample Count": {"number": {"format": "number"}},
    "SMA Message": {"rich_text": {}},
    "Daily JSON": {"rich_text": {}},
}

ASSET_CONTEXT_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "project_name": ("Project Name", "Alias", "Site"),
    "customer_name": ("Customer Registered Name", "Customer", "Customer Name"),
    "spv": ("SPV",),
    "priority": ("Priority",),
    "site_address": ("Site Address", "Billing Address"),
    "am_contact_name": (
        "Asset Manager",
        "AM",
        "AM Name",
        "REGO admin owner",
        "REGO Responsible",
        "Billing Contact",
        "O&M Contact",
        "Site Contact",
    ),
    "am_contact_email": (
        "AM Email",
        "Asset Manager Email",
        "Billing Contact Email",
        "Site Contact Email",
        "O&M Contact Email",
    ),
}


class DailyDataChecker(Protocol):
    async def check_day(self, identifier: str, target_date: date) -> "SourceCheckResult":
        ...


@dataclass(slots=True)
class SourceCheckResult:
    source: str
    status: str
    identifier: str | None
    target_date: str
    has_data: bool
    sample_count: int = 0
    message: str = ""


@dataclass(slots=True)
class MatchResolution:
    match_name: str = ""
    match_method: str = "unresolved"
    match_confidence: float = 0.0
    resolution_notes: str = ""
    mapping: dict[str, Any] | None = None


@dataclass(slots=True)
class TriageAssessment:
    issue_type: str
    severity: str
    confidence: float
    recommended_action: str
    issue_summary: str


def _normalise_key(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold().replace("_", " ")
    text = text.replace("'", "").replace("\u2019", "")
    return " ".join(text.split())


def _clean_identifier(value: Any) -> str:
    if value in (None, "", []):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if _normalise_key(text) in {"?", "n/a", "na", "none", "null", "unknown", "tbc", "pending"}:
        return ""
    return text


def _get_value(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    if not row:
        return None

    normalised = {_normalise_key(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalised.get(_normalise_key(candidate))
        if value not in (None, "", []):
            return value
    return None


def _get_candidate_and_value(row: dict[str, Any], candidates: tuple[str, ...]) -> tuple[str, Any]:
    if not row:
        return "", None

    normalised = {_normalise_key(key): (key, value) for key, value in row.items()}
    for candidate in candidates:
        matched = normalised.get(_normalise_key(candidate))
        if matched is None:
            continue
        original_key, value = matched
        if value not in (None, "", []):
            return str(original_key), value
    return "", None


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, dict):
        return _coerce_date(value.get("start"))

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            return parser(text).date()
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _extract_asset_name(row: dict[str, Any]) -> str:
    value = _get_value(row, ASSET_NAME_FIELD_CANDIDATES)
    if value is not None:
        return str(value).strip()
    return str(row.get("notion_page_id", "")).strip()


def _extract_asset_context(row: dict[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    for key, candidates in ASSET_CONTEXT_FIELD_CANDIDATES.items():
        value = _get_value(row, candidates)
        context[key] = "" if value in (None, [], {}) else str(value).strip()
    if not context.get("project_name"):
        context["project_name"] = _extract_asset_name(row)
    return context


def _coerce_float(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_capacity_kwp(row: dict[str, Any]) -> float | None:
    return _coerce_float(_get_value(row, CAPACITY_FIELD_CANDIDATES))


def _extract_ppa_rate_gbp_mwh(row: dict[str, Any]) -> tuple[float | None, str]:
    field_name, raw_value = _get_candidate_and_value(row, PPA_RATE_FIELD_CANDIDATES)
    if raw_value in (None, "", [], {}):
        return None, ""

    raw_text = str(raw_value).strip()
    numeric_text = (
        raw_text.replace("£", "")
        .replace("GBP", "")
        .replace("gbp", "")
        .replace("/MWh", "")
        .replace("/mwh", "")
        .replace("/kWh", "")
        .replace("/kwh", "")
        .replace("p/kWh", "")
        .replace("p/kwh", "")
        .replace("p per kWh", "")
        .replace("p per kwh", "")
        .replace(",", "")
        .strip()
    )
    numeric_value = _coerce_float(numeric_text)
    if numeric_value is None:
        return None, field_name

    field_key = _normalise_key(field_name)
    value_key = _normalise_key(raw_text)
    if "p/kwh" in field_key or "pence" in field_key or "p/kwh" in value_key or "p per kwh" in value_key:
        return numeric_value * 10.0, field_name
    if "£/kwh" in field_key or "gbp/kwh" in field_key or "£/kwh" in value_key or "gbp/kwh" in value_key:
        return numeric_value * 1000.0, field_name
    if "£/mwh" in field_key or "gbp/mwh" in field_key or "£/mwh" in value_key or "gbp/mwh" in value_key:
        return numeric_value, field_name

    inferred_value = numeric_value * 10.0 if numeric_value <= 20.0 else numeric_value
    return inferred_value, field_name


def _build_evidence_summary(row: dict[str, Any], context: dict[str, str]) -> str:
    sources = row.get("checked_sources", "")
    statuses: list[str] = []
    for source in SUPPORTED_SOURCES:
        status = row.get(f"{source}_status", "")
        identifier = row.get(f"{source}_identifier", "")
        if status and status != "unconfigured":
            suffix = f" ({identifier})" if identifier else ""
            statuses.append(f"{source}={status}{suffix}")

    parts = [
        f"Asset {row.get('asset_name', '')}",
        f"target date {row.get('target_date', '')}",
        f"match {row.get('match_method', '')}:{row.get('match_name', '')}",
    ]
    if context.get("customer_name"):
        parts.append(f"customer {context['customer_name']}")
    if sources:
        parts.append(f"sources checked {sources}")
    if statuses:
        parts.append("status " + "; ".join(statuses))
    note = str(row.get("resolution_notes", "")).strip()
    if note:
        parts.append(note)
    return ". ".join(part for part in parts if part).strip()


def _assess_triage_issue(row: dict[str, Any]) -> TriageAssessment:
    checked_sources = [source for source in str(row.get("checked_sources", "")).split(",") if source]
    statuses = {source: row.get(f"{source}_status", "") for source in SUPPORTED_SOURCES}
    error_sources = sorted(source for source, status in statuses.items() if status == "error")
    missing_identifier_sources = sorted(
        source for source, status in statuses.items() if status == "missing_identifier"
    )
    unconfigured_sources = sorted(
        source for source in checked_sources if statuses.get(source) == "unconfigured"
    )

    if row.get("match_method") == "unresolved":
        return TriageAssessment(
            issue_type="mapping_unresolved",
            severity="medium",
            confidence=0.95,
            recommended_action="Confirm the external monitoring site name and update Data Source Match in the asset register.",
            issue_summary="No canonical mapping is available, so the audit could not resolve an external data source.",
        )
    if error_sources:
        joined = ", ".join(error_sources)
        return TriageAssessment(
            issue_type="source_error",
            severity="high",
            confidence=0.85,
            recommended_action=f"Check the {joined} API response and credentials, then rerun the audit.",
            issue_summary=f"The audit hit API errors while checking {joined}.",
        )
    if unconfigured_sources and not row.get("has_any_data"):
        joined = ", ".join(unconfigured_sources)
        return TriageAssessment(
            issue_type="source_unconfigured",
            severity="medium",
            confidence=0.8,
            recommended_action=f"Configure credentials for {joined} in the local environment or GitHub Actions and rerun the audit.",
            issue_summary=f"The mapped source {joined} could not be checked because credentials are missing.",
        )
    if missing_identifier_sources and not row.get("has_any_data"):
        joined = ", ".join(missing_identifier_sources)
        return TriageAssessment(
            issue_type="missing_identifier",
            severity="medium",
            confidence=0.8,
            recommended_action=f"Add the missing external identifier for {joined} or confirm the Data Source Match mapping.",
            issue_summary=f"The audit knows which source to query but does not have identifiers for {joined}.",
        )
    if not row.get("has_any_data"):
        return TriageAssessment(
            issue_type="no_data",
            severity="high",
            confidence=0.7,
            recommended_action="Review telemetry availability, site communications, and inverter portal data for the target day.",
            issue_summary="The audit found no source data for the target day despite a resolved mapping.",
        )
    return TriageAssessment(
        issue_type="healthy_data_present",
        severity="info",
        confidence=0.9,
        recommended_action="No immediate action required.",
        issue_summary="At least one source reported data for the target day.",
    )


def _build_email_subject(asset_name: str, issue_type: str, target_date: str) -> str:
    return f"{asset_name}: {issue_type} for {target_date}"


def _build_email_draft(
    *,
    asset_name: str,
    target_date: str,
    assessment: TriageAssessment,
    context: dict[str, str],
    row: dict[str, Any],
) -> str:
    fallback = _build_fallback_email_draft(
        asset_name=asset_name,
        target_date=target_date,
        assessment=assessment,
        context=context,
        row=row,
    )
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return fallback

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = str(os.getenv("OPENAI_MODEL", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        prompt = (
            "Write a concise internal asset-manager email draft. "
            "Keep it factual, specific, and grounded only in the provided evidence. "
            "Do not invent telemetry or causes. Mention uncertainty explicitly when needed.\n\n"
            f"Asset: {asset_name}\n"
            f"Project: {context.get('project_name', '')}\n"
            f"Customer: {context.get('customer_name', '')}\n"
            f"SPV: {context.get('spv', '')}\n"
            f"Priority: {context.get('priority', '')}\n"
            f"Target date: {target_date}\n"
            f"Issue type: {assessment.issue_type}\n"
            f"Severity: {assessment.severity}\n"
            f"Confidence: {assessment.confidence:.2f}\n"
            f"Evidence summary: {_build_evidence_summary(row, context)}\n"
            f"Recommended action: {assessment.recommended_action}\n"
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content if response.choices else ""
        return str(content).strip() or fallback
    except Exception:
        return fallback


def _build_fallback_email_draft(
    *,
    asset_name: str,
    target_date: str,
    assessment: TriageAssessment,
    context: dict[str, str],
    row: dict[str, Any],
) -> str:
    contact = context.get("am_contact_name") or "team"
    project_name = context.get("project_name") or asset_name
    customer = context.get("customer_name") or "the customer"
    source_coverage = row.get("checked_sources", "no sources")
    preferred_source = row.get("preferred_source", "") or "none"
    return (
        f"Hi {contact},\n\n"
        f"The solar copilot triage for {project_name} ({customer}) flagged a {assessment.issue_type} issue for "
        f"{target_date}.\n\n"
        f"Summary: {assessment.issue_summary}\n"
        f"Evidence: {row.get('resolution_notes', '') or 'The current mapping and source audit were used.'}\n"
        f"Sources checked: {source_coverage}. Preferred source with data: {preferred_source}.\n\n"
        f"Recommended action: {assessment.recommended_action}\n\n"
        f"Regards,\nSolar Copilot"
    )


def _build_rich_text_items(value: Any, *, chunk_size: int = 1800) -> list[dict[str, Any]]:
    text = "" if value is None else str(value).strip()
    if not text:
        return []
    return [{"text": {"content": text[i:i + chunk_size]}} for i in range(0, len(text), chunk_size)]


def _text_property(value: Any) -> dict[str, Any]:
    return {"rich_text": _build_rich_text_items(value)}


def _title_property(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value).strip()
    return {"title": [] if not text else [{"text": {"content": text}}]}


def _date_property(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value).strip()
    return {"date": {"start": text}} if text else {"date": None}


def _number_property(value: Any) -> dict[str, Any]:
    numeric = _coerce_float(value)
    return {"number": numeric}


def _severity_sort_key(value: Any) -> int:
    return SEVERITY_RANK.get(str(value or "").strip().casefold(), -1)


def _build_finding(
    *,
    finding_type: str,
    severity: str,
    confidence: float,
    summary: str,
    recommended_action: str,
    source: str | None = None,
    context: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "finding_type": finding_type,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "recommended_action": recommended_action,
    }
    if source:
        finding["source"] = source
    if context:
        finding["context"] = context
    if metrics:
        finding["metrics"] = metrics
    return finding


def _extract_solis_day_energy_from_payload(
    payload: Any,
    *,
    target_date: date | None = None,
) -> float | None:
    data = payload.get("data", {}) if isinstance(payload, dict) else payload

    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        candidates = [data]
    elif isinstance(data, list):
        candidates = [item for item in data if isinstance(item, dict)]

    if target_date and len(candidates) > 1:
        target_token = target_date.isoformat()
        dated_candidates = [
            item
            for item in candidates
            if str(item.get("dateStr") or item.get("date") or item.get("time") or "").startswith(target_token)
        ]
        if dated_candidates:
            candidates = dated_candidates

    for item in candidates:
        value = _coerce_float(
            item.get("energy")
            or item.get("eToday")
            or item.get("dayEnergy")
            or item.get("dayEnergy1")
        )
        if value is not None:
            return value
    return None


def _derive_pac_phase(pac_date: date | None, as_of_date: date) -> str:
    if pac_date is None:
        return "unknown"
    if pac_date < as_of_date:
        return "post_pac"
    return "pre_pac"


def _coerce_platform_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]

    tokens: list[str] = []
    for item in items:
        for part in str(item).replace("/", ",").split(","):
            token = _normalise_key(part)
            if token:
                tokens.append(token)
    return tokens


def _canonical_platform(token: str) -> str | None:
    aliases = {
        "juggle": "juggle",
        "emig": "juggle",
        "solaredge": "solaredge",
        "solar edge": "solaredge",
        "solis": "solis",
        "enphase": "enphase",
        "huawei": "huawei",
        "fusion solar": "huawei",
        "fusionsolar": "huawei",
        "sma": "sma",
    }
    return aliases.get(token)


def _load_legacy_mapping(path: Path | None) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for key, value in DEFAULT_CONFIRMED_SOURCE_REGISTRY.items():
        if isinstance(value, dict):
            mapping[_normalise_key(key)] = {**value, "_mapping_name": key}

    if path is None or not path.exists():
        return mapping
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return mapping

    for key, value in raw.items():
        if isinstance(value, dict):
            mapping[_normalise_key(key)] = {**value, "_mapping_name": key}
    return mapping


def _default_legacy_mapping_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "inverter-data-juggle"
        / "2026-02-14-Inverter-data-juggle-File-Sites-Mapping-v01.json"
    )


class AdapterDailyChecker:
    def __init__(self, source: str, adapter_factory) -> None:
        self.source = source
        self._adapter_factory = adapter_factory

    async def check_day(self, identifier: str, target_date: date) -> SourceCheckResult:
        adapter = self._adapter_factory()
        if not getattr(adapter, "api_key", None) and self.source in {"juggle", "solaredge"}:
            return SourceCheckResult(
                source=self.source,
                status="unconfigured",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing API credentials",
            )
        if self.source == "enphase" and not (getattr(adapter, "client_id", "") and getattr(adapter, "client_secret", "")):
            return SourceCheckResult(
                source=self.source,
                status="unconfigured",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing API credentials",
            )
        if self.source == "huawei" and not (getattr(adapter, "username", "") and getattr(adapter, "password", "")):
            return SourceCheckResult(
                source=self.source,
                status="unconfigured",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing API credentials",
            )
        if self.source == "sma" and not (
            (getattr(adapter, "client_id", "") and getattr(adapter, "client_secret", ""))
            or (getattr(adapter, "username", "") and getattr(adapter, "password", ""))
        ):
            return SourceCheckResult(
                source=self.source,
                status="unconfigured",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing API credentials",
            )

        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        try:
            batch = await adapter.fetch_readings(identifier, start, end)
            has_data = bool(getattr(batch, "readings", []))
            return SourceCheckResult(
                source=self.source,
                status="ok" if has_data else "no_data",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=has_data,
                sample_count=len(getattr(batch, "readings", [])),
                message="; ".join(getattr(batch, "errors", []) + getattr(batch, "warnings", [])),
            )
        except Exception as exc:  # pragma: no cover - exercised against live APIs only
            return SourceCheckResult(
                source=self.source,
                status="error",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message=str(exc),
            )


class SolarEdgeDailyChecker:
    def __init__(self) -> None:
        self.base_url = os.getenv("SOLAREDGE_API_URL", "https://monitoringapi.solaredge.com")
        self.site_keys = _load_solaredge_site_keys()

    def _build_adapter(self, api_key: str):
        from solar_platform.ingestion.solaredge_adapter import SolarEdgeAdapter

        return SolarEdgeAdapter(api_key=api_key, base_url=self.base_url)

    async def check_day(self, identifier: str, target_date: date) -> SourceCheckResult:
        site_id = _clean_identifier(identifier)
        if not site_id:
            return SourceCheckResult(
                source="solaredge",
                status="missing_identifier",
                identifier=None,
                target_date=target_date.isoformat(),
                has_data=False,
                message="no source identifier available",
            )

        api_key = self.site_keys.get(site_id)
        if not api_key:
            return SourceCheckResult(
                source="solaredge",
                status="unconfigured",
                identifier=site_id,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing site-specific API key in SOLAREDGE_KEYS_JSON",
            )

        adapter = self._build_adapter(api_key)
        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        try:
            batch = await adapter.fetch_readings(site_id, start, end)
            has_data = bool(getattr(batch, "readings", []))
            return SourceCheckResult(
                source="solaredge",
                status="ok" if has_data else "no_data",
                identifier=site_id,
                target_date=target_date.isoformat(),
                has_data=has_data,
                sample_count=len(getattr(batch, "readings", [])),
                message="; ".join(getattr(batch, "errors", []) + getattr(batch, "warnings", [])),
            )
        except Exception as exc:  # pragma: no cover - exercised against live APIs only
            return SourceCheckResult(
                source="solaredge",
                status="error",
                identifier=site_id,
                target_date=target_date.isoformat(),
                has_data=False,
                message=str(exc),
            )


class SolisDailyChecker:
    def __init__(self) -> None:
        self.key_id = os.getenv("SOLIS_KEY_ID", "")
        self.key_secret = os.getenv("SOLIS_KEY_SECRET", "")
        self.base_url = (os.getenv("SOLIS_API_URL") or "https://www.soliscloud.com:13333").rstrip("/")

    async def check_day(self, identifier: str, target_date: date) -> SourceCheckResult:
        if not self.key_id or not self.key_secret:
            return SourceCheckResult(
                source="solis",
                status="unconfigured",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message="missing API credentials",
            )

        body = {
            "id": identifier,
            "money": "GBP",
            "time": target_date.isoformat(),
            "timeZone": 0,
        }
        body_str = json.dumps(body)
        headers = self._make_auth_headers(body_str, "/v1/api/stationDay")
        try:
            response = requests.post(
                f"{self.base_url}/v1/api/stationDay",
                headers=headers,
                data=body_str,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            raw_value = _extract_solis_day_energy_from_payload(
                payload,
                target_date=target_date,
            )
            has_data = raw_value not in (None, "", 0, 0.0, "0", "0.0")
            return SourceCheckResult(
                source="solis",
                status="ok" if has_data else "no_data",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=has_data,
                sample_count=1 if has_data else 0,
            )
        except Exception as exc:  # pragma: no cover - exercised against live APIs only
            return SourceCheckResult(
                source="solis",
                status="error",
                identifier=identifier,
                target_date=target_date.isoformat(),
                has_data=False,
                message=str(exc),
            )

    def _make_auth_headers(self, body: str, resource: str) -> dict[str, str]:
        content_type = "application/json"
        content_md5 = base64.b64encode(hashlib.md5(body.encode("utf-8")).digest()).decode("utf-8")
        date_str = datetime.now(tz=UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        sign_str = f"POST\n{content_md5}\n{content_type}\n{date_str}\n{resource}"
        signature = base64.b64encode(
            hmac.new(
                self.key_secret.encode("utf-8"),
                sign_str.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return {
            "Content-Type": content_type,
            "Content-MD5": content_md5,
            "Date": date_str,
            "Authorization": f"API {self.key_id}:{signature}",
        }


def build_default_checkers() -> dict[str, DailyDataChecker]:
    def _build_juggle_adapter():
        from solar_platform.ingestion.emig_adapter import EMIGAdapter

        return EMIGAdapter()

    def _build_enphase_adapter():
        from solar_platform.ingestion.enphase_adapter import EnphaseAdapter

        return EnphaseAdapter()

    def _build_huawei_adapter():
        from solar_platform.ingestion.huawei_adapter import HuaweiAdapter

        return HuaweiAdapter()

    def _build_sma_adapter():
        from solar_platform.ingestion.sma_adapter import SMAAdapter

        return SMAAdapter()

    return {
        "juggle": AdapterDailyChecker("juggle", _build_juggle_adapter),
        "solaredge": SolarEdgeDailyChecker(),
        "solis": SolisDailyChecker(),
        "enphase": AdapterDailyChecker("enphase", _build_enphase_adapter),
        "huawei": AdapterDailyChecker("huawei", _build_huawei_adapter),
        "sma": AdapterDailyChecker("sma", _build_sma_adapter),
    }


def _load_solaredge_site_keys() -> dict[str, str]:
    raw = str(os.getenv("SOLAREDGE_KEYS_JSON", "")).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(site_id).strip(): str(api_key).strip()
        for site_id, api_key in payload.items()
        if _clean_identifier(site_id) and _clean_identifier(api_key)
    }


class OpenMeteoArchiveIrradianceFetcher:
    """Thin adapter over the shared weather archive client."""

    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self, client: OpenMeteoArchiveClient | None = None) -> None:
        self.client = client or OpenMeteoArchiveClient()

    def fetch_half_hourly(
        self,
        *,
        target_date: date,
        latitude: float,
        longitude: float,
        timezone: str,
        tilt_deg: float,
        azimuth_deg: float,
    ) -> pd.DataFrame:
        records = self.client.fetch_archive(
            plant_name="irradiance_lookup",
            target_date=target_date,
            lat=latitude,
            lon=longitude,
            timezone=timezone,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
        )
        if not records:
            return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

        return _hourly_weather_records_to_half_hourly_df(records)


class OpenMeteoForecastIrradianceFetcher:
    def __init__(self, client: OpenMeteoClient | None = None) -> None:
        self.client = client or OpenMeteoClient()

    async def fetch_half_hourly(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        tilt_deg: float,
        azimuth_deg: float,
        site_name: str,
    ) -> pd.DataFrame:
        records = await self.client.fetch_forecast(
            plant_name=site_name,
            lat=latitude,
            lon=longitude,
            timezone=timezone,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
        )
        return _hourly_weather_records_to_half_hourly_df(records)


def _hourly_weather_records_to_half_hourly_df(records: list[Any]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

    rows: list[dict[str, Any]] = []
    for record in records:
        numeric_gti = _coerce_float(getattr(record, "gti_wm2", None))
        if numeric_gti is None:
            continue
        hour_ts = pd.to_datetime(getattr(record, "timestamp", None), errors="coerce", utc=True)
        if pd.isna(hour_ts):
            continue
        for offset_minutes in (0, 30):
            hh_ts = hour_ts + pd.Timedelta(minutes=offset_minutes)
            rows.append(
                {
                    "hh_ts": hh_ts,
                    "poa_interval_kwh_m2": numeric_gti / 2000.0,
                    "poa_wm2": numeric_gti,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

    return pd.DataFrame(rows).sort_values("hh_ts").reset_index(drop=True)


class RepositoryDaylightMetricsFetcher:
    def __init__(
        self,
        *,
        plant_repository: PlantRepository | Any | None = None,
        readings_repository: ReadingsRepository | Any | None = None,
        site_location_service: SiteLocationService | Any | None = None,
        archive_irradiance_fetcher: Any | None = None,
        forecast_irradiance_fetcher: Any | None = None,
        batch_fetcher=None,
        irradiance_threshold_wm2: float = 75.0,
        target_pr_ratio: float = TARGET_PR_ASSUMPTION,
        runtime_today: date | None = None,
    ) -> None:
        self.plant_repository = plant_repository or PlantRepository()
        self.readings_repository = readings_repository or ReadingsRepository()
        try:
            self.site_location_service = site_location_service or SiteLocationService()
        except Exception:
            self.site_location_service = site_location_service
        self.archive_irradiance_fetcher = archive_irradiance_fetcher or OpenMeteoArchiveIrradianceFetcher()
        self.forecast_irradiance_fetcher = forecast_irradiance_fetcher or OpenMeteoForecastIrradianceFetcher()
        self.batch_fetcher = batch_fetcher or self._fetch_source_batch
        self.irradiance_threshold_wm2 = irradiance_threshold_wm2
        self.target_pr_ratio = target_pr_ratio
        self.runtime_today = runtime_today or datetime.now(UTC).date()

    async def get_day_metrics(
        self,
        identifier: str,
        target_date: date,
        capacity_kwp: float | None = None,
        *,
        asset_name: str = "",
        match_name: str = "",
        source: str = "",
    ) -> dict[str, Any]:
        metrics = {
            "capacity_kwp": _coerce_float(capacity_kwp),
            "irradiance_source": "",
            "irradiance_device_id": "",
            "irradiance_threshold_wm2": self.irradiance_threshold_wm2,
            "daylight_hh_periods": 0,
            "available_hh_periods": 0,
            "availability_ratio": None,
            "actual_daylight_kwh": None,
            "expected_daylight_kwh": None,
            "h_poa_daylight_kwh_m2": None,
            "performance_ratio": None,
            "irradiance_message": "",
            "inverter_count": 0,
            "inverters_reporting": 0,
            "best_inverter_availability_ratio": None,
            "worst_inverter_availability_ratio": None,
            "inverter_availability_summary": "",
            "inverter_availability_breakdown": [],
        }

        plant_uid = self._resolve_plant_uid(
            source=source,
            identifier=identifier,
            match_name=match_name,
            asset_name=asset_name,
        )
        irr_df = pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])
        irradiance_errors: list[str] = []
        if plant_uid:
            try:
                irr_df = self._load_repo_poa_series(plant_uid, target_date)
            except Exception as exc:
                irradiance_errors.append(f"Repo POA lookup failed: {exc}")
                irr_df = pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])
            if not irr_df.empty:
                metrics["irradiance_source"] = "repo_solargis_weighted_poa"
                metrics["irradiance_device_id"] = "POA:SOLARGIS:WEIGHTED"

        if irr_df.empty:
            location = self._resolve_site_location(match_name=match_name, asset_name=asset_name)
            if location is not None:
                try:
                    irr_df = self.archive_irradiance_fetcher.fetch_half_hourly(
                        target_date=target_date,
                        latitude=float(location.latitude),
                        longitude=float(location.longitude),
                        timezone=str(location.timezone),
                        tilt_deg=float(location.tilt_deg),
                        azimuth_deg=float(location.azimuth_deg),
                    )
                except Exception as exc:
                    irradiance_errors.append(f"Archive irradiance fetch failed: {exc}")
                    irr_df = pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])
                if not irr_df.empty:
                    metrics["irradiance_source"] = "openmeteo_archive_gti"
                    metrics["irradiance_device_id"] = location.name

        if irr_df.empty:
            base_message = (
                "No irradiance data found for the target day."
                if plant_uid
                else "No plant or site-location match found for irradiance lookup."
            )
            if irradiance_errors:
                base_message = " | ".join([base_message, *irradiance_errors])
            metrics["irradiance_message"] = base_message
            return metrics

        daylight_df = irr_df[irr_df["poa_wm2"] > self.irradiance_threshold_wm2].copy()
        if daylight_df.empty:
            metrics["irradiance_message"] = "No daylight half-hours exceeded the irradiance threshold."
            return metrics

        metrics["daylight_hh_periods"] = int(len(daylight_df))
        metrics["h_poa_daylight_kwh_m2"] = float(daylight_df["poa_interval_kwh_m2"].sum())

        try:
            batch = await self.batch_fetcher(source, identifier, target_date)
        except Exception as exc:
            metrics["irradiance_message"] = f"Generation fetch failed: {exc}"
            return metrics

        generation_by_inverter_df = self._summarise_generation_by_inverter_batch(batch)
        daylight_hour_df = self._summarise_daylight_hours(daylight_df)
        generation_df = self._summarise_generation_by_hour(generation_by_inverter_df)
        merged = daylight_hour_df.merge(generation_df, on="hour_ts", how="left")
        merged["energy_kwh"] = pd.to_numeric(merged["energy_kwh"], errors="coerce").fillna(0.0)

        actual_daylight_kwh = float(merged["energy_kwh"].sum())
        available_hh_periods = int((merged["energy_kwh"] > 0).sum())
        metrics["actual_daylight_kwh"] = actual_daylight_kwh
        metrics["available_hh_periods"] = available_hh_periods
        metrics["availability_ratio"] = (
            available_hh_periods / len(daylight_hour_df) if len(daylight_hour_df) else None
        )
        metrics["daylight_hh_periods"] = int(len(daylight_hour_df))

        capacity = _coerce_float(capacity_kwp)
        if capacity and metrics["h_poa_daylight_kwh_m2"] is not None:
            expected_daylight_kwh = capacity * float(metrics["h_poa_daylight_kwh_m2"])
            metrics["expected_daylight_kwh"] = expected_daylight_kwh
            if expected_daylight_kwh > 0:
                metrics["performance_ratio"] = actual_daylight_kwh / expected_daylight_kwh
        else:
            metrics["irradiance_message"] = "Missing capacity kWp for PR calculation."

        metrics.update(
            self._build_inverter_availability_metrics(
                batch=batch,
                daylight_df=daylight_df,
                generation_by_inverter_df=generation_by_inverter_df,
            )
        )

        return metrics

    async def get_target_metrics(
        self,
        *,
        reference_date: date,
        capacity_kwp: float | None = None,
        ppa_rate_gbp_mwh: float | None = None,
        asset_name: str = "",
        match_name: str = "",
    ) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "ppa_rate_gbp_mwh": _coerce_float(ppa_rate_gbp_mwh),
            "target_pr_assumption_ratio": self.target_pr_ratio,
            "target_gen_yesterday_kwh": None,
            "target_revenue_yesterday_gbp": None,
            "target_weather_yesterday": "",
            "target_gen_today_kwh": None,
            "target_revenue_today_gbp": None,
            "target_weather_today": "",
            "target_gen_week_kwh": None,
            "target_revenue_week_gbp": None,
            "target_weather_week": "",
            "target_revenue_message": "",
        }

        capacity = _coerce_float(capacity_kwp)
        if capacity is None or capacity <= 0:
            metrics["target_revenue_message"] = "Missing capacity kWp for target generation."
            return metrics

        location = self._resolve_site_location(match_name=match_name, asset_name=asset_name)
        if location is None:
            metrics["target_revenue_message"] = "No site-location match found for target generation."
            return metrics

        forecast_df = pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])
        week_start = reference_date - timedelta(days=reference_date.weekday())
        week_end = week_start + timedelta(days=6)
        weather_errors: list[str] = []
        if week_end >= self.runtime_today:
            try:
                forecast_df = await self.forecast_irradiance_fetcher.fetch_half_hourly(
                    latitude=float(location.latitude),
                    longitude=float(location.longitude),
                    timezone=str(location.timezone),
                    tilt_deg=float(location.tilt_deg),
                    azimuth_deg=float(location.azimuth_deg),
                    site_name=str(location.name),
                )
            except Exception as exc:
                weather_errors.append(f"Forecast weather fetch failed: {exc}")

        yesterday_date = reference_date - timedelta(days=1)
        yesterday_gen, yesterday_source, yesterday_error = self._safe_compute_target_for_date(
            target_date=yesterday_date,
            location=location,
            capacity_kwp=capacity,
            forecast_df=forecast_df,
        )
        today_gen, today_source, today_error = self._safe_compute_target_for_date(
            target_date=reference_date,
            location=location,
            capacity_kwp=capacity,
            forecast_df=forecast_df,
        )
        if yesterday_error:
            weather_errors.append(yesterday_error)
        if today_error:
            weather_errors.append(today_error)

        week_gen_total = 0.0
        week_sources: set[str] = set()
        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            day_gen, day_source, day_error = self._safe_compute_target_for_date(
                target_date=current_date,
                location=location,
                capacity_kwp=capacity,
                forecast_df=forecast_df,
            )
            if day_gen is not None:
                week_gen_total += day_gen
            if day_source:
                week_sources.add(day_source)
            if day_error:
                weather_errors.append(day_error)

        metrics["target_gen_yesterday_kwh"] = yesterday_gen
        metrics["target_weather_yesterday"] = yesterday_source
        metrics["target_gen_today_kwh"] = today_gen
        metrics["target_weather_today"] = today_source
        metrics["target_gen_week_kwh"] = week_gen_total
        metrics["target_weather_week"] = "+".join(sorted(week_sources))
        if weather_errors:
            unique_errors: list[str] = []
            seen_errors: set[str] = set()
            for error in weather_errors:
                if error and error not in seen_errors:
                    seen_errors.add(error)
                    unique_errors.append(error)
            metrics["target_revenue_message"] = " | ".join(unique_errors)

        rate = _coerce_float(ppa_rate_gbp_mwh)
        if rate is None:
            if metrics["target_revenue_message"]:
                metrics["target_revenue_message"] += " | Missing PPA rate in asset register."
            else:
                metrics["target_revenue_message"] = "Missing PPA rate in asset register."
            return metrics

        if yesterday_gen is not None:
            metrics["target_revenue_yesterday_gbp"] = (yesterday_gen / 1000.0) * rate
        if today_gen is not None:
            metrics["target_revenue_today_gbp"] = (today_gen / 1000.0) * rate
        metrics["target_revenue_week_gbp"] = (week_gen_total / 1000.0) * rate
        return metrics

    def _safe_compute_target_for_date(
        self,
        *,
        target_date: date,
        location: Any,
        capacity_kwp: float,
        forecast_df: pd.DataFrame,
    ) -> tuple[float | None, str, str]:
        try:
            generation_kwh, weather_source = self._compute_target_for_date(
                target_date=target_date,
                location=location,
                capacity_kwp=capacity_kwp,
                forecast_df=forecast_df,
            )
            return generation_kwh, weather_source, ""
        except Exception as exc:
            weather_source = "archive" if target_date < self.runtime_today else "forecast"
            return None, weather_source, (
                f"{weather_source.capitalize()} weather fetch failed for {target_date.isoformat()}: {exc}"
            )

    def _resolve_plant_uid(
        self,
        *,
        source: str,
        identifier: str,
        match_name: str,
        asset_name: str,
    ) -> str:
        cleaned_identifier = _clean_identifier(identifier)
        if source == "juggle" and ":" in cleaned_identifier:
            return cleaned_identifier

        for candidate in (match_name, asset_name):
            if not candidate:
                continue
            try:
                plant = self.plant_repository.get_by_alias(candidate)
            except Exception as exc:
                logger.warning("plant registry alias lookup failed for %s: %s", candidate, exc)
                plant = None
            if plant and plant.get("plant_uid"):
                return str(plant["plant_uid"]).strip()

        try:
            all_plants = self.plant_repository.get_all()
        except Exception as exc:
            logger.warning("plant registry bulk lookup failed: %s", exc)
            return ""
        if not isinstance(all_plants, pd.DataFrame) or all_plants.empty:
            return ""

        candidate_tokens = set(_normalise_key(match_name or asset_name).split())
        if not candidate_tokens or "alias" not in all_plants.columns or "plant_uid" not in all_plants.columns:
            return ""

        best_uid = ""
        best_score = 0.0
        for _, plant in all_plants.iterrows():
            alias = str(plant.get("alias", "")).strip()
            plant_uid = str(plant.get("plant_uid", "")).strip()
            alias_tokens = set(_normalise_key(alias).split())
            if not alias_tokens or not plant_uid:
                continue
            score = len(candidate_tokens & alias_tokens) / max(len(candidate_tokens), len(alias_tokens))
            if score > best_score:
                best_score = score
                best_uid = plant_uid
        return best_uid if best_score >= 0.5 else ""

    def _resolve_site_location(self, *, match_name: str, asset_name: str):
        if self.site_location_service is None:
            return None

        for candidate in (match_name, asset_name):
            if not candidate:
                continue
            site = self.site_location_service.get_site(candidate)
            if site is not None:
                return site

        candidate_tokens = set(_normalise_key(match_name or asset_name).split())
        if not candidate_tokens:
            return None

        best_site = None
        best_score = 0.0
        for site in self.site_location_service.get_all_sites():
            site_tokens = set(_normalise_key(site.name).split())
            if not site_tokens:
                continue
            score = len(candidate_tokens & site_tokens) / max(len(candidate_tokens), len(site_tokens))
            if score > best_score:
                best_score = score
                best_site = site
        return best_site if best_score >= 0.5 else None

    def _compute_target_for_date(
        self,
        *,
        target_date: date,
        location: Any,
        capacity_kwp: float,
        forecast_df: pd.DataFrame,
    ) -> tuple[float | None, str]:
        weather_source = "archive" if target_date < self.runtime_today else "forecast"
        if weather_source == "archive":
            irr_df = self.archive_irradiance_fetcher.fetch_half_hourly(
                target_date=target_date,
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                timezone=str(location.timezone),
                tilt_deg=float(location.tilt_deg),
                azimuth_deg=float(location.azimuth_deg),
            )
        else:
            if forecast_df.empty:
                return None, "forecast"
            irr_df = forecast_df[
                pd.to_datetime(forecast_df["hh_ts"], utc=True).dt.date == target_date
            ].copy()

        if irr_df.empty:
            return None, weather_source

        positive_df = irr_df[pd.to_numeric(irr_df["poa_wm2"], errors="coerce").fillna(0.0) > 0].copy()
        if positive_df.empty:
            return 0.0, weather_source
        h_poa_kwh_m2 = float(pd.to_numeric(
            positive_df["poa_interval_kwh_m2"], errors="coerce"
        ).fillna(0.0).sum())
        return capacity_kwp * h_poa_kwh_m2 * self.target_pr_ratio, weather_source

    def _load_repo_poa_series(self, plant_uid: str, target_date: date) -> pd.DataFrame:
        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        df = self.readings_repository.get_readings(
            plant_uid=plant_uid,
            start=start,
            end=end,
            device_id="POA:SOLARGIS:WEIGHTED",
        )
        if df.empty:
            return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

        ts_col = "ts" if "ts" in df.columns else "timestamp"
        poa_col = "poaIrradiance_value" if "poaIrradiance_value" in df.columns else ""
        if not ts_col or not poa_col:
            return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

        work = df[[ts_col, poa_col]].copy()
        work[ts_col] = pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        work["poa_interval_kwh_m2"] = pd.to_numeric(work[poa_col], errors="coerce")
        work = work.dropna(subset=[ts_col, "poa_interval_kwh_m2"])
        if work.empty:
            return pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])

        work["hh_ts"] = work[ts_col].dt.floor("30min")
        grouped = (
            work.groupby("hh_ts", as_index=False)["poa_interval_kwh_m2"]
            .mean()
            .sort_values("hh_ts")
        )
        grouped["poa_wm2"] = grouped["poa_interval_kwh_m2"] * 2000.0
        return grouped

    def _summarise_generation_batch(self, batch) -> pd.DataFrame:  # noqa: ANN001
        work = self._summarise_generation_by_inverter_batch(batch)
        if work.empty:
            return pd.DataFrame(columns=["hh_ts", "energy_kwh"])
        return work.groupby("hh_ts", as_index=False)["energy_kwh"].sum().sort_values("hh_ts")

    def _summarise_daylight_hours(self, daylight_df: pd.DataFrame) -> pd.DataFrame:
        if daylight_df.empty:
            return pd.DataFrame(columns=["hour_ts"])

        work = daylight_df.copy()
        work["hour_ts"] = pd.to_datetime(work["hh_ts"], utc=True, errors="coerce").dt.floor("h")
        work = work.dropna(subset=["hour_ts"])
        if work.empty:
            return pd.DataFrame(columns=["hour_ts"])

        return work[["hour_ts"]].drop_duplicates().sort_values("hour_ts").reset_index(drop=True)

    def _summarise_generation_by_hour(self, generation_df: pd.DataFrame) -> pd.DataFrame:
        if generation_df.empty:
            return pd.DataFrame(columns=["hour_ts", "energy_kwh"])

        work = generation_df.copy()
        work["hour_ts"] = pd.to_datetime(work["hh_ts"], utc=True, errors="coerce").dt.floor("h")
        work = work.dropna(subset=["hour_ts"])
        if work.empty:
            return pd.DataFrame(columns=["hour_ts", "energy_kwh"])

        return (
            work.groupby("hour_ts", as_index=False)["energy_kwh"]
            .sum()
            .sort_values("hour_ts")
        )

    def _summarise_generation_by_inverter_hour(self, generation_by_inverter_df: pd.DataFrame) -> pd.DataFrame:
        if generation_by_inverter_df.empty:
            return pd.DataFrame(columns=["hour_ts", "device_id", "energy_kwh"])

        work = generation_by_inverter_df.copy()
        work["hour_ts"] = pd.to_datetime(work["hh_ts"], utc=True, errors="coerce").dt.floor("h")
        work = work.dropna(subset=["hour_ts"])
        if work.empty:
            return pd.DataFrame(columns=["hour_ts", "device_id", "energy_kwh"])

        return (
            work.groupby(["hour_ts", "device_id"], as_index=False)["energy_kwh"]
            .sum()
            .sort_values(["hour_ts", "device_id"])
        )

    def _summarise_generation_by_inverter_batch(self, batch) -> pd.DataFrame:  # noqa: ANN001
        readings = list(getattr(batch, "readings", []) or [])
        if not readings:
            return pd.DataFrame(columns=["hh_ts", "device_id", "energy_kwh"])

        rows: list[dict[str, Any]] = []
        for reading in readings:
            power_kw = _coerce_float(getattr(reading, "power_kw", None))
            energy_kwh = _coerce_float(getattr(reading, "energy_kwh", None))
            interval_seconds = _coerce_float(getattr(reading, "interval_seconds", None)) or 900.0
            interval_hours = interval_seconds / 3600.0
            timestamp = pd.to_datetime(getattr(reading, "timestamp", None), utc=True, errors="coerce")
            if pd.isna(timestamp):
                continue

            interval_kwh = None
            if power_kw is not None and power_kw > 0:
                interval_kwh = power_kw * interval_hours
            elif energy_kwh is not None and energy_kwh > 0:
                interval_kwh = energy_kwh

            raw_payload = getattr(reading, "raw_payload", None) or {}
            cumulative_wh = None
            for field_name in ("importEnergy", "exportEnergy"):
                raw_counter = raw_payload.get(field_name)
                if isinstance(raw_counter, dict):
                    counter_value = _coerce_float(raw_counter.get("value"))
                    if counter_value is not None:
                        cumulative_wh = counter_value
                        break

            rows.append(
                {
                    "hh_ts": timestamp.floor("30min"),
                    "ts": timestamp,
                    "device_id": getattr(reading, "device_id", ""),
                    "energy_kwh": float(interval_kwh) if interval_kwh is not None else None,
                    "cumulative_wh": cumulative_wh,
                }
            )

        if not rows:
            return pd.DataFrame(columns=["hh_ts", "device_id", "energy_kwh"])

        work = pd.DataFrame(rows)
        work = work.sort_values(["device_id", "ts"]).reset_index(drop=True)
        work["cumulative_wh"] = pd.to_numeric(work["cumulative_wh"], errors="coerce")
        work["derived_energy_kwh"] = work["energy_kwh"]

        for device_id, index in work.groupby("device_id").groups.items():
            device_rows = work.loc[index]
            deltas = device_rows["cumulative_wh"].diff()
            derived = deltas.where(deltas > 0) / 1000.0
            mask = device_rows["derived_energy_kwh"].isna()
            work.loc[index, "derived_energy_kwh"] = device_rows["derived_energy_kwh"].where(
                ~mask,
                derived,
            )

        work["derived_energy_kwh"] = pd.to_numeric(
            work["derived_energy_kwh"], errors="coerce"
        ).fillna(0.0)
        work = work[work["derived_energy_kwh"] > 0]
        if work.empty:
            return pd.DataFrame(columns=["hh_ts", "device_id", "energy_kwh"])

        return (
            work.groupby(["hh_ts", "device_id"], as_index=False)["derived_energy_kwh"]
            .sum()
            .rename(columns={"derived_energy_kwh": "energy_kwh"})
            .sort_values(["hh_ts", "device_id"])
        )

    def _build_inverter_availability_metrics(
        self,
        *,
        batch,
        daylight_df: pd.DataFrame,
        generation_by_inverter_df: pd.DataFrame,
    ) -> dict[str, Any]:  # noqa: ANN001
        device_ids = sorted(
            {
                str(getattr(reading, "device_id", "")).strip()
                for reading in list(getattr(batch, "readings", []) or [])
                if str(getattr(reading, "device_id", "")).strip()
            }
        )
        if not device_ids or daylight_df.empty:
            return {
                "inverter_count": len(device_ids),
                "inverters_reporting": 0,
                "best_inverter_availability_ratio": None,
                "worst_inverter_availability_ratio": None,
                "inverter_availability_summary": "",
                "inverter_availability_breakdown": [],
            }

        daylight_hour_df = self._summarise_daylight_hours(daylight_df)
        daylight_periods = int(len(daylight_hour_df))
        generation_by_inverter_hour_df = self._summarise_generation_by_inverter_hour(
            generation_by_inverter_df
        )
        breakdown: list[dict[str, Any]] = []
        for device_id in device_ids:
            device_df = (
                generation_by_inverter_hour_df[
                    generation_by_inverter_hour_df["device_id"] == device_id
                ].copy()
                if not generation_by_inverter_hour_df.empty
                else pd.DataFrame(columns=["hour_ts", "energy_kwh"])
            )
            merged = daylight_hour_df[["hour_ts"]].merge(
                device_df[["hour_ts", "energy_kwh"]],
                on="hour_ts",
                how="left",
            )
            merged["energy_kwh"] = pd.to_numeric(merged["energy_kwh"], errors="coerce").fillna(0.0)
            available_hh_periods = int((merged["energy_kwh"] > 0).sum())
            availability_ratio = available_hh_periods / daylight_periods if daylight_periods else 0.0
            actual_daylight_kwh = float(merged["energy_kwh"].sum())
            breakdown.append(
                {
                    "device_id": device_id,
                    "daylight_hh_periods": daylight_periods,
                    "available_hh_periods": available_hh_periods,
                    "availability_ratio": availability_ratio,
                    "actual_daylight_kwh": actual_daylight_kwh,
                }
            )

        best_ratio = max((item["availability_ratio"] for item in breakdown), default=None)
        worst_ratio = min((item["availability_ratio"] for item in breakdown), default=None)
        summary = "; ".join(
            f"{item['device_id']} {item['availability_ratio'] * 100:.1f}% "
            f"({item['available_hh_periods']}/{item['daylight_hh_periods']})"
            for item in breakdown
        )

        return {
            "inverter_count": len(device_ids),
            "inverters_reporting": sum(1 for item in breakdown if item["available_hh_periods"] > 0),
            "best_inverter_availability_ratio": best_ratio,
            "worst_inverter_availability_ratio": worst_ratio,
            "inverter_availability_summary": summary,
            "inverter_availability_breakdown": breakdown,
        }

    async def _fetch_source_batch(self, source: str, identifier: str, target_date: date):  # noqa: ANN001
        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)

        if source == "juggle":
            from solar_platform.ingestion.emig_adapter import EMIGAdapter

            return await EMIGAdapter().fetch_readings(identifier, start, end)

        if source == "solaredge":
            site_id = _clean_identifier(identifier)
            api_key = _load_solaredge_site_keys().get(site_id)
            if not api_key:
                raise RuntimeError("missing site-specific API key in SOLAREDGE_KEYS_JSON")
            from solar_platform.ingestion.solaredge_adapter import SolarEdgeAdapter

            base_url = os.getenv("SOLAREDGE_API_URL", "https://monitoringapi.solaredge.com")
            return await SolarEdgeAdapter(api_key=api_key, base_url=base_url).fetch_readings(site_id, start, end)

        raise RuntimeError(f"Daylight metrics do not support source '{source}'.")


class AssetRegisterAuditService:
    def __init__(
        self,
        notion_service: NotionAssetRegisterService | Any | None = None,
        settings: Any | None = None,
        legacy_mapping_path: Path | None = None,
        checkers: dict[str, DailyDataChecker] | None = None,
        supported_sources: tuple[str, ...] = SUPPORTED_SOURCES,
        daylight_metrics_fetcher: Any | None = None,
        juggle_daylight_metrics_fetcher: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.notion_service = notion_service or NotionAssetRegisterService(settings=self.settings)
        self.legacy_mapping = _load_legacy_mapping(legacy_mapping_path or _default_legacy_mapping_path())
        self.checkers = checkers or build_default_checkers()
        self.supported_sources = supported_sources
        self.daylight_metrics_fetcher = (
            daylight_metrics_fetcher
            or juggle_daylight_metrics_fetcher
            or RepositoryDaylightMetricsFetcher()
        )

    @staticmethod
    def confirmed_data_source_matches() -> dict[str, str]:
        return dict(DEFAULT_DATA_SOURCE_MATCH_UPDATES)

    def get_assets_with_past_pac_date(
        self,
        as_of_date: date | None = None,
        force_refresh: bool = False,
        asset_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.get_assets_for_daily_audit(
            as_of_date=as_of_date,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
        )
        return [row for row in rows if row.get("_pac_phase") == "post_pac"]

    def get_assets_for_daily_audit(
        self,
        as_of_date: date | None = None,
        force_refresh: bool = False,
        asset_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        today = as_of_date or datetime.now(UTC).date()
        rows = self.notion_service.get_asset_register(force_refresh=force_refresh)
        asset_filter_key = _normalise_key(asset_filter)

        filtered: list[dict[str, Any]] = []
        for row in rows:
            pac_value = _get_value(row, PAC_DATE_FIELD_CANDIDATES)
            pac_date = _coerce_date(pac_value)
            enriched = dict(row)
            enriched["_pac_date"] = pac_date
            enriched["_pac_phase"] = _derive_pac_phase(pac_date, today)
            if asset_filter_key:
                haystacks = (
                    _extract_asset_name(enriched),
                    str(_get_value(enriched, DATA_SOURCE_MATCH_FIELD_CANDIDATES) or ""),
                )
                if not any(asset_filter_key in _normalise_key(value) for value in haystacks if value):
                    continue
            filtered.append(enriched)
        return filtered

    def _lookup_exact_mapping(self, asset_name: str) -> dict[str, Any] | None:
        direct = self.legacy_mapping.get(_normalise_key(asset_name))
        return direct if isinstance(direct, dict) else None

    def _lookup_fuzzy_mapping(self, asset_name: str) -> tuple[dict[str, Any] | None, float]:
        asset_tokens = set(_normalise_key(asset_name).split())
        if not asset_tokens:
            return None, 0.0

        best_score = 0.0
        best_match: dict[str, Any] | None = None
        for mapping_name, mapping_row in self.legacy_mapping.items():
            mapping_tokens = set(mapping_name.split())
            if not mapping_tokens:
                continue

            overlap = len(asset_tokens & mapping_tokens)
            score = overlap / max(len(asset_tokens), len(mapping_tokens))

            if "ppa" in mapping_tokens:
                no_ppa_tokens = {token for token in mapping_tokens if token != "ppa"}
                if no_ppa_tokens:
                    overlap_without_ppa = len(asset_tokens & no_ppa_tokens)
                    score = max(score, overlap_without_ppa / max(len(asset_tokens), len(no_ppa_tokens)))

            if score >= 0.5 and score > best_score:
                best_score = score
                best_match = mapping_row

        return best_match, best_score

    def _extract_direct_identifiers(self, asset: dict[str, Any]) -> dict[str, str]:
        identifiers: dict[str, str] = {}
        for source, candidates in SOURCE_IDENTIFIER_FIELD_CANDIDATES.items():
            direct = _get_value(asset, candidates)
            cleaned = _clean_identifier(direct)
            if cleaned:
                identifiers[source] = cleaned
        return {key: value for key, value in identifiers.items() if value}

    def _resolve_match(self, asset: dict[str, Any]) -> MatchResolution:
        asset_name = _extract_asset_name(asset)
        override_name = str(_get_value(asset, DATA_SOURCE_MATCH_FIELD_CANDIDATES) or "").strip()
        direct_identifiers = self._extract_direct_identifiers(asset)

        if override_name:
            exact = self._lookup_exact_mapping(override_name)
            if exact:
                return MatchResolution(
                    match_name=str(exact.get("_mapping_name", override_name)),
                    match_method="notion_override",
                    match_confidence=1.0,
                    resolution_notes="Used Data Source Match override from Notion.",
                    mapping=exact,
                )
            fuzzy, score = self._lookup_fuzzy_mapping(override_name)
            if fuzzy:
                return MatchResolution(
                    match_name=str(fuzzy.get("_mapping_name", override_name)),
                    match_method="notion_override_fuzzy",
                    match_confidence=score,
                    resolution_notes=f"Notion override '{override_name}' matched the registry fuzzily.",
                    mapping=fuzzy,
                )
            return MatchResolution(
                match_name=override_name,
                match_method="notion_override",
                match_confidence=1.0,
                resolution_notes="Notion override present but not found in the registry.",
                mapping=None,
            )

        if direct_identifiers:
            return MatchResolution(
                match_name=asset_name,
                match_method="explicit_identifiers",
                match_confidence=1.0,
                resolution_notes="Used source identifiers present directly on the Notion asset row.",
                mapping=None,
            )

        exact = self._lookup_exact_mapping(asset_name)
        if exact:
            return MatchResolution(
                match_name=str(exact.get("_mapping_name", asset_name)),
                match_method="exact_registry",
                match_confidence=1.0,
                resolution_notes="Matched asset name directly against the legacy registry.",
                mapping=exact,
            )

        fuzzy, score = self._lookup_fuzzy_mapping(asset_name)
        if fuzzy:
            return MatchResolution(
                match_name=str(fuzzy.get("_mapping_name", asset_name)),
                match_method="fuzzy_registry",
                match_confidence=score,
                resolution_notes="Matched asset name fuzzily against the legacy registry.",
                mapping=fuzzy,
            )

        return MatchResolution(
            match_name="",
            match_method="unresolved",
            match_confidence=0.0,
            resolution_notes="No explicit identifiers or registry match available.",
            mapping=None,
        )

    def _infer_identifiers(self, asset: dict[str, Any], resolution: MatchResolution) -> dict[str, str]:
        identifiers = self._extract_direct_identifiers(asset)
        mapping = resolution.mapping or {}

        juggle_uid = _clean_identifier(mapping.get("juggle_uid"))
        if juggle_uid and "juggle" not in identifiers:
            identifiers["juggle"] = juggle_uid

        mapped_platform = _canonical_platform(_normalise_key(mapping.get("platform")))
        mapped_site_id = _clean_identifier(mapping.get("site_id", ""))
        if mapped_platform and mapped_site_id and mapped_platform not in identifiers:
            identifiers[mapped_platform] = mapped_site_id

        return {key: value for key, value in identifiers.items() if value}

    def _infer_candidate_sources(
        self,
        asset: dict[str, Any],
        identifiers: dict[str, str],
        resolution: MatchResolution,
    ) -> list[str]:
        mapping = resolution.mapping or {}
        hinted = {
            _canonical_platform(token)
            for token in _coerce_platform_tokens(_get_value(asset, PLATFORM_FIELD_CANDIDATES))
        }
        hinted.discard(None)
        mapped_platform = _canonical_platform(_normalise_key(mapping.get("platform")))
        if mapped_platform:
            hinted.add(mapped_platform)

        ordered: list[str] = []
        if not resolution.mapping and not identifiers and not hinted:
            ordered.append("juggle")
        elif "juggle" in identifiers or "juggle" in hinted:
            ordered.append("juggle")

        for source in self.supported_sources:
            if source == "juggle" or source in ordered:
                continue
            if source in hinted or source in identifiers:
                ordered.append(source)

        return [source for source in ordered if source in self.supported_sources]

    def _select_metrics_source(
        self,
        *,
        source_results: dict[str, SourceCheckResult],
        candidate_sources: list[str],
        identifiers: dict[str, str],
    ) -> str:
        preferred_sources = [
            source
            for source in candidate_sources
            if source_results.get(source) is not None and source_results[source].has_data
        ]
        if preferred_sources:
            return preferred_sources[0]
        for source in candidate_sources:
            if identifiers.get(source):
                return source
        return ""

    def _is_point_lane_asset(self, row: dict[str, Any]) -> bool:
        candidates = (
            row.get("asset_name", ""),
            row.get("project_name", ""),
            row.get("match_name", ""),
        )
        return any("point lane" in _normalise_key(value) for value in candidates if value)

    def _resolve_stark_daily_database_id(self) -> str:
        configured = str(getattr(self.settings, "notion_stark_daily_database_id", "") or "").strip()
        if configured:
            return configured
        finder = getattr(self.notion_service, "find_database_by_title", None)
        if callable(finder):
            return str(finder(STARK_DAILY_DATABASE_TITLE) or "").strip()
        return ""

    def _lookup_stark_daily_total(self, target_date: date) -> float | None:
        database_id = self._resolve_stark_daily_database_id()
        if not database_id:
            return None
        query_rows = getattr(self.notion_service, "query_database_rows", None)
        if not callable(query_rows):
            return None
        rows = query_rows(
            database_id,
            filter_payload={
                "filter": {
                    "property": "Date",
                    "date": {"equals": target_date.isoformat()},
                }
            },
        )
        for row in rows:
            row_date = _coerce_date(row.get("Date") or row.get("Settlement Date"))
            if row_date != target_date:
                continue
            total_kwh = _coerce_float(row.get("Total kWh"))
            if total_kwh is not None:
                return total_kwh
        return None

    def _build_stark_fusion_variance_finding(self, row: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_point_lane_asset(row):
            return None
        fusion_kwh = _coerce_float(row.get("actual_daylight_kwh"))
        if fusion_kwh is None or fusion_kwh <= 0:
            return None
        target_date = _coerce_date(row.get("target_date"))
        if target_date is None:
            return None
        stark_kwh = self._lookup_stark_daily_total(target_date)
        if stark_kwh is None:
            return None
        diff_kwh = fusion_kwh - stark_kwh
        if fusion_kwh <= 0:
            return None
        diff_pct = abs(diff_kwh) / fusion_kwh * 100.0
        if diff_pct <= STARK_FUSION_VARIANCE_THRESHOLD_PCT:
            return None
        return _build_finding(
            finding_type="stark_fusion_variance",
            severity="high",
            confidence=0.9,
            summary="Stark total differs materially from FusionSolar total for the target day.",
            recommended_action="Check the Stark HH total against the Point Lane FusionSolar day total and confirm whether the discrepancy is expected.",
            source="stark",
            metrics={
                "fusion_kwh": fusion_kwh,
                "stark_kwh": stark_kwh,
                "diff_kwh": diff_kwh,
                "diff_pct": diff_pct,
            },
        )

    def _juggle_api_key(self) -> str:
        candidates = (
            getattr(self.settings, "effective_api_key", ""),
            getattr(self.settings, "juggle_api_key", ""),
            getattr(self.settings, "emig_api_key", ""),
            os.getenv("JUGGLE_API_KEY", ""),
            os.getenv("EMIG_API_KEY", ""),
        )
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    def _juggle_base_url(self) -> str:
        return (
            str(os.getenv("EMIG_API_URL") or os.getenv("JUGGLE_API_URL") or "https://www.emig.co.uk/p/api")
            .rstrip("/")
        )

    def _request_juggle_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        api_key = self._juggle_api_key()
        if not api_key:
            return None
        response = requests.get(
            f"{self._juggle_base_url()}{path}",
            headers={"Authorization": f"token {api_key}"},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _fetch_juggle_device_ids(self, plant_uid: str) -> tuple[list[str], list[str]]:
        details = self._request_juggle_json(f"/plant/{plant_uid}")
        if not isinstance(details, dict):
            return [], []
        meters = details.get("meters", [])
        if not isinstance(meters, list):
            return [], []
        inverter_ids = [
            str(meter.get("emigId", "")).strip()
            for meter in meters
            if isinstance(meter, dict) and meter.get("type") == "INVERTER" and str(meter.get("emigId", "")).strip()
        ]
        pv_meter_ids = [
            str(meter.get("emigId", "")).strip()
            for meter in meters
            if isinstance(meter, dict) and meter.get("type") == "PV" and str(meter.get("emigId", "")).strip()
        ]
        return inverter_ids, pv_meter_ids

    def _fetch_juggle_device_readings(self, emig_id: str, target_date: date) -> list[dict[str, Any]]:
        payload = self._request_juggle_json(
            f"/meter/{emig_id}/readings",
            params={
                "startDate": target_date.strftime("%Y%m%d"),
                "endDate": target_date.strftime("%Y%m%d"),
                "minIntervalS": 1800,
            },
        )
        if isinstance(payload, dict):
            readings = payload.get("readings", [])
            return readings if isinstance(readings, list) else []
        return payload if isinstance(payload, list) else []

    def _normalise_juggle_readings(self, device_id: str, readings: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            if not isinstance(reading, dict):
                continue
            timestamp = pd.to_datetime(reading.get("ts") or reading.get("timestamp"), utc=True, errors="coerce")
            if pd.isna(timestamp):
                continue

            def _raw_value(name: str) -> float | None:
                raw = reading.get(name)
                if isinstance(raw, dict):
                    return _coerce_float(raw.get("value"))
                return _coerce_float(raw)

            rows.append(
                {
                    "device_id": device_id,
                    "timestamp": timestamp,
                    "importEnergy": _raw_value("importEnergy"),
                    "exportEnergy": _raw_value("exportEnergy"),
                    "importActivePower": _raw_value("importActivePower"),
                }
            )
        return pd.DataFrame(rows)

    def _counter_total_kwh(self, df: pd.DataFrame, column: str) -> float:
        if df.empty or column not in df.columns:
            return 0.0
        work = df.copy()
        work[column] = pd.to_numeric(work[column], errors="coerce")
        work = work.dropna(subset=[column])
        if work.empty:
            return 0.0
        grouped = work.groupby("device_id")[column].agg(["min", "max"]).reset_index()
        grouped["energy_wh"] = grouped["max"] - grouped["min"]
        grouped.loc[grouped["energy_wh"] < 0, "energy_wh"] = 0.0
        return float(grouped["energy_wh"].sum() / 1000.0)

    def _positive_power_total_kwh(self, df: pd.DataFrame, column: str) -> float:
        if df.empty or column not in df.columns:
            return 0.0
        work = df.copy()
        work[column] = pd.to_numeric(work[column], errors="coerce")
        work = work.dropna(subset=[column])
        work = work[work[column] > 0]
        if work.empty:
            return 0.0
        grouped = work.groupby("device_id")[column].sum().reset_index()
        return float(grouped[column].sum() * 0.5 / 1000.0)

    def _fetch_juggle_inverter_meter_totals(
        self,
        plant_uid: str,
        target_date: date,
    ) -> tuple[float | None, float | None]:
        inverter_ids, pv_meter_ids = self._fetch_juggle_device_ids(plant_uid)
        if not inverter_ids or not pv_meter_ids:
            return None, None

        inverter_frames = [
            self._normalise_juggle_readings(device_id, self._fetch_juggle_device_readings(device_id, target_date))
            for device_id in inverter_ids
        ]
        meter_frames = [
            self._normalise_juggle_readings(device_id, self._fetch_juggle_device_readings(device_id, target_date))
            for device_id in pv_meter_ids
        ]

        inverter_df = pd.concat([frame for frame in inverter_frames if not frame.empty], ignore_index=True) if any(
            not frame.empty for frame in inverter_frames
        ) else pd.DataFrame()
        meter_df = pd.concat([frame for frame in meter_frames if not frame.empty], ignore_index=True) if any(
            not frame.empty for frame in meter_frames
        ) else pd.DataFrame()

        inverter_kwh = self._counter_total_kwh(inverter_df, "exportEnergy")
        if inverter_kwh <= 0:
            inverter_kwh = self._counter_total_kwh(inverter_df, "importEnergy")
        if inverter_kwh <= 0:
            inverter_kwh = self._positive_power_total_kwh(inverter_df, "importActivePower")

        meter_kwh = self._counter_total_kwh(meter_df, "importEnergy")
        if meter_kwh <= 0:
            meter_kwh = self._positive_power_total_kwh(meter_df, "importActivePower")
        if meter_kwh <= 0:
            meter_kwh = self._counter_total_kwh(meter_df, "exportEnergy")

        return inverter_kwh, meter_kwh

    def _fetch_solis_day_energy(self, station_id: str, target_date: date) -> float | None:
        key_id = str(os.getenv("SOLIS_KEY_ID", "")).strip()
        key_secret = str(os.getenv("SOLIS_KEY_SECRET", "")).strip()
        if not key_id or not key_secret:
            return None
        body = {
            "id": station_id,
            "money": "GBP",
            "time": target_date.isoformat(),
            "timeZone": 0,
        }
        body_str = json.dumps(body)
        checker = SolisDailyChecker()
        headers = checker._make_auth_headers(body_str, "/v1/api/stationDay")
        try:
            response = requests.post(
                f"{checker.base_url}/v1/api/stationDay",
                headers=headers,
                data=body_str,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            return _extract_solis_day_energy_from_payload(
                payload,
                target_date=target_date,
            )
        except Exception:
            return None

    def _compute_inverter_meter_alert(self, inverter_kwh: float, meter_kwh: float) -> str:
        has_inv = inverter_kwh > 0
        has_meter = meter_kwh > 0
        if has_meter and not has_inv:
            return "Meter Only"
        if has_inv and not has_meter:
            return "Inverter Only"
        if not has_inv and not has_meter:
            return "OK"
        diff_pct = abs((inverter_kwh - meter_kwh) / meter_kwh) * 100.0 if meter_kwh else 0.0
        if diff_pct > INVERTER_METER_ALERT_CRITICAL_PCT:
            return "Critical"
        return "OK"

    def _build_inverter_meter_comparison_finding(
        self,
        row: dict[str, Any],
        identifiers: dict[str, str],
        resolution: MatchResolution,
        target_date: date,
    ) -> dict[str, Any] | None:
        plant_uid = identifiers.get("juggle")
        if not plant_uid:
            return None
        try:
            inverter_kwh, meter_kwh = self._fetch_juggle_inverter_meter_totals(plant_uid, target_date)
        except Exception:
            return None
        if inverter_kwh is None or meter_kwh is None:
            return None

        platform = _canonical_platform(_normalise_key((resolution.mapping or {}).get("platform")))
        solis_kwh = None
        if platform == "solis":
            solis_id = identifiers.get("solis")
            if solis_id:
                solis_kwh = self._fetch_solis_day_energy(solis_id, target_date)

        alert_label = self._compute_inverter_meter_alert(inverter_kwh, meter_kwh)
        if alert_label == "OK":
            return None

        diff_kwh = inverter_kwh - meter_kwh
        diff_pct = (diff_kwh / meter_kwh * 100.0) if meter_kwh else 0.0
        severity = "high" if alert_label == "Critical" else "medium"
        metrics = {
            "inverter_kwh": inverter_kwh,
            "meter_kwh": meter_kwh,
            "diff_kwh": diff_kwh,
            "diff_pct": diff_pct,
            "alert_label": alert_label,
            "platform": platform or "",
        }
        if solis_kwh is not None:
            metrics["solis_kwh"] = solis_kwh

        return _build_finding(
            finding_type="inverter_meter_comparison",
            severity=severity,
            confidence=0.9,
            summary="Inverter total differs from PV meter total.",
            recommended_action="Review Juggle inverter totals, PV meter totals, and platform day totals for the target day.",
            source="juggle",
            metrics=metrics,
        )

    def _build_findings_for_row(
        self,
        *,
        row: dict[str, Any],
        identifiers: dict[str, str],
        resolution: MatchResolution,
        target_date: date,
    ) -> list[dict[str, Any]]:
        checked_sources = [source for source in str(row.get("checked_sources", "")).split(",") if source]
        statuses = {source: row.get(f"{source}_status", "") for source in self.supported_sources}
        error_sources = sorted(source for source, status in statuses.items() if status == "error")
        missing_identifier_sources = sorted(
            source for source, status in statuses.items() if status == "missing_identifier"
        )
        unconfigured_sources = sorted(
            source for source in checked_sources if statuses.get(source) == "unconfigured"
        )

        findings: list[dict[str, Any]] = []
        if row.get("match_method") == "unresolved":
            findings.append(
                _build_finding(
                    finding_type="mapping_unresolved",
                    severity="medium",
                    confidence=0.95,
                    summary="No canonical mapping is available, so the audit could not resolve an external data source.",
                    recommended_action="Confirm the external monitoring site name and update Data Source Match in the asset register.",
                    context={
                        "checked_sources": row.get("checked_sources", ""),
                        "match_method": row.get("match_method", ""),
                    },
                )
            )
        elif error_sources:
            joined = ", ".join(error_sources)
            findings.append(
                _build_finding(
                    finding_type="source_error",
                    severity="high",
                    confidence=0.85,
                    summary=f"The audit hit API errors while checking {joined}.",
                    recommended_action=f"Check the {joined} API response and credentials, then rerun the audit.",
                    source=joined if len(error_sources) == 1 else None,
                    context={
                        "checked_sources": row.get("checked_sources", ""),
                        "match_method": row.get("match_method", ""),
                    },
                )
            )
        elif unconfigured_sources and not row.get("has_any_data"):
            joined = ", ".join(unconfigured_sources)
            findings.append(
                _build_finding(
                    finding_type="source_unconfigured",
                    severity="medium",
                    confidence=0.8,
                    summary=f"The mapped source {joined} could not be checked because credentials are missing.",
                    recommended_action=f"Configure credentials for {joined} in the local environment or GitHub Actions and rerun the audit.",
                    source=joined if len(unconfigured_sources) == 1 else None,
                    context={
                        "checked_sources": row.get("checked_sources", ""),
                        "match_method": row.get("match_method", ""),
                    },
                )
            )
        elif missing_identifier_sources and not row.get("has_any_data"):
            joined = ", ".join(missing_identifier_sources)
            findings.append(
                _build_finding(
                    finding_type="missing_identifier",
                    severity="medium",
                    confidence=0.8,
                    summary=f"The audit knows which source to query but does not have identifiers for {joined}.",
                    recommended_action=f"Add the missing external identifier for {joined} or confirm the Data Source Match mapping.",
                    source=joined if len(missing_identifier_sources) == 1 else None,
                    context={
                        "checked_sources": row.get("checked_sources", ""),
                        "match_method": row.get("match_method", ""),
                    },
                )
            )
        elif not row.get("has_any_data"):
            findings.append(
                _build_finding(
                    finding_type="no_data",
                    severity="high",
                    confidence=0.7,
                    summary="The audit found no source data for the target day despite a resolved mapping.",
                    recommended_action="Review telemetry availability, site communications, and inverter portal data for the target day.",
                    context={
                        "checked_sources": row.get("checked_sources", ""),
                        "match_method": row.get("match_method", ""),
                    },
                )
            )

        stark_finding = self._build_stark_fusion_variance_finding(row)
        if stark_finding is not None:
            findings.append(stark_finding)

        inverter_meter_finding = self._build_inverter_meter_comparison_finding(
            row,
            identifiers,
            resolution,
            target_date,
        )
        if inverter_meter_finding is not None:
            findings.append(inverter_meter_finding)

        findings.sort(key=lambda item: _severity_sort_key(item.get("severity")), reverse=True)
        return findings

    def _project_triage_record(
        self,
        *,
        row: dict[str, Any],
        finding: dict[str, Any],
        context: dict[str, str],
    ) -> dict[str, Any]:
        finding_type = str(finding.get("finding_type", "")).strip()
        finding_summary = str(finding.get("summary", "")).strip()
        email_subject = _build_email_subject(
            asset_name=str(row.get("asset_name", "")).strip(),
            issue_type=finding_type,
            target_date=str(row.get("target_date", "")).strip(),
        )
        assessment = TriageAssessment(
            issue_type=finding_type,
            severity=str(finding.get("severity", "medium")).strip() or "medium",
            confidence=float(finding.get("confidence", 0.0) or 0.0),
            recommended_action=str(finding.get("recommended_action", "")).strip(),
            issue_summary=finding_summary,
        )
        email_draft = _build_email_draft(
            asset_name=str(row.get("asset_name", "")).strip(),
            target_date=str(row.get("target_date", "")).strip(),
            assessment=assessment,
            context=context,
            row=row,
        )
        return {
            "row_key": f"{row.get('target_date', '')}|{row.get('asset_name', '')}|{finding_type}",
            "asset_name": row.get("asset_name", ""),
            "project_name": context["project_name"],
            "customer_name": context["customer_name"],
            "spv": context["spv"],
            "priority": context["priority"],
            "target_date": row.get("target_date", ""),
            "finding_type": finding_type,
            "finding_summary": finding_summary,
            "issue_type": finding_type,
            "severity": assessment.severity,
            "confidence": assessment.confidence,
            "source_coverage": row.get("checked_sources", ""),
            "evidence_summary": _build_evidence_summary(row, context),
            "recommended_action": assessment.recommended_action,
            "email_subject": email_subject,
            "email_draft": email_draft,
            "am_contact_name": context["am_contact_name"],
            "am_contact_email": context["am_contact_email"],
            "asset_register_url": row.get("notion_url", ""),
            "preferred_source": row.get("preferred_source", ""),
            "match_method": row.get("match_method", ""),
            "has_any_data": bool(row.get("has_any_data")),
        }

    def backfill_confirmed_data_source_matches(
        self,
        updates: dict[str, str] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        mapping_updates = updates or self.confirmed_data_source_matches()
        rows = self.notion_service.get_asset_register(force_refresh=force_refresh)

        summary = {
            "property_name": DATA_SOURCE_MATCH_FIELD_CANDIDATES[0],
            "requested_updates": len(mapping_updates),
            "updated": [],
            "unchanged": [],
            "missing_pages": [],
            "missing_assets": [],
            "failed": [],
        }

        if not self.notion_service.ensure_rich_text_property(DATA_SOURCE_MATCH_FIELD_CANDIDATES[0]):
            summary["failed"].append("property_create_failed")
            return summary

        rows_by_name = {_extract_asset_name(row): row for row in rows}
        for asset_name, canonical_name in mapping_updates.items():
            row = rows_by_name.get(asset_name)
            if not row:
                summary["missing_assets"].append(asset_name)
                continue

            current_value = str(_get_value(row, DATA_SOURCE_MATCH_FIELD_CANDIDATES) or "").strip()
            if current_value == canonical_name:
                summary["unchanged"].append(asset_name)
                continue

            page_id = str(row.get("notion_page_id", "")).strip()
            if not page_id:
                summary["missing_pages"].append(asset_name)
                continue

            success = self.notion_service.update_page_properties(
                page_id,
                {DATA_SOURCE_MATCH_FIELD_CANDIDATES[0]: canonical_name},
            )
            if success:
                summary["updated"].append(asset_name)
            else:
                summary["failed"].append(asset_name)

        return summary

    async def build_yesterday_dataset(
        self,
        reference_date: date | None = None,
        force_refresh: bool = False,
        asset_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        today = reference_date or datetime.now(UTC).date()
        target_date = today - timedelta(days=1)
        assets = self.get_assets_for_daily_audit(
            as_of_date=today,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
        )

        rows: list[dict[str, Any]] = []
        for asset in assets:
            asset_name = _extract_asset_name(asset)
            pac_date = asset.get("_pac_date")
            pac_phase = str(asset.get("_pac_phase", _derive_pac_phase(pac_date, today)))
            capacity_kwp = _extract_capacity_kwp(asset)
            ppa_rate_gbp_mwh, ppa_rate_source = _extract_ppa_rate_gbp_mwh(asset)
            resolution = self._resolve_match(asset)
            identifiers = self._infer_identifiers(asset, resolution)
            candidate_sources = self._infer_candidate_sources(asset, identifiers, resolution)
            source_results: dict[str, SourceCheckResult] = {}

            for source in candidate_sources:
                checker = self.checkers.get(source)
                identifier = identifiers.get(source)
                if checker is None:
                    source_results[source] = SourceCheckResult(
                        source=source,
                        status="unconfigured",
                        identifier=identifier,
                        target_date=target_date.isoformat(),
                        has_data=False,
                        message="checker not configured",
                    )
                elif not identifier:
                    source_results[source] = SourceCheckResult(
                        source=source,
                        status="missing_identifier",
                        identifier=None,
                        target_date=target_date.isoformat(),
                        has_data=False,
                        message="no source identifier available",
                    )
                else:
                    result = await checker.check_day(identifier, target_date)
                    if isinstance(result, dict):
                        result = SourceCheckResult(**result)
                    source_results[source] = result

            row: dict[str, Any] = {
                "asset_name": asset_name,
                "target_date": target_date.isoformat(),
                "pac_date": pac_date.isoformat() if isinstance(pac_date, date) else "",
                "pac_phase": pac_phase,
                "pac_in_past": pac_phase == "post_pac",
                "pac_date_missing": pac_phase == "unknown",
                "notion_page_id": asset.get("notion_page_id", ""),
                "notion_url": asset.get("notion_url", ""),
                "match_name": resolution.match_name,
                "match_method": resolution.match_method,
                "match_confidence": resolution.match_confidence,
                "resolved_source_types": ",".join(sorted(identifiers)),
                "resolution_notes": resolution.resolution_notes,
                "capacity_kwp": capacity_kwp,
                "ppa_rate_gbp_mwh": ppa_rate_gbp_mwh,
                "ppa_rate_source": ppa_rate_source,
                "target_pr_assumption_ratio": TARGET_PR_ASSUMPTION,
                "target_gen_yesterday_kwh": None,
                "target_revenue_yesterday_gbp": None,
                "target_weather_yesterday": "",
                "target_gen_today_kwh": None,
                "target_revenue_today_gbp": None,
                "target_weather_today": "",
                "target_gen_week_kwh": None,
                "target_revenue_week_gbp": None,
                "target_weather_week": "",
                "target_revenue_message": "",
                "curtailment_event_type": "",
                "curtailment_generation_loss_kwh": None,
                "curtailment_revenue_loss_gbp": None,
                "curtailment_confidence": None,
                "curtailment_message": "",
                "irradiance_source": "",
                "irradiance_device_id": "",
                "irradiance_threshold_wm2": None,
                "daylight_hh_periods": 0,
                "available_hh_periods": 0,
                "availability_ratio": None,
                "actual_daylight_kwh": None,
                "expected_daylight_kwh": None,
                "h_poa_daylight_kwh_m2": None,
                "performance_ratio": None,
                "irradiance_message": "",
                "inverter_count": 0,
                "inverters_reporting": 0,
                "best_inverter_availability_ratio": None,
                "worst_inverter_availability_ratio": None,
                "inverter_availability_summary": "",
                "inverter_availability_breakdown": [],
                "findings": [],
                "finding_types": [],
                "actionable_finding_count": 0,
                "highest_finding_severity": "",
            }
            row.update(_extract_asset_context(asset))

            if self.daylight_metrics_fetcher is not None:
                target_metrics_getter = getattr(self.daylight_metrics_fetcher, "get_target_metrics", None)
                if callable(target_metrics_getter):
                    target_metrics = target_metrics_getter(
                        reference_date=today,
                        capacity_kwp=capacity_kwp,
                        ppa_rate_gbp_mwh=ppa_rate_gbp_mwh,
                        asset_name=asset_name,
                        match_name=resolution.match_name,
                    )
                    if inspect.isawaitable(target_metrics):
                        target_metrics = await target_metrics
                    if isinstance(target_metrics, dict):
                        row.update(target_metrics)

            sources_with_data: list[str] = []
            for source in self.supported_sources:
                result = source_results.get(source)
                identifier = identifiers.get(source)
                row[f"{source}_identifier"] = identifier or ""
                if result is None:
                    row[f"{source}_status"] = "unconfigured"
                    row[f"{source}_has_data"] = False
                    row[f"{source}_sample_count"] = 0
                    row[f"{source}_message"] = ""
                    continue

                row[f"{source}_status"] = result.status
                row[f"{source}_has_data"] = result.has_data
                row[f"{source}_sample_count"] = result.sample_count
                row[f"{source}_message"] = result.message
                if result.has_data:
                    sources_with_data.append(source)

            row["checked_sources"] = ",".join(candidate_sources)
            row["sources_with_data"] = ",".join(sources_with_data)
            row["has_any_data"] = bool(sources_with_data)
            row["preferred_source"] = sources_with_data[0] if sources_with_data else ""
            metrics_source = self._select_metrics_source(
                source_results=source_results,
                candidate_sources=candidate_sources,
                identifiers=identifiers,
            )
            if metrics_source and self.daylight_metrics_fetcher is not None:
                identifier = identifiers.get(metrics_source, "")
                metrics = self.daylight_metrics_fetcher.get_day_metrics(
                    identifier,
                    target_date,
                    capacity_kwp=capacity_kwp,
                    asset_name=asset_name,
                    match_name=resolution.match_name,
                    source=metrics_source,
                )
                if inspect.isawaitable(metrics):
                    metrics = await metrics
                if isinstance(metrics, dict):
                    row.update(metrics)

            expected_daylight_kwh = _coerce_float(row.get("expected_daylight_kwh"))
            actual_daylight_kwh = _coerce_float(row.get("actual_daylight_kwh"))
            ppa_rate = _coerce_float(row.get("ppa_rate_gbp_mwh"))
            if (
                row.get("has_any_data")
                and expected_daylight_kwh is not None
                and actual_daylight_kwh is not None
                and expected_daylight_kwh > actual_daylight_kwh
            ):
                generation_loss_kwh = expected_daylight_kwh - actual_daylight_kwh
                row["curtailment_event_type"] = "curtailment_candidate"
                row["curtailment_generation_loss_kwh"] = generation_loss_kwh
                row["curtailment_revenue_loss_gbp"] = (
                    (generation_loss_kwh / 1000.0) * ppa_rate
                    if ppa_rate is not None
                    else None
                )
                row["curtailment_confidence"] = 0.6
                row["curtailment_message"] = (
                    "Estimated from daylight expected-vs-actual generation gap; "
                    "controller state is not confirmed in the daily asset audit."
                )
            findings = self._build_findings_for_row(
                row=row,
                identifiers=identifiers,
                resolution=resolution,
                target_date=target_date,
            )
            row["findings"] = findings
            row["finding_types"] = [str(item.get("finding_type", "")).strip() for item in findings if item.get("finding_type")]
            row["actionable_finding_count"] = sum(1 for item in findings if _severity_sort_key(item.get("severity")) >= _severity_sort_key("medium"))
            highest_severity = max((item.get("severity", "") for item in findings), key=_severity_sort_key, default="")
            row["highest_finding_severity"] = str(highest_severity or "")
            rows.append(row)

        return rows

    async def build_triage_records(
        self,
        reference_date: date | None = None,
        force_refresh: bool = False,
        asset_filter: str | None = None,
        include_healthy: bool = False,
    ) -> list[dict[str, Any]]:
        dataset = await self.build_yesterday_dataset(
            reference_date=reference_date,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
        )

        triage_records: list[dict[str, Any]] = []
        for row in dataset:
            if row.get("pac_phase") != "post_pac":
                continue
            findings = list(row.get("findings", []) or [])
            if not findings:
                if not include_healthy:
                    continue
                findings = [
                    _build_finding(
                        finding_type="healthy_data_present",
                        severity="info",
                        confidence=0.9,
                        summary="At least one source reported data for the target day.",
                        recommended_action="No immediate action required.",
                    )
                ]
            actionable_findings = [
                finding
                for finding in findings
                if include_healthy or str(finding.get("finding_type", "")).strip() != "healthy_data_present"
            ]
            if not actionable_findings:
                continue

            context = {
                "project_name": str(row.get("project_name", "")).strip(),
                "customer_name": str(row.get("customer_name", "")).strip(),
                "spv": str(row.get("spv", "")).strip(),
                "priority": str(row.get("priority", "")).strip(),
                "site_address": str(row.get("site_address", "")).strip(),
                "am_contact_name": str(row.get("am_contact_name", "")).strip(),
                "am_contact_email": str(row.get("am_contact_email", "")).strip(),
            }
            for finding in actionable_findings:
                triage_records.append(
                    self._project_triage_record(
                        row=row,
                        finding=finding,
                        context=context,
                    )
                )

        return triage_records

    def publish_daily_dataset_to_notion(
        self,
        dataset: list[dict[str, Any]],
        *,
        database_id: str | None = None,
        parent_page_id: str | None = None,
        database_title: str = DAILY_JSON_DATABASE_TITLE,
        only_with_data: bool = True,
    ) -> dict[str, Any]:
        if only_with_data:
            rows_to_publish = [
                row
                for row in dataset
                if row.get("has_any_data") or row.get("findings")
            ]
        else:
            rows_to_publish = list(dataset)
        target_database_id = str(database_id or "").strip()
        if not target_database_id:
            target_database_id = self.notion_service.ensure_database(
                database_title,
                DAILY_JSON_DATABASE_PROPERTIES,
                parent_page_id=parent_page_id,
            ) or ""
        if not target_database_id:
            return {"database_id": None, "published": 0, "failed": len(rows_to_publish)}
        self.notion_service.ensure_database_properties(target_database_id, DAILY_JSON_DATABASE_PROPERTIES)

        published = 0
        failed = 0
        for row in rows_to_publish:
            row_key = f"{row.get('target_date', '')}|{row.get('asset_name', '')}"
            properties = {
                "Asset": _title_property(row.get("asset_name")),
                "Row Key": _text_property(row_key),
                "Target Date": _date_property(row.get("target_date")),
                "PAC Date": _date_property(row.get("pac_date")),
                "PAC Phase": _text_property(row.get("pac_phase")),
                "PAC In Past": {"checkbox": bool(row.get("pac_in_past"))},
                "PAC Date Missing": {"checkbox": bool(row.get("pac_date_missing"))},
                "Has Any Data": {"checkbox": bool(row.get("has_any_data"))},
                "Sources With Data": _text_property(row.get("sources_with_data")),
                "Preferred Source": _text_property(row.get("preferred_source")),
                "Checked Sources": _text_property(row.get("checked_sources")),
                "Match Name": _text_property(row.get("match_name")),
                "Match Method": _text_property(row.get("match_method")),
                "Match Confidence": {"number": float(row.get("match_confidence", 0.0) or 0.0)},
                "Resolved Source Types": _text_property(row.get("resolved_source_types")),
                "Resolution Notes": _text_property(row.get("resolution_notes")),
                "Project Name": _text_property(row.get("project_name")),
                "Customer": _text_property(row.get("customer_name")),
                "SPV": _text_property(row.get("spv")),
                "Priority": _text_property(row.get("priority")),
                "Site Address": _text_property(row.get("site_address")),
                "AM Contact": _text_property(row.get("am_contact_name")),
                "AM Contact Email": {"email": str(row.get("am_contact_email", "")).strip() or None},
                "Notion Page ID": _text_property(row.get("notion_page_id")),
                "Asset Register URL": {"url": str(row.get("notion_url", "")).strip() or None},
                "Capacity kWp": _number_property(row.get("capacity_kwp")),
                "PPA Rate (GBP/MWh)": _number_property(row.get("ppa_rate_gbp_mwh")),
                "PPA Rate Source": _text_property(row.get("ppa_rate_source")),
                "Target PR Assumption (%)": _number_property(row.get("target_pr_assumption_ratio")),
                "Target Gen Yesterday (kWh)": _number_property(row.get("target_gen_yesterday_kwh")),
                "Target Revenue Yesterday (£)": _number_property(row.get("target_revenue_yesterday_gbp")),
                "Target Weather Yesterday": _text_property(row.get("target_weather_yesterday")),
                "Target Gen Today (kWh)": _number_property(row.get("target_gen_today_kwh")),
                "Target Revenue Today (£)": _number_property(row.get("target_revenue_today_gbp")),
                "Target Weather Today": _text_property(row.get("target_weather_today")),
                "Target Gen Week (kWh)": _number_property(row.get("target_gen_week_kwh")),
                "Target Revenue Week (£)": _number_property(row.get("target_revenue_week_gbp")),
                "Target Weather Week": _text_property(row.get("target_weather_week")),
                "Target Revenue Message": _text_property(row.get("target_revenue_message")),
                "Curtailment Event Type": _text_property(row.get("curtailment_event_type")),
                "Curtailment Generation Loss (kWh)": _number_property(row.get("curtailment_generation_loss_kwh")),
                "Curtailment Revenue Loss (£)": _number_property(row.get("curtailment_revenue_loss_gbp")),
                "Curtailment Confidence": _number_property(row.get("curtailment_confidence")),
                "Curtailment Message": _text_property(row.get("curtailment_message")),
                "Irradiance Source": _text_property(row.get("irradiance_source")),
                "Irradiance Device ID": _text_property(row.get("irradiance_device_id")),
                "Irradiance Threshold W/m2": _number_property(row.get("irradiance_threshold_wm2")),
                "Daylight HH Periods": _number_property(row.get("daylight_hh_periods")),
                "Available HH Periods": _number_property(row.get("available_hh_periods")),
                "Availability (%)": _number_property(row.get("availability_ratio")),
                "Actual Daylight (kWh)": _number_property(row.get("actual_daylight_kwh")),
                "Expected Daylight (kWh)": _number_property(row.get("expected_daylight_kwh")),
                "H POA Daylight (kWh/m2)": _number_property(row.get("h_poa_daylight_kwh_m2")),
                "PR (%)": _number_property(row.get("performance_ratio")),
                "Irradiance Message": _text_property(row.get("irradiance_message")),
                "Inverter Count": _number_property(row.get("inverter_count")),
                "Inverters Reporting": _number_property(row.get("inverters_reporting")),
                "Best Inverter Availability (%)": _number_property(row.get("best_inverter_availability_ratio")),
                "Worst Inverter Availability (%)": _number_property(row.get("worst_inverter_availability_ratio")),
                "Inverter Availability Summary": _text_property(row.get("inverter_availability_summary")),
                "Inverter Availability Breakdown": _text_property(
                    json.dumps(row.get("inverter_availability_breakdown", []), sort_keys=True)
                ),
                "Juggle Identifier": _text_property(row.get("juggle_identifier")),
                "Juggle Status": _text_property(row.get("juggle_status")),
                "Juggle Has Data": {"checkbox": bool(row.get("juggle_has_data"))},
                "Juggle Sample Count": {"number": float(row.get("juggle_sample_count", 0) or 0)},
                "Juggle Message": _text_property(row.get("juggle_message")),
                "SolarEdge Identifier": _text_property(row.get("solaredge_identifier")),
                "SolarEdge Status": _text_property(row.get("solaredge_status")),
                "SolarEdge Has Data": {"checkbox": bool(row.get("solaredge_has_data"))},
                "SolarEdge Sample Count": {"number": float(row.get("solaredge_sample_count", 0) or 0)},
                "SolarEdge Message": _text_property(row.get("solaredge_message")),
                "Solis Identifier": _text_property(row.get("solis_identifier")),
                "Solis Status": _text_property(row.get("solis_status")),
                "Solis Has Data": {"checkbox": bool(row.get("solis_has_data"))},
                "Solis Sample Count": {"number": float(row.get("solis_sample_count", 0) or 0)},
                "Solis Message": _text_property(row.get("solis_message")),
                "Enphase Identifier": _text_property(row.get("enphase_identifier")),
                "Enphase Status": _text_property(row.get("enphase_status")),
                "Enphase Has Data": {"checkbox": bool(row.get("enphase_has_data"))},
                "Enphase Sample Count": {"number": float(row.get("enphase_sample_count", 0) or 0)},
                "Enphase Message": _text_property(row.get("enphase_message")),
                "Huawei Identifier": _text_property(row.get("huawei_identifier")),
                "Huawei Status": _text_property(row.get("huawei_status")),
                "Huawei Has Data": {"checkbox": bool(row.get("huawei_has_data"))},
                "Huawei Sample Count": {"number": float(row.get("huawei_sample_count", 0) or 0)},
                "Huawei Message": _text_property(row.get("huawei_message")),
                "SMA Identifier": _text_property(row.get("sma_identifier")),
                "SMA Status": _text_property(row.get("sma_status")),
                "SMA Has Data": {"checkbox": bool(row.get("sma_has_data"))},
                "SMA Sample Count": {"number": float(row.get("sma_sample_count", 0) or 0)},
                "SMA Message": _text_property(row.get("sma_message")),
                "Daily JSON": _text_property(json.dumps(row, sort_keys=True)),
            }
            create_page = getattr(self.notion_service, "create_database_page", None)
            if callable(create_page):
                page_id = create_page(
                    database_id=target_database_id,
                    properties=properties,
                )
            else:
                page_id = self.notion_service.upsert_database_page(
                    database_id=target_database_id,
                    match_field="Row Key",
                    match_value=row_key,
                    properties=properties,
                )
            if page_id:
                published += 1
            else:
                failed += 1

        return {
            "database_id": target_database_id,
            "published": published,
            "failed": failed,
            "eligible_rows": len(rows_to_publish),
        }

    def publish_triage_records_to_notion(
        self,
        triage_records: list[dict[str, Any]],
        parent_page_id: str | None = None,
    ) -> dict[str, Any]:
        database_id = self.notion_service.ensure_database(
            TRIAGE_DATABASE_TITLE,
            TRIAGE_DATABASE_PROPERTIES,
            parent_page_id=parent_page_id or getattr(self.settings, "notion_page_id", None),
        )
        if not database_id:
            return {"database_id": None, "published": 0, "failed": len(triage_records)}

        published = 0
        failed = 0
        for record in triage_records:
            properties = {
                "Asset": _title_property(record.get("asset_name")),
                "Row Key": _text_property(record.get("row_key")),
                "Target Date": {"date": {"start": str(record.get("target_date", "")).strip() or None}},
                "Issue Type": _text_property(record.get("issue_type")),
                "Severity": _text_property(record.get("severity")),
                "Confidence": {"number": float(record.get("confidence", 0.0) or 0.0)},
                "Source Coverage": _text_property(record.get("source_coverage")),
                "Evidence Summary": _text_property(record.get("evidence_summary")),
                "Recommended Action": _text_property(record.get("recommended_action")),
                "AM Email Subject": _text_property(record.get("email_subject")),
                "AM Email Draft": _text_property(record.get("email_draft")),
                "AM Contact": _text_property(record.get("am_contact_name")),
                "AM Contact Email": {"email": str(record.get("am_contact_email", "")).strip() or None},
                "Project Name": _text_property(record.get("project_name")),
                "Customer": _text_property(record.get("customer_name")),
                "SPV": _text_property(record.get("spv")),
                "Priority": _text_property(record.get("priority")),
                "Asset Register URL": {"url": str(record.get("asset_register_url", "")).strip() or None},
                "Preferred Source": _text_property(record.get("preferred_source")),
                "Match Method": _text_property(record.get("match_method")),
                "Has Any Data": {"checkbox": bool(record.get("has_any_data"))},
            }
            page_id = self.notion_service.upsert_database_page(
                database_id=database_id,
                match_field="Row Key",
                match_value=str(record.get("row_key", "")).strip(),
                properties=properties,
            )
            if page_id:
                published += 1
            else:
                failed += 1

        return {"database_id": database_id, "published": published, "failed": failed}

    def write_dataset(
        self,
        dataset: list[dict[str, Any]],
        output_dir: Path,
        target_date: str,
    ) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"asset_yesterday_dataset_{target_date}.json"
        csv_path = output_dir / f"asset_yesterday_dataset_{target_date}.csv"

        json_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

        fieldnames: list[str] = []
        for row in dataset:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in dataset:
                writer.writerow(row)

        return {"json": str(json_path), "csv": str(csv_path)}


async def run_asset_register_yesterday_audit(
    output_dir: Path,
    reference_date: date | None = None,
    force_refresh: bool = False,
    asset_filter: str | None = None,
) -> dict[str, Any]:
    service = AssetRegisterAuditService()
    dataset = await service.build_yesterday_dataset(
        reference_date=reference_date,
        force_refresh=force_refresh,
        asset_filter=asset_filter,
    )
    target_date = (reference_date or datetime.now(UTC).date()) - timedelta(days=1)
    paths = service.write_dataset(dataset, output_dir=output_dir, target_date=target_date.isoformat())
    return {
        "target_date": target_date.isoformat(),
        "rows": len(dataset),
        "paths": paths,
        "dataset": dataset,
    }


async def run_asset_register_triage_publish(
    output_dir: Path,
    reference_date: date | None = None,
    force_refresh: bool = False,
    asset_filter: str | None = None,
    include_healthy: bool = False,
) -> dict[str, Any]:
    service = AssetRegisterAuditService()
    triage_records = await service.build_triage_records(
        reference_date=reference_date,
        force_refresh=force_refresh,
        asset_filter=asset_filter,
        include_healthy=include_healthy,
    )
    target_date = (reference_date or datetime.now(UTC).date()) - timedelta(days=1)
    output_dir.mkdir(parents=True, exist_ok=True)
    triage_json_path = output_dir / f"asset_triage_records_{target_date.isoformat()}.json"
    triage_json_path.write_text(json.dumps(triage_records, indent=2), encoding="utf-8")

    publish_result = service.publish_triage_records_to_notion(triage_records)
    return {
        "target_date": target_date.isoformat(),
        "rows": len(triage_records),
        "triage_json": str(triage_json_path),
        "publish_result": publish_result,
        "triage_records": triage_records,
    }


async def run_asset_register_daily_publish(
    output_dir: Path,
    reference_date: date | None = None,
    force_refresh: bool = False,
    asset_filter: str | None = None,
    *,
    database_id: str | None = None,
    parent_page_id: str | None = None,
) -> dict[str, Any]:
    service = AssetRegisterAuditService()
    dataset = await service.build_yesterday_dataset(
        reference_date=reference_date,
        force_refresh=force_refresh,
        asset_filter=asset_filter,
    )
    target_date = (reference_date or datetime.now(UTC).date()) - timedelta(days=1)
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_json_path = output_dir / f"asset_daily_records_{target_date.isoformat()}.json"
    daily_json_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    publish_result = service.publish_daily_dataset_to_notion(
        dataset,
        database_id=database_id,
        parent_page_id=parent_page_id,
    )
    return {
        "target_date": target_date.isoformat(),
        "rows": len(dataset),
        "daily_json": str(daily_json_path),
        "publish_result": publish_result,
        "dataset": dataset,
    }
