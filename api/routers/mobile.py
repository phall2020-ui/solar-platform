"""Mobile API router for the Solar Portfolio Dashboard.

Provides 6 endpoint groups optimised for mobile consumption.

All endpoints:
  - Use Optional fields and return sensible defaults — never raise 500 on
    missing / empty data.
  - Query DuckDB directly when service methods are unavailable.
  - Use httpx.AsyncClient for the Elexon SSP live-price API.

Endpoints
---------
GET /mobile/dashboard                     — portfolio snapshot
GET /mobile/sites/{plant_uid}             — site detail
GET /mobile/sites/{plant_uid}/inverters   — inverter list
GET /mobile/alerts                        — portfolio / plant alerts
GET /mobile/revenue                       — revenue with Elexon SSP
GET /mobile/sites/{plant_uid}/history     — per-site history
GET /mobile/portfolio/history             — aggregated portfolio history

Mount with prefix="/api/v1" in main.py.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from solar_platform.alerts.models import AlertSeverity, AlertStatus
from solar_platform.alerts.repository import AlertRepository
from solar_platform.db.engine import get_engine

logger = logging.getLogger("api.mobile")

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELEXON_SSP_BASE = (
    "https://data.elexon.co.uk/bmrs/api/v1/balancing/settlement/system-prices"
)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SiteOverview(BaseModel):
    plant_uid: str
    name: str
    platform: str  # juggle, solaredge, solis, fusionsolar, unknown
    capacity_kwp: float
    today_kwh: float
    current_kw: float
    pr_pct: Optional[float] = None
    status: str  # online, offline, standby, unknown
    alert_count: int
    last_reading: Optional[str] = None


class PortfolioSummary(BaseModel):
    total_sites: int
    total_capacity_mwp: float
    generation_today_mwh: float
    fleet_pr_pct: Optional[float] = None
    active_alerts: int
    critical_alerts: int
    sites_online: int
    sites_offline: int


class RevenueSummary(BaseModel):
    today_gbp: float
    current_ssp_gbp_mwh: Optional[float] = None
    mtd_gbp: float


class DashboardResponse(BaseModel):
    timestamp: str
    portfolio: PortfolioSummary
    sites: list[SiteOverview]
    revenue: RevenueSummary


class GenerationData(BaseModel):
    today_kwh: float
    today_mwh: float
    current_kw: float
    peak_kw: float
    mtd_mwh: Optional[float] = None
    ytd_mwh: Optional[float] = None


class PerformanceData(BaseModel):
    pr_pct: Optional[float] = None
    specific_yield: Optional[float] = None  # kWh/kWp
    irradiance_kwh_m2: Optional[float] = None


class InverterDevice(BaseModel):
    emig_id: str
    name: str
    status: str  # online, offline, standby, fault
    power_kw: float
    energy_today_kwh: float
    dc_voltage_v: Optional[float] = None
    temperature_c: Optional[float] = None
    last_reading: Optional[str] = None


class InverterSummary(BaseModel):
    total: int
    online: int
    offline: int
    standby: int
    devices: list[InverterDevice]


class AlarmItem(BaseModel):
    severity: str
    message: str
    device: Optional[str] = None
    since: str


class AlarmData(BaseModel):
    critical: int
    major: int
    minor: int
    warning: int
    items: list[AlarmItem]


class HourlyPoint(BaseModel):
    hour: str  # "06:00"
    kwh: float
    irradiance_wm2: Optional[float] = None


class SiteDetailResponse(BaseModel):
    plant_uid: str
    name: str
    platform: str
    capacity_kwp: float
    generation: GenerationData
    performance: PerformanceData
    inverters: InverterSummary
    alarms: AlarmData
    hourly_generation: list[HourlyPoint]
    last_updated: Optional[str] = None


class AlertResponse(BaseModel):
    id: str
    severity: str  # critical, major, minor, warning
    site_name: str
    plant_uid: str
    message: str
    device: Optional[str] = None
    since: str
    status: str  # active, acknowledged, resolved


class RevenueResponse(BaseModel):
    date: str
    today_gbp: float
    current_ssp_gbp_mwh: Optional[float] = None
    sites: list[dict[str, Any]]  # [{plant_uid, name, revenue_gbp}]
    hourly_ssp: list[dict[str, Any]]  # [{hour, ssp_gbp_mwh}]


class HistoryPoint(BaseModel):
    date: str
    kwh: float
    pr_pct: Optional[float] = None
    irradiance_kwh_m2: Optional[float] = None
    revenue_gbp: Optional[float] = None


# ---------------------------------------------------------------------------
# Small utility helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f  # guard NaN
    except (TypeError, ValueError):
        return default


def _safe_opt_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def _parse_payload(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _get_scalar(payload: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """Extract a scalar float from a payload dict, checking multiple key names."""
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("value")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return default


def _get_scalar_opt(payload: dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("value")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _is_daylight() -> bool:
    """Rough UTC daylight heuristic (06:00–20:00)."""
    return 6 <= datetime.now(timezone.utc).hour <= 20


def _infer_inverter_status(
    power_kw: float, has_recent_reading: bool, is_day: bool
) -> str:
    if not has_recent_reading:
        return "offline" if is_day else "standby"
    if power_kw > 0:
        return "online"
    return "standby"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _engine():
    return get_engine()


def _table_exists(table: str) -> bool:
    try:
        return _engine().table_exists(table)
    except Exception:
        return False


def _resolve_ts_col(conn: Any) -> str:
    """Return the timestamp column name actually present in the readings table."""
    try:
        cols = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='main' AND table_name='readings'"
            ).fetchall()
        }
        return "ts" if "ts" in cols else "timestamp"
    except Exception:
        return "ts"


def _resolve_plants_cols(conn: Any) -> set[str]:
    try:
        return {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='main' AND table_name='plants'"
            ).fetchall()
        }
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Data-access functions (sync — DuckDB is in-process)
# ---------------------------------------------------------------------------


def _get_all_plants() -> list[dict[str, Any]]:
    """Return all plants from the plants table as a list of dicts."""
    if not _table_exists("plants"):
        return []
    try:
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            cols = [
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='main' AND table_name='plants'"
                ).fetchall()
            ]
            rows = conn.execute("SELECT * FROM plants ORDER BY alias").fetchall()
            return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


def _get_plant_today_data(plant_uid: str) -> dict[str, Any]:
    """
    Query readings for today and return a summary dict:
      today_kwh, current_kw, peak_kw, pr_pct, last_ts,
      hourly_generation (list[{hour, kwh}]),
      emig_readings (dict[emig_id → list[{ts, power, energy, payload}]])
    """
    empty: dict[str, Any] = {
        "today_kwh": 0.0,
        "current_kw": 0.0,
        "peak_kw": 0.0,
        "pr_pct": None,
        "last_ts": None,
        "irradiance_kwh_m2": None,
        "hourly_generation": [],
        "emig_readings": {},
    }
    if not _table_exists("readings"):
        return empty
    try:
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            ts_col = _resolve_ts_col(conn)
            today_start = (
                datetime.now(timezone.utc)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .strftime("%Y-%m-%d %H:%M:%S")
            )
            rows = conn.execute(
                f"""
                SELECT emig_id, {ts_col}, payload
                FROM readings
                WHERE plant_uid = ?
                  AND CAST({ts_col} AS TIMESTAMP)
                      >= CAST(? AS TIMESTAMP)
                ORDER BY CAST({ts_col} AS TIMESTAMP) ASC
                """,
                [plant_uid, today_start],
            ).fetchall()

        if not rows:
            return empty

        # Build per-inverter reading list
        emig_data: dict[str, list[dict[str, Any]]] = {}
        last_ts: Any = None

        for emig_id, ts_val, raw_payload in rows:
            payload = _parse_payload(raw_payload)
            power_kw = _get_scalar(
                payload, "activePower", "power_kw", "pac", "p_ac", "powerKw"
            )
            # Daily-cumulative energy keys (prefer these — take max per inverter)
            energy_kwh = _get_scalar(
                payload,
                "energyProduction",
                "dailyEnergy",
                "dayEnergy",
                "energy_kwh",
                "e_grid",
            )
            if emig_id not in emig_data:
                emig_data[emig_id] = []
            emig_data[emig_id].append(
                {"ts": ts_val, "power": power_kw, "energy": energy_kwh, "payload": payload}
            )
            last_ts = ts_val

        # Aggregate today_kwh: take max per inverter (daily cumulative counter)
        total_kwh = 0.0
        for readings in emig_data.values():
            energies = [r["energy"] for r in readings if r["energy"] > 0]
            total_kwh += max(energies) if energies else 0.0

        # If all energy fields were zero, fall back to summing power × 0.5 h
        if total_kwh == 0.0:
            all_power_vals = [r["power"] for rlist in emig_data.values() for r in rlist]
            if all_power_vals:
                # Approximate: assume 30-min intervals
                total_kwh = sum(all_power_vals) * 0.5

        # Current kW = latest reading across all inverters
        last_readings = [rlist[-1] for rlist in emig_data.values() if rlist]
        current_kw = sum(r["power"] for r in last_readings)
        peak_kw = max(
            (r["power"] for rlist in emig_data.values() for r in rlist), default=0.0
        )

        # Hourly generation: bucket each reading into its half-hour slot
        hourly_power: dict[str, float] = defaultdict(float)
        for rlist in emig_data.values():
            for r in rlist:
                try:
                    ts_raw = r["ts"]
                    if isinstance(ts_raw, str):
                        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    elif hasattr(ts_raw, "hour"):
                        dt = ts_raw
                    else:
                        continue
                    slot = f"{dt.hour:02d}:{'30' if dt.minute >= 30 else '00'}"
                    hourly_power[slot] += r["power"]
                except Exception:
                    continue

        # Convert power accumulations to kWh (each slot was 30 min)
        hourly_generation = [
            {"hour": slot, "kwh": round(pwr * 0.5, 3)}
            for slot, pwr in sorted(hourly_power.items())
        ]

        return {
            "today_kwh": total_kwh,
            "current_kw": current_kw,
            "peak_kw": peak_kw,
            "pr_pct": None,  # PR requires irradiance — not computed here
            "irradiance_kwh_m2": None,
            "last_ts": str(last_ts) if last_ts is not None else None,
            "hourly_generation": hourly_generation,
            "emig_readings": emig_data,
        }
    except Exception:
        logger.exception("today_data_query_failed", extra={"plant_uid": plant_uid})
        return empty


def _get_generation_for_date(plant_uid: str, date_str: str) -> float:
    """Total generation kWh for a plant on a specific date (YYYY-MM-DD)."""
    if not _table_exists("readings"):
        return 0.0
    try:
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            ts_col = _resolve_ts_col(conn)
            rows = conn.execute(
                f"""
                SELECT emig_id, payload
                FROM readings
                WHERE plant_uid = ?
                  AND CAST({ts_col} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                  AND CAST({ts_col} AS TIMESTAMP) <= CAST(? AS TIMESTAMP)
                """,
                [plant_uid, f"{date_str} 00:00:00", f"{date_str} 23:59:59"],
            ).fetchall()
        emig_max: dict[str, float] = {}
        for emig_id, raw_payload in rows:
            payload = _parse_payload(raw_payload)
            energy = _get_scalar(
                payload,
                "energyProduction",
                "dailyEnergy",
                "dayEnergy",
                "energy_kwh",
                "e_grid",
            )
            if energy > emig_max.get(emig_id, 0.0):
                emig_max[emig_id] = energy
        # Fall back to power sum if no energy fields found
        total = sum(emig_max.values())
        if total == 0.0:
            # Re-query for power sum fallback
            engine2 = _engine()
            with engine2.connection(read_only=True) as conn2:
                ts_col2 = _resolve_ts_col(conn2)
                prows = conn2.execute(
                    f"""
                    SELECT payload
                    FROM readings
                    WHERE plant_uid = ?
                      AND CAST({ts_col2} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                      AND CAST({ts_col2} AS TIMESTAMP) <= CAST(? AS TIMESTAMP)
                    """,
                    [plant_uid, f"{date_str} 00:00:00", f"{date_str} 23:59:59"],
                ).fetchall()
            for (raw_payload,) in prows:
                payload = _parse_payload(raw_payload)
                power = _get_scalar(payload, "activePower", "power_kw", "pac", "p_ac")
                total += power * 0.5  # assume 30-min intervals
        return total
    except Exception:
        return 0.0


def _get_period_generation(plant_uid: str, start_dt: datetime) -> float:
    """Aggregate generation kWh from start_dt to now (MTD / YTD)."""
    if not _table_exists("readings"):
        return 0.0
    try:
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            ts_col = _resolve_ts_col(conn)
            rows = conn.execute(
                f"""
                SELECT emig_id, payload
                FROM readings
                WHERE plant_uid = ?
                  AND CAST({ts_col} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                """,
                [plant_uid, start_dt.strftime("%Y-%m-%d %H:%M:%S")],
            ).fetchall()
        emig_max: dict[str, float] = {}
        for emig_id, raw_payload in rows:
            payload = _parse_payload(raw_payload)
            # For longer periods the energy field may be totalEnergy / monthEnergy
            energy = _get_scalar(
                payload,
                "energyProduction",
                "totalEnergy",
                "monthEnergy",
                "yearEnergy",
                "energy_kwh",
                "e_grid",
            )
            if energy > emig_max.get(emig_id, 0.0):
                emig_max[emig_id] = energy
        # Power-sum fallback
        total = sum(emig_max.values())
        if total == 0.0:
            engine2 = _engine()
            with engine2.connection(read_only=True) as conn2:
                ts_col2 = _resolve_ts_col(conn2)
                prows = conn2.execute(
                    f"""
                    SELECT payload FROM readings
                    WHERE plant_uid = ?
                      AND CAST({ts_col2} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                    """,
                    [plant_uid, start_dt.strftime("%Y-%m-%d %H:%M:%S")],
                ).fetchall()
            for (raw_payload,) in prows:
                payload = _parse_payload(raw_payload)
                power = _get_scalar(payload, "activePower", "power_kw", "pac", "p_ac")
                total += power * 0.5
        return total
    except Exception:
        return 0.0


def _get_tariff_for_plant(plant_uid: str) -> Optional[float]:
    """Return the current fixed tariff rate (£/MWh) for a plant, or None."""
    if not _table_exists("plant_tariffs"):
        return None
    try:
        today_str = date.today().isoformat()
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT rate FROM plant_tariffs
                WHERE plant_uid = ?
                  AND start_date <= ?
                  AND (end_date IS NULL OR end_date >= ?)
                ORDER BY start_date DESC
                LIMIT 1
                """,
                [plant_uid, today_str, today_str],
            ).fetchall()
        if rows:
            return float(rows[0][0])
    except Exception:
        pass
    return None


def _calculate_revenue(
    kwh: float,
    ssp_gbp_mwh: Optional[float],
    tariff: Optional[float],
) -> float:
    """Revenue in GBP. Uses plant tariff if available, falls back to SSP."""
    mwh = kwh / 1000.0
    rate = tariff if tariff is not None else (ssp_gbp_mwh or 0.0)
    return mwh * rate


def _infer_site_status(today_data: dict[str, Any]) -> str:
    last_ts = today_data.get("last_ts")
    if not last_ts:
        return "unknown"
    try:
        ts_str = str(last_ts)[:19]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                last_dt = datetime.strptime(ts_str, fmt)
                break
            except ValueError:
                continue
        else:
            return "unknown"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_min = (now - last_dt).total_seconds() / 60
        if age_min > 60:
            return "offline" if _is_daylight() else "standby"
        if today_data.get("current_kw", 0.0) > 0:
            return "online"
        return "standby"
    except Exception:
        return "unknown"


def _build_inverter_devices(
    emig_readings: dict[str, list[dict[str, Any]]],
    plant_inverter_ids: list[str],
) -> list[InverterDevice]:
    """Build InverterDevice list from today's per-emig readings."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)
    is_day = _is_daylight()

    all_ids = sorted(set(plant_inverter_ids) | set(emig_readings.keys()))
    devices: list[InverterDevice] = []

    for emig_id in all_ids:
        readings = emig_readings.get(emig_id, [])
        if readings:
            last = readings[-1]
            payload = last["payload"]
            power_kw = last["power"]
            energy_kwh = _get_scalar(
                payload,
                "energyProduction",
                "dailyEnergy",
                "dayEnergy",
                "energy_kwh",
                "e_grid",
            )
            dc_voltage = _get_scalar_opt(
                payload, "dcVoltage", "dc_voltage_v", "pvVoltage", "vdc", "u_pv"
            )
            temperature = _get_scalar_opt(
                payload,
                "temperature",
                "temperature_c",
                "inverterTemperature",
                "temp",
            )
            ts_raw = last["ts"]
            # Determine recency
            try:
                if isinstance(ts_raw, str):
                    ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                elif hasattr(ts_raw, "tzinfo"):
                    ts_dt = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
                else:
                    ts_dt = datetime.min.replace(tzinfo=timezone.utc)
                recent = ts_dt >= cutoff
            except Exception:
                recent = False

            status = _infer_inverter_status(power_kw, recent, is_day)
            last_reading_str = str(ts_raw) if ts_raw else None
        else:
            power_kw = 0.0
            energy_kwh = 0.0
            dc_voltage = None
            temperature = None
            status = "offline" if is_day else "standby"
            last_reading_str = None

        devices.append(
            InverterDevice(
                emig_id=emig_id,
                name=emig_id,
                status=status,
                power_kw=power_kw,
                energy_today_kwh=energy_kwh,
                dc_voltage_v=dc_voltage,
                temperature_c=temperature,
                last_reading=last_reading_str,
            )
        )
    return devices


def _get_plant_alarms(plant_uid: str) -> AlarmData:
    """Fetch active alerts for a plant and map to mobile AlarmData schema."""
    try:
        repo = AlertRepository()
        alerts = repo.list_alerts(plant_uid=plant_uid, status=AlertStatus.ACTIVE)
        counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "warning": 0}
        items: list[AlarmItem] = []
        for a in alerts:
            sev = (a.severity.value or "").lower()
            if sev == "critical":
                counts["critical"] += 1
                mobile_sev = "critical"
            elif sev == "warning":
                counts["warning"] += 1
                mobile_sev = "warning"
            else:
                counts["minor"] += 1
                mobile_sev = "minor"
            since = (
                a.first_seen.isoformat()
                if hasattr(a.first_seen, "isoformat")
                else str(a.first_seen)
            )
            items.append(
                AlarmItem(
                    severity=mobile_sev,
                    message=a.title or a.description or "(no message)",
                    device=None,
                    since=since,
                )
            )
        return AlarmData(
            critical=counts["critical"],
            major=counts["major"],
            minor=counts["minor"],
            warning=counts["warning"],
            items=items,
        )
    except Exception:
        return AlarmData(critical=0, major=0, minor=0, warning=0, items=[])


def _get_alert_counts() -> tuple[int, int]:
    """Return (active_count, critical_count) across the whole portfolio."""
    try:
        repo = AlertRepository()
        active = repo.list_alerts(status=AlertStatus.ACTIVE)
        critical = sum(1 for a in active if a.severity == AlertSeverity.CRITICAL)
        return len(active), critical
    except Exception:
        return 0, 0


def _get_plant_alert_count(plant_uid: str) -> int:
    try:
        repo = AlertRepository()
        return len(repo.list_alerts(plant_uid=plant_uid, status=AlertStatus.ACTIVE))
    except Exception:
        return 0


def _parse_inverter_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(i) for i in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(i) for i in parsed]
        except Exception:
            pass
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


# ---------------------------------------------------------------------------
# Elexon SSP helper
# ---------------------------------------------------------------------------


async def _fetch_ssp(date_str: str) -> tuple[Optional[float], list[dict[str, Any]]]:
    """
    Fetch system sell price (£/MWh) from Elexon BMRS.

    Returns:
        (current_ssp, hourly_list)
        hourly_list items: {hour: "HH:MM", ssp_gbp_mwh: float}
    """
    try:
        url = f"{ELEXON_SSP_BASE}/{date_str}?format=json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning("elexon_non_200", extra={"status": resp.status_code, "url": url})
            return None, []

        data = resp.json()
        items: list[dict[str, Any]] = data.get("data", [])
        if not items:
            return None, []

        # Build hourly summary from settlement periods (48 × 30 min per day)
        hourly: list[dict[str, Any]] = []
        for item in items:
            sp_raw = item.get("settlementPeriod")
            price_raw = item.get("systemSellPrice") or item.get("ssp")
            if sp_raw is None or price_raw is None:
                continue
            sp = int(sp_raw)
            half_hour_idx = sp - 1
            h = half_hour_idx // 2
            m = 30 if half_hour_idx % 2 else 0
            hourly.append({"hour": f"{h:02d}:{m:02d}", "ssp_gbp_mwh": float(price_raw)})

        # Find current settlement period
        now = datetime.now(timezone.utc)
        minutes = now.hour * 60 + now.minute
        current_sp = (minutes // 30) + 1
        current_ssp: Optional[float] = None
        for item in items:
            if item.get("settlementPeriod") == current_sp:
                raw = item.get("systemSellPrice") or item.get("ssp")
                if raw is not None:
                    current_ssp = float(raw)
                break
        # Use last available if current period not published yet
        if current_ssp is None and hourly:
            current_ssp = hourly[-1]["ssp_gbp_mwh"]

        return current_ssp, hourly

    except Exception:
        logger.warning("elexon_fetch_failed", exc_info=True)
        return None, []


# ---------------------------------------------------------------------------
# Endpoint 1 — GET /mobile/dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/dashboard",
    response_model=DashboardResponse,
    summary="Portfolio-level snapshot",
)
async def mobile_dashboard() -> DashboardResponse:
    """Return a portfolio snapshot for the mobile home screen."""
    today_str = date.today().isoformat()
    current_ssp, _ = await _fetch_ssp(today_str)

    plants = _get_all_plants()
    active_alerts, critical_alerts = _get_alert_counts()

    sites: list[SiteOverview] = []
    total_kwh = 0.0
    total_cap_kw = 0.0
    total_revenue = 0.0
    mtd_revenue = 0.0
    sites_online = 0
    sites_offline = 0

    now_utc = datetime.now(timezone.utc)
    mtd_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for plant in plants:
        uid = str(plant.get("plant_uid", ""))
        name = str(plant.get("alias") or plant.get("name") or uid)
        platform = str(
            plant.get("platform")
            or plant.get("source")
            or plant.get("integration")
            or "unknown"
        )
        capacity_kwp = _safe_float(
            plant.get("dc_size_kw")
            or plant.get("capacity_kwp")
            or plant.get("capacity_kw"),
            0.0,
        )
        total_cap_kw += capacity_kwp

        today_data = _get_plant_today_data(uid)
        plant_kwh = today_data["today_kwh"]
        total_kwh += plant_kwh

        status = _infer_site_status(today_data)
        if status == "online":
            sites_online += 1
        elif status == "offline":
            sites_offline += 1

        tariff = _get_tariff_for_plant(uid)
        total_revenue += _calculate_revenue(plant_kwh, current_ssp, tariff)

        mtd_kwh = _get_period_generation(uid, mtd_start)
        mtd_revenue += _calculate_revenue(mtd_kwh, current_ssp, tariff)

        alert_count = _get_plant_alert_count(uid)

        sites.append(
            SiteOverview(
                plant_uid=uid,
                name=name,
                platform=platform,
                capacity_kwp=capacity_kwp,
                today_kwh=round(plant_kwh, 2),
                current_kw=round(today_data["current_kw"], 2),
                pr_pct=today_data.get("pr_pct"),
                status=status,
                alert_count=alert_count,
                last_reading=today_data.get("last_ts"),
            )
        )

    portfolio = PortfolioSummary(
        total_sites=len(plants),
        total_capacity_mwp=round(total_cap_kw / 1000.0, 3),
        generation_today_mwh=round(total_kwh / 1000.0, 3),
        fleet_pr_pct=None,  # Requires irradiance data — not computed here
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        sites_online=sites_online,
        sites_offline=sites_offline,
    )

    revenue = RevenueSummary(
        today_gbp=round(total_revenue, 2),
        current_ssp_gbp_mwh=current_ssp,
        mtd_gbp=round(mtd_revenue, 2),
    )

    return DashboardResponse(
        timestamp=_utcnow_iso(),
        portfolio=portfolio,
        sites=sites,
        revenue=revenue,
    )


# ---------------------------------------------------------------------------
# Endpoint 2 — GET /mobile/sites/{plant_uid}
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/sites/{plant_uid}",
    response_model=SiteDetailResponse,
    summary="Single-site detail view",
)
async def site_detail(plant_uid: str) -> SiteDetailResponse:
    """Return comprehensive detail for one site."""
    plants = _get_all_plants()
    plant = next(
        (p for p in plants if str(p.get("plant_uid", "")) == plant_uid), {}
    )

    name = str(plant.get("alias") or plant.get("name") or plant_uid)
    platform = str(
        plant.get("platform")
        or plant.get("source")
        or plant.get("integration")
        or "unknown"
    )
    capacity_kwp = _safe_float(
        plant.get("dc_size_kw")
        or plant.get("capacity_kwp")
        or plant.get("capacity_kw"),
        0.0,
    )
    inverter_ids = _parse_inverter_ids(plant.get("inverter_ids"))

    today_data = _get_plant_today_data(plant_uid)

    now_utc = datetime.now(timezone.utc)
    mtd_kwh = _get_period_generation(
        plant_uid,
        now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    )
    ytd_kwh = _get_period_generation(
        plant_uid,
        now_utc.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
    )

    generation = GenerationData(
        today_kwh=round(today_data["today_kwh"], 2),
        today_mwh=round(today_data["today_kwh"] / 1000.0, 4),
        current_kw=round(today_data["current_kw"], 2),
        peak_kw=round(today_data["peak_kw"], 2),
        mtd_mwh=round(mtd_kwh / 1000.0, 3) if mtd_kwh else None,
        ytd_mwh=round(ytd_kwh / 1000.0, 3) if ytd_kwh else None,
    )

    spec_yield = (
        round(today_data["today_kwh"] / capacity_kwp, 3)
        if capacity_kwp > 0
        else None
    )
    performance = PerformanceData(
        pr_pct=today_data.get("pr_pct"),
        specific_yield=spec_yield,
        irradiance_kwh_m2=today_data.get("irradiance_kwh_m2"),
    )

    devices = _build_inverter_devices(today_data["emig_readings"], inverter_ids)
    inverters = InverterSummary(
        total=len(devices),
        online=sum(1 for d in devices if d.status == "online"),
        offline=sum(1 for d in devices if d.status == "offline"),
        standby=sum(1 for d in devices if d.status == "standby"),
        devices=devices,
    )

    alarms = _get_plant_alarms(plant_uid)

    hourly = [
        HourlyPoint(hour=h["hour"], kwh=h["kwh"])
        for h in today_data["hourly_generation"]
    ]

    return SiteDetailResponse(
        plant_uid=plant_uid,
        name=name,
        platform=platform,
        capacity_kwp=capacity_kwp,
        generation=generation,
        performance=performance,
        inverters=inverters,
        alarms=alarms,
        hourly_generation=hourly,
        last_updated=today_data.get("last_ts"),
    )


# ---------------------------------------------------------------------------
# Endpoint 3 — GET /mobile/sites/{plant_uid}/inverters
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/sites/{plant_uid}/inverters",
    response_model=list[InverterDevice],
    summary="Inverter device list for a site",
)
async def site_inverters(plant_uid: str) -> list[InverterDevice]:
    """Return per-inverter status and live readings for a site."""
    plants = _get_all_plants()
    plant = next(
        (p for p in plants if str(p.get("plant_uid", "")) == plant_uid), {}
    )
    inverter_ids = _parse_inverter_ids(plant.get("inverter_ids"))
    today_data = _get_plant_today_data(plant_uid)
    return _build_inverter_devices(today_data["emig_readings"], inverter_ids)


# ---------------------------------------------------------------------------
# Endpoint 4 — GET /mobile/alerts
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/alerts",
    response_model=list[AlertResponse],
    summary="Portfolio / site alert list",
)
async def list_mobile_alerts(
    severity: Optional[str] = Query(
        None,
        description="Filter by severity: critical, warning, info",
    ),
    status: Optional[str] = Query(
        "active",
        description="Filter by status: active, acknowledged, resolved",
    ),
    plant_uid: Optional[str] = Query(None, description="Filter to a single site"),
) -> list[AlertResponse]:
    """Return active (or filtered) alerts across the portfolio."""
    try:
        repo = AlertRepository()

        status_enum: Optional[AlertStatus] = None
        if status:
            try:
                status_enum = AlertStatus(status.lower())
            except ValueError:
                status_enum = AlertStatus.ACTIVE

        severity_enum: Optional[AlertSeverity] = None
        if severity:
            try:
                severity_enum = AlertSeverity(severity.lower())
            except ValueError:
                pass

        alerts = repo.list_alerts(
            plant_uid=plant_uid,
            status=status_enum,
            severity=severity_enum,
        )

        plants = _get_all_plants()
        uid_to_name = {
            str(p.get("plant_uid", "")): str(p.get("alias") or p.get("name") or "")
            for p in plants
        }

        results: list[AlertResponse] = []
        for a in alerts:
            since = (
                a.first_seen.isoformat()
                if hasattr(a.first_seen, "isoformat")
                else str(a.first_seen)
            )
            results.append(
                AlertResponse(
                    id=a.id,
                    severity=a.severity.value,
                    site_name=uid_to_name.get(a.plant_uid, a.plant_uid),
                    plant_uid=a.plant_uid,
                    message=a.title or a.description or "(no message)",
                    device=None,
                    since=since,
                    status=a.status.value,
                )
            )
        return results
    except Exception:
        logger.warning("alerts_list_failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Endpoint 5 — GET /mobile/revenue
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/revenue",
    response_model=RevenueResponse,
    summary="Revenue summary with live Elexon SSP",
)
async def get_revenue(
    date_param: Optional[str] = Query(
        None,
        alias="date",
        description="Date to calculate revenue for (YYYY-MM-DD). Defaults to today.",
    ),
) -> RevenueResponse:
    """Return per-site revenue and live Elexon SSP data."""
    target_date = date_param or date.today().isoformat()
    current_ssp, hourly_ssp = await _fetch_ssp(target_date)

    plants = _get_all_plants()
    total_revenue = 0.0
    site_revenues: list[dict[str, Any]] = []
    today_str = date.today().isoformat()

    for plant in plants:
        uid = str(plant.get("plant_uid", ""))
        name = str(plant.get("alias") or plant.get("name") or uid)

        if target_date == today_str:
            today_data = _get_plant_today_data(uid)
            kwh = today_data["today_kwh"]
        else:
            kwh = _get_generation_for_date(uid, target_date)

        tariff = _get_tariff_for_plant(uid)
        rev = _calculate_revenue(kwh, current_ssp, tariff)
        total_revenue += rev
        site_revenues.append(
            {"plant_uid": uid, "name": name, "revenue_gbp": round(rev, 2)}
        )

    return RevenueResponse(
        date=target_date,
        today_gbp=round(total_revenue, 2),
        current_ssp_gbp_mwh=current_ssp,
        sites=site_revenues,
        hourly_ssp=hourly_ssp,
    )


# ---------------------------------------------------------------------------
# Shared history query
# ---------------------------------------------------------------------------


def _get_history(
    plant_uid: str, start: str, end: str, interval: str
) -> list[HistoryPoint]:
    """Aggregate generation history for a single plant."""
    if not _table_exists("readings"):
        return []
    try:
        engine = _engine()
        with engine.connection(read_only=True) as conn:
            ts_col = _resolve_ts_col(conn)

            if interval == "monthly":
                date_trunc = f"STRFTIME(CAST({ts_col} AS TIMESTAMP), '%Y-%m-01')"
            elif interval == "weekly":
                date_trunc = (
                    f"DATE_TRUNC('week', CAST({ts_col} AS TIMESTAMP))::VARCHAR"
                )
            else:
                date_trunc = f"STRFTIME(CAST({ts_col} AS TIMESTAMP), '%Y-%m-%d')"

            rows = conn.execute(
                f"""
                SELECT {date_trunc} AS period, emig_id, payload
                FROM readings
                WHERE plant_uid = ?
                  AND CAST({ts_col} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                  AND CAST({ts_col} AS TIMESTAMP) <= CAST(? AS TIMESTAMP)
                ORDER BY CAST({ts_col} AS TIMESTAMP) ASC
                """,
                [plant_uid, f"{start} 00:00:00", f"{end} 23:59:59"],
            ).fetchall()

        # period → emig_id → max cumulative energy
        period_emig: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for period, emig_id, raw_payload in rows:
            period_str = str(period)
            payload = _parse_payload(raw_payload)
            energy = _get_scalar(
                payload,
                "energyProduction",
                "dailyEnergy",
                "dayEnergy",
                "energy_kwh",
                "e_grid",
            )
            if energy > period_emig[period_str][emig_id]:
                period_emig[period_str][emig_id] = energy

        use_power_fallback = not any(
            any(v > 0 for v in em.values()) for em in period_emig.values()
        )

        if use_power_fallback:
            # Sum power × 0.5 h per period
            period_kwh: dict[str, float] = defaultdict(float)
            for _, _, raw_payload in rows:
                # Re-iterate rows — we need period again so we re-read them
                pass
            # Re-query to get power sums properly
            engine2 = _engine()
            with engine2.connection(read_only=True) as conn2:
                ts_col2 = _resolve_ts_col(conn2)
                if interval == "monthly":
                    dt2 = f"STRFTIME(CAST({ts_col2} AS TIMESTAMP), '%Y-%m-01')"
                elif interval == "weekly":
                    dt2 = f"DATE_TRUNC('week', CAST({ts_col2} AS TIMESTAMP))::VARCHAR"
                else:
                    dt2 = f"STRFTIME(CAST({ts_col2} AS TIMESTAMP), '%Y-%m-%d')"
                prows = conn2.execute(
                    f"""
                    SELECT {dt2} AS period, payload
                    FROM readings
                    WHERE plant_uid = ?
                      AND CAST({ts_col2} AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
                      AND CAST({ts_col2} AS TIMESTAMP) <= CAST(? AS TIMESTAMP)
                    ORDER BY CAST({ts_col2} AS TIMESTAMP) ASC
                    """,
                    [plant_uid, f"{start} 00:00:00", f"{end} 23:59:59"],
                ).fetchall()
            for period_val, raw_payload in prows:
                payload = _parse_payload(raw_payload)
                power = _get_scalar(
                    payload, "activePower", "power_kw", "pac", "p_ac"
                )
                period_kwh[str(period_val)] += power * 0.5

            tariff = _get_tariff_for_plant(plant_uid)
            return [
                HistoryPoint(
                    date=period,
                    kwh=round(kwh_val, 2),
                    revenue_gbp=round(kwh_val / 1000.0 * tariff, 2)
                    if tariff is not None
                    else None,
                )
                for period, kwh_val in sorted(period_kwh.items())
            ]

        tariff = _get_tariff_for_plant(plant_uid)
        results: list[HistoryPoint] = []
        for period in sorted(period_emig.keys()):
            total_kwh = sum(period_emig[period].values())
            results.append(
                HistoryPoint(
                    date=period,
                    kwh=round(total_kwh, 2),
                    pr_pct=None,
                    irradiance_kwh_m2=None,
                    revenue_gbp=round(total_kwh / 1000.0 * tariff, 2)
                    if tariff is not None
                    else None,
                )
            )
        return results

    except Exception:
        logger.exception("history_query_failed", extra={"plant_uid": plant_uid})
        return []


# ---------------------------------------------------------------------------
# Endpoint 6a — GET /mobile/sites/{plant_uid}/history
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/sites/{plant_uid}/history",
    response_model=list[HistoryPoint],
    summary="Per-site historical generation",
)
async def site_history(
    plant_uid: str,
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    interval: str = Query(
        "daily",
        description="Aggregation interval: daily | weekly | monthly",
    ),
) -> list[HistoryPoint]:
    """Return aggregated historical generation for a single site."""
    return _get_history(plant_uid, start, end, interval)


# ---------------------------------------------------------------------------
# Endpoint 6b — GET /mobile/portfolio/history
# ---------------------------------------------------------------------------


@router.get(
    "/mobile/portfolio/history",
    response_model=list[HistoryPoint],
    summary="Portfolio historical generation (all sites aggregated)",
)
async def portfolio_history(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    interval: str = Query(
        "daily",
        description="Aggregation interval: daily | weekly | monthly",
    ),
) -> list[HistoryPoint]:
    """Return aggregated historical generation across all sites."""
    plants = _get_all_plants()
    if not plants:
        return []

    aggregated: dict[str, HistoryPoint] = {}
    for plant in plants:
        uid = str(plant.get("plant_uid", ""))
        for point in _get_history(uid, start, end, interval):
            if point.date in aggregated:
                existing = aggregated[point.date]
                aggregated[point.date] = HistoryPoint(
                    date=point.date,
                    kwh=existing.kwh + point.kwh,
                    pr_pct=None,  # Cannot simply aggregate PR
                    irradiance_kwh_m2=None,
                    revenue_gbp=(
                        (existing.revenue_gbp or 0.0) + (point.revenue_gbp or 0.0)
                    )
                    if (
                        existing.revenue_gbp is not None
                        or point.revenue_gbp is not None
                    )
                    else None,
                )
            else:
                aggregated[point.date] = point

    return sorted(aggregated.values(), key=lambda p: p.date)
