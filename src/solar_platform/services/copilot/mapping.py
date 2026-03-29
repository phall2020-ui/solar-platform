"""Field extraction, mapping resolution helpers, and Notion property builder utilities."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from solar_platform.services.copilot.models import (
    ASSET_CONTEXT_FIELD_CANDIDATES,
    ASSET_NAME_FIELD_CANDIDATES,
    CAPACITY_FIELD_CANDIDATES,
    DEFAULT_CONFIRMED_SOURCE_REGISTRY,
    DEFAULT_PPA_RATE_GBP_MWH,
    DEFAULT_PPA_RATE_SOURCE,
    PPA_RATE_FIELD_CANDIDATES,
    SEVERITY_RANK,
    SUPPORTED_SOURCES,
)


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
        return DEFAULT_PPA_RATE_GBP_MWH, DEFAULT_PPA_RATE_SOURCE

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
        return DEFAULT_PPA_RATE_GBP_MWH, DEFAULT_PPA_RATE_SOURCE

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
        Path(__file__).resolve().parents[4]
        / "tools"
        / "inverter-data-juggle"
        / "2026-02-14-Inverter-data-Juggle-File-Sites-Mapping-v01.json"
    )
