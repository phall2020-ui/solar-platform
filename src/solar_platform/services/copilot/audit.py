"""AssetRegisterAuditService and top-level entry point functions for the performance copilot."""

from __future__ import annotations

import csv
import inspect
import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from solar_platform.config import get_settings
from solar_platform.integrations.notion_assets import NotionAssetRegisterService
from solar_platform.services.copilot.checkers import (
    SolisDailyChecker,
    build_default_checkers,
    _load_solaredge_site_keys,
)
from solar_platform.services.copilot.curtailment import ExportLimitCurtailmentFetcher
from solar_platform.services.copilot.daylight_metrics import RepositoryDaylightMetricsFetcher
from solar_platform.services.copilot.mapping import (
    _build_evidence_summary,
    _build_finding,
    _build_rich_text_items,
    _canonical_platform,
    _clean_identifier,
    _coerce_date,
    _coerce_float,
    _coerce_platform_tokens,
    _date_property,
    _default_legacy_mapping_path,
    _derive_pac_phase,
    _extract_asset_context,
    _extract_asset_name,
    _extract_capacity_kwp,
    _extract_ppa_rate_gbp_mwh,
    _extract_solis_day_energy_from_payload,
    _get_value,
    _load_legacy_mapping,
    _normalise_key,
    _number_property,
    _severity_sort_key,
    _text_property,
    _title_property,
)
from solar_platform.services.copilot.models import (
    DAILY_JSON_DATABASE_PROPERTIES,
    DAILY_JSON_DATABASE_TITLE,
    DATA_SOURCE_MATCH_FIELD_CANDIDATES,
    DEFAULT_DATA_SOURCE_MATCH_UPDATES,
    DEFAULT_PPA_RATE_SOURCE,
    INVERTER_METER_ALERT_CRITICAL_PCT,
    PAC_DATE_FIELD_CANDIDATES,
    PLATFORM_FIELD_CANDIDATES,
    SOURCE_CREDENTIAL_REPORT_ORDER,
    SOURCE_IDENTIFIER_FIELD_CANDIDATES,
    STARK_DAILY_DATABASE_TITLE,
    STARK_FUSION_VARIANCE_THRESHOLD_PCT,
    SUPPORTED_SOURCES,
    TARGET_PR_ASSUMPTION,
    TRIAGE_DATABASE_PROPERTIES,
    TRIAGE_DATABASE_TITLE,
    CurtailmentFetcher,
    DailyDataChecker,
    MatchResolution,
    SourceCheckResult,
    TriageAssessment,
)
from solar_platform.services.copilot.triage import _build_email_draft, _build_email_subject

logger = logging.getLogger(__name__)


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
        curtailment_fetcher: CurtailmentFetcher | Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.notion_service = notion_service or NotionAssetRegisterService(settings=self.settings)
        self.legacy_mapping = _load_legacy_mapping(legacy_mapping_path or _default_legacy_mapping_path())
        self.checkers = checkers or build_default_checkers()
        self.supported_sources = supported_sources
        self.daylight_metrics_fetcher = (
            daylight_metrics_fetcher
            or juggle_daylight_metrics_fetcher
            or RepositoryDaylightMetricsFetcher(prefer_archive_irradiance=True)
        )
        self.curtailment_fetcher = curtailment_fetcher or ExportLimitCurtailmentFetcher()

    @staticmethod
    def confirmed_data_source_matches() -> dict[str, str]:
        return dict(DEFAULT_DATA_SOURCE_MATCH_UPDATES)

    @staticmethod
    def describe_source_credential_preflight() -> dict[str, dict[str, Any]]:
        def _is_set(name: str) -> bool:
            return bool(str(os.getenv(name, "")).strip())

        def _missing_fields(*names: str) -> list[str]:
            return [name for name in names if not _is_set(name)]

        report: dict[str, dict[str, Any]] = {}

        juggle_fields = [name for name in ("JUGGLE_API_KEY", "EMIG_API_KEY") if _is_set(name)]
        report["juggle"] = {
            "status": "configured" if juggle_fields else "missing",
            "detail": (
                f"credentials present via {', '.join(juggle_fields)}"
                if juggle_fields
                else "set JUGGLE_API_KEY or EMIG_API_KEY"
            ),
            "present_fields": juggle_fields,
            "missing_fields": [] if juggle_fields else ["JUGGLE_API_KEY", "EMIG_API_KEY"],
        }

        solaredge_raw = str(os.getenv("SOLAREDGE_KEYS_JSON", "")).strip()
        solaredge_keys = _load_solaredge_site_keys()
        if solaredge_keys:
            solaredge_status = "configured"
            solaredge_detail = f"{len(solaredge_keys)} site-specific API key entries loaded"
            solaredge_missing_fields: list[str] = []
        elif solaredge_raw:
            solaredge_status = "partial"
            solaredge_detail = "SOLAREDGE_KEYS_JSON is set but empty or invalid"
            solaredge_missing_fields = []
        else:
            solaredge_status = "missing"
            solaredge_detail = "set SOLAREDGE_KEYS_JSON with site_id to api_key entries"
            solaredge_missing_fields = ["SOLAREDGE_KEYS_JSON"]
        report["solaredge"] = {
            "status": solaredge_status,
            "detail": solaredge_detail,
            "present_fields": ["SOLAREDGE_KEYS_JSON"] if solaredge_raw else [],
            "missing_fields": solaredge_missing_fields,
        }

        solis_missing = _missing_fields("SOLIS_KEY_ID", "SOLIS_KEY_SECRET")
        report["solis"] = {
            "status": "configured" if not solis_missing else "partial" if len(solis_missing) == 1 else "missing",
            "detail": (
                "credentials present via SOLIS_KEY_ID and SOLIS_KEY_SECRET"
                if not solis_missing
                else f"missing {', '.join(solis_missing)}"
            ),
            "present_fields": [name for name in ("SOLIS_KEY_ID", "SOLIS_KEY_SECRET") if _is_set(name)],
            "missing_fields": solis_missing,
        }

        enphase_missing = _missing_fields("ENPHASE_CLIENT_ID", "ENPHASE_CLIENT_SECRET", "ENPHASE_API_KEY")
        report["enphase"] = {
            "status": "configured" if not enphase_missing else "partial" if len(enphase_missing) < 3 else "missing",
            "detail": (
                "credentials present via ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET, and ENPHASE_API_KEY"
                if not enphase_missing
                else f"missing {', '.join(enphase_missing)}"
            ),
            "present_fields": [
                name
                for name in ("ENPHASE_CLIENT_ID", "ENPHASE_CLIENT_SECRET", "ENPHASE_API_KEY")
                if _is_set(name)
            ],
            "missing_fields": enphase_missing,
        }

        huawei_missing = _missing_fields("HUAWEI_USERNAME", "HUAWEI_PASSWORD")
        report["huawei"] = {
            "status": "configured" if not huawei_missing else "partial" if len(huawei_missing) == 1 else "missing",
            "detail": (
                "credentials present via HUAWEI_USERNAME and HUAWEI_PASSWORD"
                if not huawei_missing
                else f"missing {', '.join(huawei_missing)}"
            ),
            "present_fields": [name for name in ("HUAWEI_USERNAME", "HUAWEI_PASSWORD") if _is_set(name)],
            "missing_fields": huawei_missing,
        }

        sma_client_pair = _is_set("SMA_CLIENT_ID") and _is_set("SMA_CLIENT_SECRET")
        sma_user_pair = _is_set("SMA_USERNAME") and _is_set("SMA_PASSWORD")
        sma_present = [
            name
            for name in ("SMA_CLIENT_ID", "SMA_CLIENT_SECRET", "SMA_USERNAME", "SMA_PASSWORD")
            if _is_set(name)
        ]
        if sma_client_pair:
            sma_status = "configured"
            sma_detail = "credentials present via SMA_CLIENT_ID and SMA_CLIENT_SECRET"
            sma_missing_fields: list[str] = []
        elif sma_user_pair:
            sma_status = "configured"
            sma_detail = "credentials present via SMA_USERNAME and SMA_PASSWORD"
            sma_missing_fields = []
        elif sma_present:
            sma_status = "partial"
            sma_detail = "provide either SMA_CLIENT_ID and SMA_CLIENT_SECRET or SMA_USERNAME and SMA_PASSWORD"
            sma_missing_fields = [
                "SMA_CLIENT_ID/SMA_CLIENT_SECRET or SMA_USERNAME/SMA_PASSWORD"
            ]
        else:
            sma_status = "missing"
            sma_detail = "set SMA_CLIENT_ID and SMA_CLIENT_SECRET or SMA_USERNAME and SMA_PASSWORD"
            sma_missing_fields = [
                "SMA_CLIENT_ID/SMA_CLIENT_SECRET or SMA_USERNAME/SMA_PASSWORD"
            ]
        report["sma"] = {
            "status": sma_status,
            "detail": sma_detail,
            "present_fields": sma_present,
            "missing_fields": sma_missing_fields,
        }

        return {source: report[source] for source in SOURCE_CREDENTIAL_REPORT_ORDER}

    def _build_asset_processing_error_row(
        self,
        *,
        asset: dict[str, Any],
        today: date,
        target_date: date,
        error: Exception,
    ) -> dict[str, Any]:
        asset_name = _extract_asset_name(asset)
        pac_date = asset.get("_pac_date")
        pac_phase = str(asset.get("_pac_phase", _derive_pac_phase(pac_date, today)))
        error_message = str(error).strip() or error.__class__.__name__
        row: dict[str, Any] = {
            "asset_name": asset_name,
            "target_date": target_date.isoformat(),
            "pac_date": pac_date.isoformat() if isinstance(pac_date, date) else "",
            "pac_phase": pac_phase,
            "pac_in_past": pac_phase == "post_pac",
            "pac_date_missing": pac_phase == "unknown",
            "notion_page_id": asset.get("notion_page_id", ""),
            "notion_url": asset.get("notion_url", ""),
            "match_name": "",
            "match_method": "asset_processing_error",
            "match_confidence": 0.0,
            "resolved_source_types": "",
            "resolution_notes": error_message,
            "capacity_kwp": _extract_capacity_kwp(asset),
            "ppa_rate_gbp_mwh": None,
            "ppa_rate_source": "",
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
            "checked_sources": "",
            "sources_with_data": "",
            "has_any_data": False,
            "preferred_source": "",
        }
        row.update(_extract_asset_context(asset))
        for source in self.supported_sources:
            row[f"{source}_identifier"] = ""
            row[f"{source}_status"] = "not_checked"
            row[f"{source}_has_data"] = False
            row[f"{source}_sample_count"] = 0
            row[f"{source}_message"] = ""

        finding = _build_finding(
            finding_type="asset_processing_error",
            severity="high",
            confidence=0.95,
            summary="The audit failed while processing this asset.",
            recommended_action="Review the asset row, source mapping, and downstream service responses, then rerun the audit.",
            context={"error": error_message},
        )
        row["findings"] = [finding]
        row["finding_types"] = ["asset_processing_error"]
        row["actionable_finding_count"] = 1
        row["highest_finding_severity"] = "high"
        return row

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

    @staticmethod
    def _is_actionable_audit_candidate(
        *,
        pac_phase: str,
        identifiers: dict[str, str],
        resolution: MatchResolution,
    ) -> bool:
        if pac_phase != "post_pac":
            return False
        return bool(identifiers) or resolution.mapping is not None

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
        *,
        actionable_only: bool = False,
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
            try:
                asset_name = _extract_asset_name(asset)
                pac_date = asset.get("_pac_date")
                pac_phase = str(asset.get("_pac_phase", _derive_pac_phase(pac_date, today)))
                capacity_kwp = _extract_capacity_kwp(asset)
                ppa_rate_gbp_mwh, ppa_rate_source = _extract_ppa_rate_gbp_mwh(asset)
                resolution = self._resolve_match(asset)
                identifiers = self._infer_identifiers(asset, resolution)
                if actionable_only and not self._is_actionable_audit_candidate(
                    pac_phase=pac_phase,
                    identifiers=identifiers,
                    resolution=resolution,
                ):
                    continue
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
                    target_metrics = None
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
                        if ppa_rate_source == DEFAULT_PPA_RATE_SOURCE:
                            existing_message = str(row.get("target_revenue_message", "")).strip()
                            fallback_message = f"Using {DEFAULT_PPA_RATE_SOURCE} because the asset register PPA rate is missing or invalid."
                            row["target_revenue_message"] = (
                                f"{existing_message} | {fallback_message}"
                                if existing_message
                                else fallback_message
                            )

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

                if self.curtailment_fetcher is not None:
                    plant_uid = identifiers.get("juggle", "")
                    if plant_uid:
                        curtailment = self.curtailment_fetcher.get_day_curtailment(
                            plant_uid,
                            target_date,
                            ppa_rate_gbp_mwh=_coerce_float(row.get("ppa_rate_gbp_mwh")),
                            asset_name=asset_name,
                            match_name=resolution.match_name,
                            preferred_source=row.get("preferred_source", ""),
                            expected_daylight_kwh=row.get("expected_daylight_kwh"),
                            actual_daylight_kwh=row.get("actual_daylight_kwh"),
                        )
                        if inspect.isawaitable(curtailment):
                            curtailment = await curtailment
                        if isinstance(curtailment, dict):
                            for key in (
                                "curtailment_event_type",
                                "curtailment_generation_loss_kwh",
                                "curtailment_revenue_loss_gbp",
                                "curtailment_confidence",
                                "curtailment_message",
                            ):
                                row[key] = curtailment.get(key, row.get(key))
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
            except Exception as exc:
                logger.exception(
                    "asset_register_audit_asset_failed",
                    extra={
                        "asset_name": _extract_asset_name(asset),
                        "target_date": target_date.isoformat(),
                    },
                )
                rows.append(
                    self._build_asset_processing_error_row(
                        asset=asset,
                        today=today,
                        target_date=target_date,
                        error=exc,
                    )
                )

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
        return self._build_triage_records_from_dataset(dataset, include_healthy=include_healthy)

    # ------------------------------------------------------------------
    # Pre-publish validation
    # ------------------------------------------------------------------

    DAILY_REQUIRED_FIELDS: tuple[str, ...] = ("asset_name", "target_date", "match_method")
    TRIAGE_REQUIRED_FIELDS: tuple[str, ...] = ("row_key", "asset_name", "target_date", "issue_type")

    @staticmethod
    def validate_dataset_rows(
        rows: list[dict[str, Any]],
        required_fields: tuple[str, ...] | list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split *rows* into (valid, rejected) based on required-field presence."""
        valid: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for row in rows:
            missing = [f for f in required_fields if not str(row.get(f, "")).strip()]
            if missing:
                rejected.append({**row, "_validation_missing_fields": missing})
            else:
                valid.append(row)
        return valid, rejected

    def _build_triage_records_from_dataset(
        self,
        dataset: list[dict[str, Any]],
        *,
        include_healthy: bool = False,
    ) -> list[dict[str, Any]]:
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

        rows_to_publish, rejected = self.validate_dataset_rows(rows_to_publish, self.DAILY_REQUIRED_FIELDS)
        if rejected:
            logger.warning("daily_publish_validation_rejected: %d rows", len(rejected))

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
            asset_name = str(row.get("asset_name", "")).strip()
            row_key = f"{row.get('target_date', '')}|{row.get('asset_name', '')}"
            properties = {
                "Asset": _title_property(asset_name),
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
                "Finding Types": _text_property(", ".join(row.get("finding_types", []) or [])),
                "Actionable Finding Count": _number_property(row.get("actionable_finding_count")),
                "Highest Finding Severity": _text_property(row.get("highest_finding_severity")),
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
                "Trend Days Available": _number_property(row.get("trend_days_available")),
                "Trend Gen Mean (kWh)": _number_property(row.get("trend_gen_mean_kwh")),
                "Trend Availability Mean (%)": _number_property(row.get("trend_availability_mean")),
                "Daily JSON": _text_property(json.dumps(row, sort_keys=True)),
            }
            page_id = self.notion_service.upsert_database_page(
                database_id=target_database_id,
                match_field="Asset",
                match_value=asset_name or row_key,
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
        triage_records, rejected = self.validate_dataset_rows(triage_records, self.TRIAGE_REQUIRED_FIELDS)
        if rejected:
            logger.warning("triage_publish_validation_rejected: %d rows", len(rejected))

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

    # ------------------------------------------------------------------
    # 7-day rolling trend context
    # ------------------------------------------------------------------

    @staticmethod
    def enrich_dataset_with_rolling_trend(
        dataset: list[dict[str, Any]],
        output_dir: Path,
        reference_date: date,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Add 7-day rolling generation/availability trend fields to each row.

        Scans *output_dir* for cached daily JSON datasets from the preceding
        *lookback_days* and computes per-asset mean generation and availability.
        """
        history: dict[str, list[dict[str, Any]]] = {}
        for offset in range(1, lookback_days + 1):
            day = reference_date - timedelta(days=offset)
            cached = _load_cached_audit_dataset(output_dir, day)
            if not cached:
                continue
            for row in cached:
                name = str(row.get("asset_name", "")).strip()
                if name:
                    history.setdefault(name, []).append(row)

        for row in dataset:
            asset_name = str(row.get("asset_name", "")).strip()
            past_rows = history.get(asset_name, [])
            gen_values = [
                float(r["actual_daylight_kwh"])
                for r in past_rows
                if r.get("actual_daylight_kwh") is not None
            ]
            avail_values = [
                float(r["availability_ratio"])
                for r in past_rows
                if r.get("availability_ratio") is not None
            ]
            row["trend_days_available"] = len(past_rows)
            row["trend_gen_mean_kwh"] = (
                round(sum(gen_values) / len(gen_values), 2) if gen_values else None
            )
            row["trend_availability_mean"] = (
                round(sum(avail_values) / len(avail_values), 4) if avail_values else None
            )

        return dataset

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
        actionable_only=True,
    )
    target_date = (reference_date or datetime.now(UTC).date()) - timedelta(days=1)
    service.enrich_dataset_with_rolling_trend(dataset, output_dir, target_date)
    paths = service.write_dataset(dataset, output_dir=output_dir, target_date=target_date.isoformat())
    return {
        "target_date": target_date.isoformat(),
        "rows": len(dataset),
        "paths": paths,
        "dataset": dataset,
    }


def _resolve_audit_target_date(reference_date: date | None) -> date:
    return (reference_date or datetime.now(UTC).date()) - timedelta(days=1)


def _load_cached_audit_dataset(output_dir: Path, target_date: date) -> list[dict[str, Any]] | None:
    dataset_path = output_dir / f"asset_yesterday_dataset_{target_date.isoformat()}.json"
    if not dataset_path.exists():
        return None
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list):
        return None
    return [row for row in raw if isinstance(row, dict)]


async def run_asset_register_triage_publish(
    output_dir: Path,
    reference_date: date | None = None,
    force_refresh: bool = False,
    asset_filter: str | None = None,
    include_healthy: bool = False,
) -> dict[str, Any]:
    service = AssetRegisterAuditService()
    target_date = _resolve_audit_target_date(reference_date)
    dataset = _load_cached_audit_dataset(output_dir, target_date)
    if dataset is None:
        dataset = await service.build_yesterday_dataset(
            reference_date=reference_date,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
            actionable_only=True,
        )
    triage_records = service._build_triage_records_from_dataset(dataset, include_healthy=include_healthy)
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
    target_date = _resolve_audit_target_date(reference_date)
    dataset = _load_cached_audit_dataset(output_dir, target_date)
    if dataset is None:
        dataset = await service.build_yesterday_dataset(
            reference_date=reference_date,
            force_refresh=force_refresh,
            asset_filter=asset_filter,
            actionable_only=True,
        )
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
