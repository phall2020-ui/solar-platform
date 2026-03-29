"""DailyDataChecker protocol implementations for each inverter data source."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import requests

from solar_platform.services.copilot.mapping import _clean_identifier, _extract_solis_day_energy_from_payload
from solar_platform.services.copilot.models import DailyDataChecker, SourceCheckResult

logger = logging.getLogger(__name__)


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
