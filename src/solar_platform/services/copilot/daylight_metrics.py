"""Irradiance fetchers and repository-based daylight performance metrics fetcher."""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pandas as pd

from solar_platform.db.repository import PlantRepository, ReadingsRepository
from solar_platform.services.copilot.checkers import _load_solaredge_site_keys
from solar_platform.services.copilot.mapping import (
    _clean_identifier,
    _coerce_float,
    _normalise_key,
)
from solar_platform.services.copilot.models import TARGET_PR_ASSUMPTION
from solar_platform.services.site_locations import SiteLocationService
from solar_platform.weather.open_meteo import OpenMeteoArchiveClient, OpenMeteoClient

logger = logging.getLogger(__name__)


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
        prefer_archive_irradiance: bool = False,
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
        self.prefer_archive_irradiance = prefer_archive_irradiance
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

        plant_uid = ""
        irr_df = pd.DataFrame(columns=["hh_ts", "poa_interval_kwh_m2", "poa_wm2"])
        irradiance_errors: list[str] = []
        location = self._resolve_site_location(match_name=match_name, asset_name=asset_name)
        if self.prefer_archive_irradiance and location is not None:
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
            plant_uid = self._resolve_plant_uid(
                source=source,
                identifier=identifier,
                match_name=match_name,
                asset_name=asset_name,
            )
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
            base_message = (
                "No irradiance data found for the target day."
                if location is not None or plant_uid
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
