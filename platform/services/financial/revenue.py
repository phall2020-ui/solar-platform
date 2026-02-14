"""Revenue calculation service for solar plants.

Computes monthly revenue per plant and portfolio-level summaries based on
generation data stored in DuckDB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd
import structlog

from services.database.engine import DuckDBEngine, get_engine

logger = structlog.get_logger("services.financial.revenue")


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
class TariffType(str, Enum):
    """Supported tariff structures."""

    FIXED = "fixed"
    TIME_OF_USE = "time_of_use"
    FIT = "fit"
    PPA = "ppa"


@dataclass
class RevenueResult:
    """Monthly revenue calculation for a single plant."""

    plant_uid: str
    year: int
    month: int
    generation_mwh: float = 0.0
    tariff_per_mwh: float = 0.0
    revenue: float = 0.0
    tariff_type: TariffType = TariffType.FIXED
    currency: str = "EUR"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class RevenueService:
    """Calculate plant and portfolio revenue from generation data."""

    def __init__(self, engine: DuckDBEngine | None = None):
        self.engine = engine or get_engine()

    def calculate_monthly(
        self,
        plant_uid: str,
        year: int,
        month: int,
        tariff_per_mwh: float,
        tariff_type: TariffType = TariffType.FIXED,
        currency: str = "EUR",
    ) -> RevenueResult:
        """Calculate revenue for *plant_uid* in the given month."""
        generation_mwh = self._get_monthly_generation_mwh(plant_uid, year, month)
        revenue = generation_mwh * tariff_per_mwh

        logger.info(
            "revenue_calculated",
            plant_uid=plant_uid,
            year=year,
            month=month,
            generation_mwh=round(generation_mwh, 3),
            revenue=round(revenue, 2),
        )

        return RevenueResult(
            plant_uid=plant_uid,
            year=year,
            month=month,
            generation_mwh=generation_mwh,
            tariff_per_mwh=tariff_per_mwh,
            revenue=revenue,
            tariff_type=tariff_type,
            currency=currency,
        )

    def portfolio_summary(
        self,
        year: int,
        month: int,
        default_tariff_per_mwh: float = 0.0,
    ) -> list[RevenueResult]:
        """Calculate revenue for every plant in a given month.

        If a plant has a tariff record in *plant_tariffs* that is used;
        otherwise *default_tariff_per_mwh* is applied.
        """
        plant_uids = self._list_plant_uids()
        tariffs = self._load_tariffs(year, month)

        results: list[RevenueResult] = []
        for uid in plant_uids:
            tariff_info = tariffs.get(uid, {})
            rate = tariff_info.get("rate", default_tariff_per_mwh)
            tt = TariffType(tariff_info.get("tariff_type", TariffType.FIXED.value))
            results.append(
                self.calculate_monthly(uid, year, month, rate, tariff_type=tt)
            )
        return results

    # ---- internal helpers ------------------------------------------------

    def _get_monthly_generation_mwh(
        self, plant_uid: str, year: int, month: int
    ) -> float:
        """Sum generation_kwh for a plant/month and convert to MWh."""
        ts_col = self._resolve_ts_column()
        query = f"""
            SELECT COALESCE(SUM(generation_kwh), 0) AS total_kwh
            FROM readings
            WHERE plant_uid = ?
              AND EXTRACT(YEAR FROM {ts_col}::TIMESTAMP) = ?
              AND EXTRACT(MONTH FROM {ts_col}::TIMESTAMP) = ?
        """
        rows = self.engine.execute(query, (plant_uid, year, month))
        total_kwh = float(rows[0][0]) if rows and rows[0][0] is not None else 0.0
        return total_kwh / 1000.0

    def _resolve_ts_column(self) -> str:
        """Return the timestamp column name used in the readings table."""
        if not self.engine.table_exists("readings"):
            return "timestamp"
        with self.engine.connection(read_only=True) as conn:
            cols = [
                row[0]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='main' AND table_name='readings'"
                ).fetchall()
            ]
        for candidate in ("timestamp", "ts"):
            if candidate in cols:
                return candidate
        return "timestamp"

    def _list_plant_uids(self) -> list[str]:
        if not self.engine.table_exists("plants"):
            return []
        rows = self.engine.execute("SELECT plant_uid FROM plants ORDER BY plant_uid")
        return [r[0] for r in rows]

    def _load_tariffs(self, year: int, month: int) -> dict[str, dict[str, Any]]:
        """Load tariff records applicable to the given period."""
        if not self.engine.table_exists("plant_tariffs"):
            return {}
        try:
            query = """
                SELECT plant_uid, tariff_type, rate
                FROM plant_tariffs
                WHERE start_date <= MAKE_DATE(?, ?, 1)
                  AND (end_date IS NULL OR end_date >= MAKE_DATE(?, ?, 1))
            """
            rows = self.engine.execute(query, (year, month, year, month))
            return {
                row[0]: {"tariff_type": row[1], "rate": float(row[2])}
                for row in rows
            }
        except Exception:
            logger.warning("tariff_load_failed", year=year, month=month)
            return {}
