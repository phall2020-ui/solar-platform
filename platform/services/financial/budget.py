"""Budget tracking and comparison service.

Compares actual generation against budgeted values and provides year-to-date
summary reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from services.database.engine import DuckDBEngine, get_engine

logger = structlog.get_logger("services.financial.budget")

_CREATE_BUDGETS_TABLE = """
CREATE TABLE IF NOT EXISTS plant_budgets (
    plant_uid       VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    budget_kwh      DOUBLE  NOT NULL,
    scenario        VARCHAR DEFAULT 'base',
    source          VARCHAR DEFAULT 'manual',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plant_uid, year, month, scenario)
)
"""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
@dataclass
class BudgetComparison:
    """Single month budget vs actual comparison."""

    plant_uid: str
    year: int
    month: int
    budget_kwh: float = 0.0
    actual_kwh: float = 0.0
    variance_kwh: float = 0.0
    variance_pct: float = 0.0
    scenario: str = "base"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def on_track(self) -> bool:
        """Within ±5 % of budget."""
        return abs(self.variance_pct) <= 5.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class BudgetService:
    """Compare actual generation against budget targets."""

    def __init__(self, engine: DuckDBEngine | None = None):
        self.engine = engine or get_engine()
        self._ensure_table()

    def compare(
        self,
        plant_uid: str,
        year: int,
        month: int,
        scenario: str = "base",
    ) -> BudgetComparison:
        """Compare actual vs budget for a single month."""
        budget_kwh = self._get_budget(plant_uid, year, month, scenario)
        actual_kwh = self._get_actual(plant_uid, year, month)

        variance_kwh = actual_kwh - budget_kwh
        variance_pct = (variance_kwh / budget_kwh * 100.0) if budget_kwh else 0.0

        result = BudgetComparison(
            plant_uid=plant_uid,
            year=year,
            month=month,
            budget_kwh=budget_kwh,
            actual_kwh=actual_kwh,
            variance_kwh=variance_kwh,
            variance_pct=variance_pct,
            scenario=scenario,
        )
        logger.info(
            "budget_compared",
            plant_uid=plant_uid,
            year=year,
            month=month,
            on_track=result.on_track,
            variance_pct=round(variance_pct, 2),
        )
        return result

    def ytd_summary(
        self,
        plant_uid: str,
        year: int,
        scenario: str = "base",
    ) -> list[BudgetComparison]:
        """Return month-by-month comparison for the year to date."""
        from datetime import UTC, datetime

        current_month = datetime.now(UTC).month
        if datetime.now(UTC).year > year:
            current_month = 12

        results: list[BudgetComparison] = []
        for month in range(1, current_month + 1):
            results.append(self.compare(plant_uid, year, month, scenario))
        return results

    def set_budget(
        self,
        plant_uid: str,
        year: int,
        month: int,
        budget_kwh: float,
        scenario: str = "base",
        source: str = "manual",
    ) -> None:
        """Insert or update a budget value for a specific month."""
        data = {
            "plant_uid": plant_uid,
            "year": year,
            "month": month,
            "budget_kwh": budget_kwh,
            "scenario": scenario,
            "source": source,
        }
        self.engine.execute_upsert(
            "plant_budgets", data, ["plant_uid", "year", "month", "scenario"]
        )
        logger.info(
            "budget_set",
            plant_uid=plant_uid,
            year=year,
            month=month,
            budget_kwh=budget_kwh,
        )

    # ---- internal --------------------------------------------------------

    def _get_budget(
        self, plant_uid: str, year: int, month: int, scenario: str
    ) -> float:
        query = """
            SELECT budget_kwh FROM plant_budgets
            WHERE plant_uid = ? AND year = ? AND month = ? AND scenario = ?
        """
        rows = self.engine.execute(query, (plant_uid, year, month, scenario))
        if rows and rows[0][0] is not None:
            return float(rows[0][0])
        return 0.0

    def _get_actual(self, plant_uid: str, year: int, month: int) -> float:
        """Sum actual generation_kwh for the month from readings."""
        if not self.engine.table_exists("readings"):
            return 0.0

        ts_col = self._resolve_ts_column()
        query = f"""
            SELECT COALESCE(SUM(generation_kwh), 0)
            FROM readings
            WHERE plant_uid = ?
              AND EXTRACT(YEAR FROM {ts_col}::TIMESTAMP) = ?
              AND EXTRACT(MONTH FROM {ts_col}::TIMESTAMP) = ?
        """
        rows = self.engine.execute(query, (plant_uid, year, month))
        if rows and rows[0][0] is not None:
            return float(rows[0][0])
        return 0.0

    def _resolve_ts_column(self) -> str:
        with self.engine.connection(read_only=True) as conn:
            cols = [
                r[0]
                for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='main' AND table_name='readings'"
                ).fetchall()
            ]
        for candidate in ("timestamp", "ts"):
            if candidate in cols:
                return candidate
        return "timestamp"

    def _ensure_table(self) -> None:
        if not self.engine.table_exists("plant_budgets"):
            self.engine.execute(_CREATE_BUDGETS_TABLE)
            logger.info("table_created", table="plant_budgets")
