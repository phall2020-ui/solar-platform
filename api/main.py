"""Read-only FastAPI application for the solar portfolio.

Exposes plant, readings, and portfolio summary endpoints.  FastAPI and
uvicorn are optional dependencies — the module degrades gracefully if they
are not installed.

Run standalone::

    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger("api.main")

# ---------------------------------------------------------------------------
# Guard: FastAPI may not be installed
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel
except ImportError:
    logger.warning("fastapi_not_installed")
    # Expose a placeholder so imports don't break
    app = None  # type: ignore[assignment]
    raise SystemExit(
        "FastAPI is not installed. Install it with: pip install fastapi uvicorn"
    )


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "healthy"


class PlantOut(BaseModel):
    plant_uid: str
    alias: str | None = None
    capacity_kwp: float | None = None


class ReadingOut(BaseModel):
    timestamp: str
    generation_kwh: float | None = None
    irradiance: float | None = None
    pr: float | None = None


class PortfolioSummary(BaseModel):
    total_plants: int = 0
    total_capacity_kwp: float = 0.0
    total_generation_kwh: float = 0.0


class OfftakerConsumptionEntry(BaseModel):
    date: str
    generation_kwh: float
    export_kwh: float
    consumption_kwh: float
    consumption_pct: float | None = None


class OfftakerConsumptionResponse(BaseModel):
    plant_uid: str
    pv_meter_id: str
    start_date: str
    end_date: str
    total_generation_kwh: float
    total_export_kwh: float
    total_consumption_kwh: float
    total_consumption_pct: float | None = None
    days: list[OfftakerConsumptionEntry]
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Solar Portfolio API",
    version="1.0.0",
    description="Read-only API for solar portfolio data.",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
try:
    from api.routers.mobile import router as mobile_router

    app.include_router(mobile_router, prefix="/api/v1", tags=["mobile"])
except Exception as _router_exc:  # pragma: no cover
    logger.warning("mobile_router_not_loaded", error=str(_router_exc))


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="healthy")


@app.get("/api/v1/plants", response_model=list[PlantOut], tags=["plants"])
def list_plants() -> list[PlantOut]:
    """Return all plants in the portfolio."""
    from solar_platform.db.engine import get_engine

    engine = get_engine()
    if not engine.table_exists("plants"):
        return []

    rows = engine.execute("SELECT * FROM plants ORDER BY alias")
    columns = _get_columns(engine, "plants")

    results: list[PlantOut] = []
    for row in rows:
        data = dict(zip(columns, row))
        results.append(
            PlantOut(
                plant_uid=str(data.get("plant_uid", "")),
                alias=data.get("alias"),
                capacity_kwp=_safe_float(data.get("capacity_kwp")),
            )
        )
    return results


@app.get("/api/v1/plants/{plant_uid}/readings", response_model=list[ReadingOut], tags=["readings"])
def get_readings(
    plant_uid: str,
    start: str | None = Query(None, description="Start date/time ISO format"),
    end: str | None = Query(None, description="End date/time ISO format"),
    limit: int = Query(1000, ge=1, le=50_000),
) -> list[ReadingOut]:
    """Return readings for a specific plant with optional date filters."""
    from datetime import datetime

    from solar_platform.db.repository import ReadingsRepository

    repo = ReadingsRepository()

    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end)

    try:
        df = repo.get_readings(
            plant_uid=plant_uid,
            start=start_dt,
            end=end_dt,
            limit=limit,
        )
    except Exception as exc:
        logger.error("readings_query_failed", plant_uid=plant_uid, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve readings.") from exc

    if df.empty:
        return []

    # Resolve column names
    ts_col = _pick_col(df, ("timestamp", "ts", "date"))
    gen_col = _pick_col(df, ("generation_kwh", "gen_kwh", "kwh"))
    irr_col = _pick_col(df, ("irradiance", "ghi", "poa_irradiance"))
    pr_col = _pick_col(df, ("pr", "performance_ratio"))

    results: list[ReadingOut] = []
    for _, row in df.iterrows():
        ts_val = row.get(ts_col) if ts_col else None
        results.append(
            ReadingOut(
                timestamp=str(ts_val) if ts_val is not None else "",
                generation_kwh=_safe_float(row.get(gen_col) if gen_col else None),
                irradiance=_safe_float(row.get(irr_col) if irr_col else None),
                pr=_safe_float(row.get(pr_col) if pr_col else None),
            )
        )
    return results


@app.get(
    "/api/v1/plants/{plant_uid}/offtaker-consumption",
    response_model=OfftakerConsumptionResponse,
    tags=["consumption"],
)
def offtaker_consumption(
    plant_uid: str,
    start: str | None = Query(None, description="Start date YYYY-MM-DD (default: 30 days ago)"),
    end: str | None = Query(None, description="End date YYYY-MM-DD (default: today)"),
    pv_meter: str | None = Query(None, description="Override PV meter EMIG ID (auto-discovered if omitted)"),
) -> OfftakerConsumptionResponse:
    """Return how much solar generation was consumed on-site by the offtaker vs exported to the grid.

    Uses the PV generation meter (EMIG API, device type=PV) which records:
      - ``importEnergy``: cumulative energy from the solar array into the meter (total generation)
      - ``exportEnergy``: cumulative energy from the meter out to the grid

    ``consumption_kwh = generation_kwh − export_kwh``
    """
    from datetime import date, timedelta

    from solar_platform.monitoring.offtaker_consumption import OfftakerConsumptionService

    today = date.today()
    end_d = _parse_date(end) or today
    start_d = _parse_date(start) or (end_d - timedelta(days=30))

    svc = OfftakerConsumptionService()
    result = svc.get_consumption(
        plant_uid=plant_uid,
        start_date=start_d,
        end_date=end_d,
        pv_meter_id=pv_meter,
    )

    return OfftakerConsumptionResponse(
        plant_uid=result.plant_uid,
        pv_meter_id=result.pv_meter_id,
        start_date=str(result.start_date),
        end_date=str(result.end_date),
        total_generation_kwh=round(result.total_generation_kwh, 2),
        total_export_kwh=round(result.total_export_kwh, 2),
        total_consumption_kwh=round(result.total_consumption_kwh, 2),
        total_consumption_pct=(
            round(result.total_consumption_pct, 1)
            if result.total_consumption_pct is not None
            else None
        ),
        days=[
            OfftakerConsumptionEntry(
                date=str(d.date),
                generation_kwh=d.generation_kwh,
                export_kwh=d.export_kwh,
                consumption_kwh=d.consumption_kwh,
                consumption_pct=d.consumption_pct,
            )
            for d in result.days
        ],
        warnings=result.warnings,
    )


@app.get("/api/v1/portfolio/summary", response_model=PortfolioSummary, tags=["portfolio"])
def portfolio_summary() -> PortfolioSummary:
    """Return high-level KPIs for the whole portfolio."""
    from solar_platform.db.engine import get_engine

    engine = get_engine()

    total_plants = 0
    total_cap = 0.0
    total_gen = 0.0

    if engine.table_exists("plants"):
        rows = engine.execute("SELECT COUNT(*), COALESCE(SUM(capacity_kwp), 0) FROM plants")
        if rows:
            total_plants = int(rows[0][0])
            total_cap = float(rows[0][1])

    if engine.table_exists("readings"):
        rows = engine.execute("SELECT COALESCE(SUM(generation_kwh), 0) FROM readings")
        if rows:
            total_gen = float(rows[0][0])

    return PortfolioSummary(
        total_plants=total_plants,
        total_capacity_kwp=total_cap,
        total_generation_kwh=total_gen,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_columns(engine: object, table: str) -> list[str]:
    """Return column names for a table."""
    from solar_platform.db.engine import DuckDBEngine

    assert isinstance(engine, DuckDBEngine)
    with engine.connection(read_only=True) as conn:
        desc = conn.execute(f"SELECT * FROM {table} LIMIT 0").description  # noqa: S608
        return [d[0] for d in desc]


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)  # type: ignore[arg-type]
        return f
    except (TypeError, ValueError):
        return None


def _parse_date(val: str | None) -> "date | None":
    if not val:
        return None
    from datetime import date

    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(val: str | None) -> "datetime | None":
    if not val:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _pick_col(df: "object", candidates: tuple[str, ...]) -> str | None:
    """Return the first matching column name from *candidates*."""
    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    for c in candidates:
        if c in df.columns:
            return c
    return None
