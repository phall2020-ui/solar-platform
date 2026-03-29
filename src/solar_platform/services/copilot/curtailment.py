"""Export limit curtailment fetcher for the copilot package."""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from solar_platform.config import get_settings
from solar_platform.services.copilot.mapping import _coerce_float

logger = logging.getLogger(__name__)


class ExportLimitCurtailmentFetcher:
    LIMIT_THRESHOLD_PCT = 99.0

    def __init__(
        self,
        curtailment_engine: Any | None = None,
        export_limit_history_dir: Path | None = None,
    ) -> None:
        self.curtailment_engine = curtailment_engine
        self.export_limit_history_dir = export_limit_history_dir or self._default_export_limit_history_dir()
        self._export_limit_history_cache: pd.DataFrame | None = None
        self._curtailment_engine_db_available: bool | None = None

    @staticmethod
    def _default_export_limit_history_dir() -> Path:
        return Path(__file__).resolve().parents[4] / "platform" / "data" / "export_limits"

    def _curtailment_engine_is_available(self) -> bool:
        if self.curtailment_engine is not None:
            return True
        if self._curtailment_engine_db_available is None:
            import sys
            _shim = sys.modules.get("solar_platform.services.performance_copilot_asset_audit")
            _fn = getattr(_shim, "get_settings", None) if _shim is not None else None
            if _fn is None:
                _fn = get_settings
            self._curtailment_engine_db_available = _fn().db_path.exists()
        return self._curtailment_engine_db_available

    def _get_curtailment_engine(self) -> Any | None:
        if self.curtailment_engine is not None:
            return self.curtailment_engine
        if not self._curtailment_engine_is_available():
            return None
        from solar_platform.analysis.curtailment import CurtailmentEngine

        self.curtailment_engine = CurtailmentEngine()
        return self.curtailment_engine

    @staticmethod
    def _juggle_api_key() -> str:
        candidates = (
            os.getenv("JUGGLE_API_KEY", ""),
            os.getenv("EMIG_API_KEY", ""),
        )
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _juggle_base_url() -> str:
        return str(os.getenv("EMIG_API_URL") or os.getenv("JUGGLE_API_URL") or "https://www.emig.co.uk/p/api").rstrip("/")

    def _request_juggle_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        api_key = self._juggle_api_key()
        if not api_key:
            return None
        query_params = dict(params or {})
        query_params.setdefault("apikey", api_key)
        response = requests.get(
            f"{self._juggle_base_url()}{path}",
            headers={"Authorization": f"token {api_key}"},
            params=query_params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_export_limit_pct(reading: dict[str, Any]) -> float | None:
        candidates = (
            reading.get("exportLimit"),
            reading.get("exportLimitPct"),
            reading.get("exportLimitPercentage"),
            reading.get("export_limit_pct"),
        )
        for candidate in candidates:
            if isinstance(candidate, dict):
                value = _coerce_float(candidate.get("value"))
            else:
                value = _coerce_float(candidate)
            if value is not None:
                return value
        return None

    def _fetch_limitation_device_ids(self, plant_uid: str) -> list[str]:
        details = self._request_juggle_json(f"/plant/{plant_uid}")
        if not isinstance(details, dict):
            return []
        meters = details.get("meters", [])
        if not isinstance(meters, list):
            return []
        return [
            str(meter.get("emigId", "")).strip()
            for meter in meters
            if isinstance(meter, dict) and meter.get("type") == "LIMITATION" and str(meter.get("emigId", "")).strip()
        ]

    def _fetch_limitation_device_readings(self, emig_id: str, target_date: date) -> list[dict[str, Any]]:
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

    def _lookup_export_limit_api_signal(self, plant_uid: str, target_date: date) -> dict[str, Any] | None:
        try:
            limitation_ids = self._fetch_limitation_device_ids(plant_uid)
        except Exception:
            return None
        if not limitation_ids:
            return None

        readings: list[dict[str, Any]] = []
        for limitation_id in limitation_ids:
            try:
                readings.extend(self._fetch_limitation_device_readings(limitation_id, target_date))
            except Exception:
                continue

        if not readings:
            return None

        limit_values = [
            self._extract_export_limit_pct(reading)
            for reading in readings
            if isinstance(reading, dict)
        ]
        valid_values = [value for value in limit_values if value is not None]
        if not valid_values:
            return None

        curtailed_values = [value for value in valid_values if value < self.LIMIT_THRESHOLD_PCT]
        if not curtailed_values:
            return None

        return {
            "records": len(valid_values),
            "curtailed_records": len(curtailed_values),
            "min_limit_pct": min(curtailed_values),
        }

    @staticmethod
    def _estimate_generation_loss_kwh(expected_daylight_kwh: Any, actual_daylight_kwh: Any) -> float | None:
        expected = _coerce_float(expected_daylight_kwh)
        actual = _coerce_float(actual_daylight_kwh)
        if expected is None or actual is None or expected <= actual:
            return None
        return expected - actual

    @staticmethod
    def _build_curtailment_result(
        *,
        generation_loss_kwh: float | None,
        ppa_rate_gbp_mwh: float | None,
        confidence: float,
        message: str,
    ) -> dict[str, Any]:
        revenue_loss_gbp = None
        if generation_loss_kwh is not None and generation_loss_kwh > 0 and ppa_rate_gbp_mwh is not None:
            revenue_loss_gbp = (generation_loss_kwh / 1000.0) * ppa_rate_gbp_mwh
        return {
            "curtailment_event_type": "export_limit_curtailment",
            "curtailment_generation_loss_kwh": generation_loss_kwh,
            "curtailment_revenue_loss_gbp": revenue_loss_gbp,
            "curtailment_confidence": confidence,
            "curtailment_message": message,
        }

    def _load_export_limit_history(self) -> pd.DataFrame:
        if self._export_limit_history_cache is not None:
            return self._export_limit_history_cache

        history_dir = self.export_limit_history_dir
        if not history_dir.exists():
            self._export_limit_history_cache = pd.DataFrame()
            return self._export_limit_history_cache

        parquet_paths = sorted(history_dir.glob("*.parquet"))
        csv_paths = sorted(history_dir.glob("*.csv"))
        frames: list[pd.DataFrame] = []
        for candidate_paths in (parquet_paths, csv_paths):
            if not candidate_paths:
                continue
            frames = []
            for path in candidate_paths:
                try:
                    if path.suffix == ".parquet":
                        frame = pd.read_parquet(path)
                    else:
                        frame = pd.read_csv(path)
                except Exception:
                    continue
                if not frame.empty:
                    frames.append(frame)
            if frames:
                break

        if not frames:
            self._export_limit_history_cache = pd.DataFrame()
            return self._export_limit_history_cache

        history = pd.concat(frames, ignore_index=True)
        if "timestamp" in history.columns:
            history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True, errors="coerce")
            history = history.dropna(subset=["timestamp"]).copy()
        if "export_limit_pct" in history.columns:
            history["export_limit_pct"] = pd.to_numeric(history["export_limit_pct"], errors="coerce")
        if "is_curtailed" in history.columns:
            history["is_curtailed"] = history["is_curtailed"].apply(
                lambda value: str(value).strip().casefold() in {"1", "true", "t", "yes"}
            )
        self._export_limit_history_cache = history
        return history

    def _lookup_export_limit_history_signal(self, plant_uid: str, target_date: date) -> dict[str, Any] | None:
        history = self._load_export_limit_history()
        if history.empty or "plant_uid" not in history.columns or "timestamp" not in history.columns:
            return None

        day_rows = history[
            (history["plant_uid"].astype(str) == plant_uid)
            & (history["timestamp"].dt.date == target_date)
        ].copy()
        if day_rows.empty or "is_curtailed" not in day_rows.columns:
            return None

        curtailed_rows = day_rows[day_rows["is_curtailed"]].copy()
        if curtailed_rows.empty:
            return None

        min_limit_raw = curtailed_rows.get("export_limit_pct").min()
        min_limit_pct = float(min_limit_raw) if pd.notna(min_limit_raw) else None
        return {
            "records": int(len(day_rows)),
            "curtailed_records": int(len(curtailed_rows)),
            "min_limit_pct": min_limit_pct,
        }

    def get_day_curtailment(
        self,
        plant_uid: str,
        target_date: date,
        ppa_rate_gbp_mwh: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        ppa_rate = _coerce_float(ppa_rate_gbp_mwh)
        daylight_gap_kwh = self._estimate_generation_loss_kwh(
            kwargs.get("expected_daylight_kwh"),
            kwargs.get("actual_daylight_kwh"),
        )
        api_signal = self._lookup_export_limit_api_signal(plant_uid, target_date)
        if api_signal is not None:
            min_limit_pct = _coerce_float(api_signal.get("min_limit_pct"))
            min_limit_fragment = (
                f" Min observed limit was {min_limit_pct:.2f}%."
                if min_limit_pct is not None
                else ""
            )
            return self._build_curtailment_result(
                generation_loss_kwh=daylight_gap_kwh,
                ppa_rate_gbp_mwh=ppa_rate,
                confidence=0.95,
                message=(
                    f"Detected from live export-limit telemetry with {api_signal['curtailed_records']} curtailed intervals."
                    f"{min_limit_fragment}"
                ),
            )

        history_signal = self._lookup_export_limit_history_signal(plant_uid, target_date)
        if history_signal is not None:
            min_limit_pct = _coerce_float(history_signal.get("min_limit_pct"))
            min_limit_fragment = (
                f" Min observed limit was {min_limit_pct:.2f}%."
                if min_limit_pct is not None
                else ""
            )
            return self._build_curtailment_result(
                generation_loss_kwh=daylight_gap_kwh,
                ppa_rate_gbp_mwh=ppa_rate,
                confidence=0.95,
                message=(
                    f"Detected from export-limit history with {history_signal['curtailed_records']} curtailed intervals."
                    f"{min_limit_fragment}"
                ),
            )

        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        curtailment_engine = self._get_curtailment_engine()
        if curtailment_engine is None:
            return None
        try:
            result = curtailment_engine.run(plant_uid, start, end)
        except Exception:
            logger.exception(
                "curtailment_fetch_failed",
                extra={"plant_uid": plant_uid, "target_date": target_date.isoformat()},
            )
            return None

        summary = getattr(result, "summary", None)
        if not isinstance(summary, dict):
            return None

        detection_method = str(summary.get("detection_method", "")).strip()
        curtailed_records = int(summary.get("curtailed_records") or 0)
        generation_loss_kwh = _coerce_float(summary.get("curtailed_energy_kwh"))
        if detection_method != "export_limit" or curtailed_records <= 0:
            return None

        if generation_loss_kwh is None or generation_loss_kwh <= 0:
            generation_loss_kwh = daylight_gap_kwh
        curtailment_rate_pct = _coerce_float(summary.get("curtailment_rate_pct"))
        rate_fragment = (
            f" Curtailed coverage was {curtailment_rate_pct:.2f}%."
            if curtailment_rate_pct is not None
            else ""
        )
        return self._build_curtailment_result(
            generation_loss_kwh=generation_loss_kwh,
            ppa_rate_gbp_mwh=ppa_rate,
            confidence=0.95,
            message=(
                f"Detected from export-limit telemetry with {curtailed_records} curtailed intervals."
                f"{rate_fragment}"
            ),
        )
