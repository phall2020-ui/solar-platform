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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Solar Portfolio API",
    version="1.0.0",
    description="Read-only API for solar portfolio data.",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="healthy")


@app.get("/api/v1/plants", response_model=list[PlantOut], tags=["plants"])
def list_plants() -> list[PlantOut]:
    """Return all plants in the portfolio."""
    from services.database.engine import get_engine

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

    from services.database.repository import ReadingsRepository

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


@app.get("/api/v1/portfolio/summary", response_model=PortfolioSummary, tags=["portfolio"])
def portfolio_summary() -> PortfolioSummary:
    """Return high-level KPIs for the whole portfolio."""
    from services.database.engine import get_engine

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
    from services.database.engine import DuckDBEngine

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
