"""Asset-register driven yesterday data audit for the performance copilot."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

import requests

from solar_platform.config import get_settings
from solar_platform.ingestion.emig_adapter import EMIGAdapter
from solar_platform.ingestion.enphase_adapter import EnphaseAdapter
from solar_platform.ingestion.huawei_adapter import HuaweiAdapter
from solar_platform.ingestion.sma_adapter import SMAAdapter
from solar_platform.ingestion.solaredge_adapter import SolarEdgeAdapter
from solar_platform.integrations.notion_assets import NotionAssetRegisterService


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

TRIAGE_DATABASE_TITLE = "Solar Copilot Daily Triage"

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


def _get_value(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    if not row:
        return None

    normalised = {_normalise_key(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalised.get(_normalise_key(candidate))
        if value not in (None, "", []):
            return value
    return None


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


def _text_property(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value).strip()
    return {"rich_text": [] if not text else [{"text": {"content": text}}]}


def _title_property(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value).strip()
    return {"title": [] if not text else [{"text": {"content": text}}]}


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
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    mapping: dict[str, dict[str, Any]] = {}
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


class SolisDailyChecker:
    def __init__(self) -> None:
        self.key_id = os.getenv("SOLIS_KEY_ID", "")
        self.key_secret = os.getenv("SOLIS_KEY_SECRET", "")
        self.base_url = os.getenv("SOLIS_API_URL", "https://www.soliscloud.com:13333")

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
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            raw_value = data.get("energy") or data.get("eToday") or data.get("dayEnergy")
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
    return {
        "juggle": AdapterDailyChecker("juggle", lambda: EMIGAdapter()),
        "solaredge": AdapterDailyChecker("solaredge", lambda: SolarEdgeAdapter()),
        "solis": SolisDailyChecker(),
        "enphase": AdapterDailyChecker("enphase", lambda: EnphaseAdapter()),
        "huawei": AdapterDailyChecker("huawei", lambda: HuaweiAdapter()),
        "sma": AdapterDailyChecker("sma", lambda: SMAAdapter()),
    }


class AssetRegisterAuditService:
    def __init__(
        self,
        notion_service: NotionAssetRegisterService | Any | None = None,
        settings: Any | None = None,
        legacy_mapping_path: Path | None = None,
        checkers: dict[str, DailyDataChecker] | None = None,
        supported_sources: tuple[str, ...] = SUPPORTED_SOURCES,
    ) -> None:
        self.settings = settings or get_settings()
        self.notion_service = notion_service or NotionAssetRegisterService(settings=self.settings)
        self.legacy_mapping = _load_legacy_mapping(legacy_mapping_path or _default_legacy_mapping_path())
        self.checkers = checkers or build_default_checkers()
        self.supported_sources = supported_sources

    @staticmethod
    def confirmed_data_source_matches() -> dict[str, str]:
        return dict(DEFAULT_DATA_SOURCE_MATCH_UPDATES)

    def get_assets_with_past_pac_date(
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
            if pac_date is None or pac_date >= today:
                continue
            enriched = dict(row)
            enriched["_pac_date"] = pac_date
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
            if direct not in (None, "", []):
                identifiers[source] = str(direct).strip()
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

        if mapping.get("juggle_uid") and "juggle" not in identifiers:
            identifiers["juggle"] = str(mapping["juggle_uid"]).strip()

        mapped_platform = _canonical_platform(_normalise_key(mapping.get("platform")))
        mapped_site_id = str(mapping.get("site_id", "")).strip()
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

        ordered = ["juggle"]
        for source in self.supported_sources:
            if source == "juggle":
                continue
            if source in hinted or source in identifiers:
                ordered.append(source)

        return [source for source in ordered if source in self.supported_sources]

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
        assets = self.get_assets_with_past_pac_date(
            as_of_date=today,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
        )

        rows: list[dict[str, Any]] = []
        for asset in assets:
            asset_name = _extract_asset_name(asset)
            pac_date = asset.get("_pac_date")
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
                "notion_page_id": asset.get("notion_page_id", ""),
                "notion_url": asset.get("notion_url", ""),
                "match_name": resolution.match_name,
                "match_method": resolution.match_method,
                "match_confidence": resolution.match_confidence,
                "resolved_source_types": ",".join(sorted(identifiers)),
                "resolution_notes": resolution.resolution_notes,
            }
            row.update(_extract_asset_context(asset))

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
            assessment = _assess_triage_issue(row)
            if not include_healthy and assessment.issue_type == "healthy_data_present":
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
            evidence_summary = _build_evidence_summary(row, context)
            email_subject = _build_email_subject(
                asset_name=str(row.get("asset_name", "")).strip(),
                issue_type=assessment.issue_type,
                target_date=str(row.get("target_date", "")).strip(),
            )
            email_draft = _build_email_draft(
                asset_name=str(row.get("asset_name", "")).strip(),
                target_date=str(row.get("target_date", "")).strip(),
                assessment=assessment,
                context=context,
                row=row,
            )
            triage_records.append(
                {
                    "row_key": f"{row.get('target_date', '')}|{row.get('asset_name', '')}|{assessment.issue_type}",
                    "asset_name": row.get("asset_name", ""),
                    "project_name": context["project_name"],
                    "customer_name": context["customer_name"],
                    "spv": context["spv"],
                    "priority": context["priority"],
                    "target_date": row.get("target_date", ""),
                    "issue_type": assessment.issue_type,
                    "severity": assessment.severity,
                    "confidence": assessment.confidence,
                    "source_coverage": row.get("checked_sources", ""),
                    "evidence_summary": evidence_summary,
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
            )

        return triage_records

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
