"""
Offtaker consumption service for Juggle/EMIG plants.

Computes how much of the solar generation was consumed on-site by the offtaker
(vs exported to the grid) using the PV generation meter from the EMIG API.

Data source:
    EMIG API  GET /plant/{uid}            → discover PV meter device (type=PV)
              GET /meter/{id}/readings    → daily importEnergy + exportEnergy

Calculation (per day):
    generation_kwh  = Δ importEnergy  (array → PV meter, Wh → kWh)
    export_kwh      = Δ exportEnergy  (PV meter → grid, Wh → kWh)
    consumption_kwh = generation_kwh − export_kwh
    consumption_pct = consumption_kwh / generation_kwh × 100
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

EMIG_BASE_URL = "https://www.emig.co.uk/p/api"


@dataclass
class DailyConsumption:
    """Offtaker consumption breakdown for a single calendar day."""

    date: date
    generation_kwh: float       # importEnergy delta  (array → PV meter)
    export_kwh: float           # exportEnergy delta  (PV meter → grid)
    consumption_kwh: float      # generation_kwh − export_kwh
    consumption_pct: Optional[float]  # None when generation is zero


@dataclass
class OfftakerConsumptionResult:
    """Result of the offtaker consumption calculation for a date range."""

    plant_uid: str
    pv_meter_id: str
    start_date: date
    end_date: date
    days: List[DailyConsumption] = field(default_factory=list)
    total_generation_kwh: float = 0.0
    total_export_kwh: float = 0.0
    total_consumption_kwh: float = 0.0
    total_consumption_pct: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def compute_totals(self) -> None:
        self.total_generation_kwh = sum(d.generation_kwh for d in self.days)
        self.total_export_kwh = sum(d.export_kwh for d in self.days)
        self.total_consumption_kwh = sum(d.consumption_kwh for d in self.days)
        if self.total_generation_kwh > 0:
            self.total_consumption_pct = (
                self.total_consumption_kwh / self.total_generation_kwh * 100
            )


class OfftakerConsumptionService:
    """
    Fetches PV generation meter data from the EMIG API and computes how much
    solar generation was consumed on-site by the offtaker vs exported.

    The PV meter (device type ``PV``) records two cumulative energy counters:
      - ``importEnergy``: total energy flowing from the solar array into the meter
      - ``exportEnergy``: energy flowing from the meter out to the grid

    Offtaker consumption = importEnergy − exportEnergy.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = EMIG_BASE_URL,
    ) -> None:
        self.api_key = api_key or os.getenv("JUGGLE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"token {self.api_key}"})

    # ------------------------------------------------------------------
    # EMIG API helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self.base_url}{path}"
        resp = self._session.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def discover_pv_meter(self, plant_uid: str) -> str | None:
        """Return the EMIG ID of the PV generation meter for the plant."""
        try:
            data = self._get(f"/plant/{plant_uid}")
            for meter in data.get("meters", []):
                if meter.get("type") == "PV":
                    return meter.get("emigId")
        except Exception as exc:
            logger.warning(
                "discover_pv_meter_failed", extra={"plant_uid": plant_uid, "error": str(exc)}
            )
        return None

    def _fetch_meter_readings(self, emig_id: str, start: date, end: date) -> list:
        """Fetch all readings for one meter over the given date range."""
        params = {
            "startDate": start.strftime("%Y%m%d"),
            "endDate": end.strftime("%Y%m%d"),
        }
        try:
            data = self._get(f"/meter/{emig_id}/readings", params)
            if isinstance(data, dict):
                return data.get("readings", [])
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning(
                "fetch_meter_readings_failed",
                extra={"emig_id": emig_id, "error": str(exc)},
            )
            return []

    # ------------------------------------------------------------------
    # Energy calculation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_value(field_val: object) -> float:
        """Unwrap nested ``{value, unit}`` dicts returned by the EMIG API."""
        if isinstance(field_val, dict):
            return float(field_val.get("value", 0) or 0)
        try:
            return float(field_val or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _daily_delta_kwh(readings: list, energy_field: str) -> dict[date, float]:
        """
        Compute per-day energy (kWh) from a cumulative Wh counter.

        For each calendar day, daily energy = max(counter) − min(counter).
        Negative deltas (counter resets) are clamped to zero.

        Returns a ``{date: kwh}`` mapping.
        """
        points: list[tuple[datetime, float]] = []
        for r in readings:
            ts_raw = r.get("ts") or r.get("timestamp")
            val = r.get(energy_field)
            if not ts_raw or val is None:
                continue
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                wh = OfftakerConsumptionService._extract_value(val)
                points.append((ts, wh))
            except Exception:
                continue

        if not points:
            return {}

        points.sort(key=lambda x: x[0])

        day_values: dict[date, list[float]] = defaultdict(list)
        for ts, wh in points:
            day_values[ts.date()].append(wh)

        result: dict[date, float] = {}
        for d, values in day_values.items():
            delta_wh = max(values) - min(values)
            result[d] = max(0.0, delta_wh) / 1000.0  # Wh → kWh

        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_consumption(
        self,
        plant_uid: str,
        start_date: date,
        end_date: date,
        pv_meter_id: str | None = None,
    ) -> OfftakerConsumptionResult:
        """
        Compute offtaker consumption for a plant over a date range.

        Args:
            plant_uid:    Juggle plant UID (e.g. ``"ERS:00001"`` for Fylde).
            start_date:   Start of the reporting period (inclusive).
            end_date:     End of the reporting period (inclusive).
            pv_meter_id:  Override the PV meter EMIG ID; auto-discovered if
                          ``None``.

        Returns:
            :class:`OfftakerConsumptionResult` with per-day and aggregate
            figures.
        """
        warnings: list[str] = []

        # Discover PV meter if not provided
        meter_id = pv_meter_id or self.discover_pv_meter(plant_uid)
        if not meter_id:
            warnings.append(
                f"No PV generation meter (type=PV) found for plant {plant_uid}."
            )
            return OfftakerConsumptionResult(
                plant_uid=plant_uid,
                pv_meter_id="",
                start_date=start_date,
                end_date=end_date,
                warnings=warnings,
            )

        # Fetch readings from the EMIG API
        readings = self._fetch_meter_readings(meter_id, start_date, end_date)
        if not readings:
            warnings.append(
                f"No meter readings returned for {meter_id} "
                f"({start_date} – {end_date})."
            )
            return OfftakerConsumptionResult(
                plant_uid=plant_uid,
                pv_meter_id=meter_id,
                start_date=start_date,
                end_date=end_date,
                warnings=warnings,
            )

        # Compute daily energy deltas for both counters
        generation_by_day = self._daily_delta_kwh(readings, "importEnergy")
        export_by_day = self._daily_delta_kwh(readings, "exportEnergy")

        if not generation_by_day and not export_by_day:
            warnings.append(
                "Readings received but neither importEnergy nor exportEnergy "
                "fields were found. Check the meter type and API response."
            )

        # Build one record per day in the requested range
        days: list[DailyConsumption] = []
        current = start_date
        while current <= end_date:
            gen = generation_by_day.get(current, 0.0)
            exp = export_by_day.get(current, 0.0)
            cons = max(0.0, gen - exp)
            cons_pct = (cons / gen * 100) if gen > 0 else None
            days.append(
                DailyConsumption(
                    date=current,
                    generation_kwh=round(gen, 2),
                    export_kwh=round(exp, 2),
                    consumption_kwh=round(cons, 2),
                    consumption_pct=round(cons_pct, 1) if cons_pct is not None else None,
                )
            )
            current += timedelta(days=1)

        result = OfftakerConsumptionResult(
            plant_uid=plant_uid,
            pv_meter_id=meter_id,
            start_date=start_date,
            end_date=end_date,
            days=days,
            warnings=warnings,
        )
        result.compute_totals()
        return result
