"""Tariff management service.

Stores per-plant tariff schedules in a ``plant_tariffs`` DuckDB table and
provides helpers for querying, setting, and importing tariffs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from services.database.engine import DuckDBEngine, get_engine

logger = structlog.get_logger("services.financial.tariff")

_CREATE_TARIFFS_TABLE = """
CREATE TABLE IF NOT EXISTS plant_tariffs (
    plant_uid       VARCHAR NOT NULL,
    tariff_type     VARCHAR NOT NULL DEFAULT 'fixed',
    rate            DOUBLE  NOT NULL,
    start_date      DATE    NOT NULL,
    end_date        DATE,
    escalation_pct  DOUBLE  DEFAULT 0,
    currency        VARCHAR DEFAULT 'EUR',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plant_uid, start_date)
)
"""


class TariffManager:
    """CRUD + import operations for plant tariff schedules."""

    def __init__(self, engine: DuckDBEngine | None = None):
        self.engine = engine or get_engine()
        self._ensure_table()

    # ---- public API ------------------------------------------------------

    def get_tariff(self, plant_uid: str, target_date: date | None = None) -> dict[str, Any] | None:
        """Return the applicable tariff record for *plant_uid* at *target_date*.

        Returns ``None`` when no matching record exists.
        """
        if target_date is None:
            from datetime import UTC, datetime

            target_date = datetime.now(UTC).date()

        query = """
            SELECT plant_uid, tariff_type, rate, start_date, end_date,
                   escalation_pct, currency
            FROM plant_tariffs
            WHERE plant_uid = ?
              AND start_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY start_date DESC
            LIMIT 1
        """
        rows = self.engine.execute(query, (plant_uid, target_date, target_date))
        if not rows:
            return None

        row = rows[0]
        return {
            "plant_uid": row[0],
            "tariff_type": row[1],
            "rate": float(row[2]),
            "start_date": row[3],
            "end_date": row[4],
            "escalation_pct": float(row[5]) if row[5] is not None else 0.0,
            "currency": row[6],
        }

    def set_tariff(
        self,
        plant_uid: str,
        tariff_type: str,
        rate: float,
        start_date: date,
        end_date: date | None = None,
        escalation_pct: float = 0.0,
        currency: str = "EUR",
    ) -> None:
        """Insert or update a tariff record for *plant_uid*."""
        data = {
            "plant_uid": plant_uid,
            "tariff_type": tariff_type,
            "rate": rate,
            "start_date": start_date,
            "end_date": end_date,
            "escalation_pct": escalation_pct,
            "currency": currency,
        }
        self.engine.execute_upsert("plant_tariffs", data, ["plant_uid", "start_date"])
        logger.info("tariff_set", plant_uid=plant_uid, rate=rate, start_date=str(start_date))

    def import_from_csv(self, filepath: str | Path) -> int:
        """Import tariff records from a CSV file.

        Expected columns: plant_uid, tariff_type, rate, start_date
        Optional columns: end_date, escalation_pct, currency

        Returns the number of rows imported.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Tariff CSV not found: {filepath}")

        # Try comma then semicolon
        try:
            df = pd.read_csv(filepath, sep=",")
            if len(df.columns) < 3:
                df = pd.read_csv(filepath, sep=";")
        except Exception:
            df = pd.read_csv(filepath, sep=";")

        required = {"plant_uid", "tariff_type", "rate", "start_date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date
        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce").dt.date
        if "escalation_pct" not in df.columns:
            df["escalation_pct"] = 0.0
        if "currency" not in df.columns:
            df["currency"] = "EUR"

        df = df.dropna(subset=["plant_uid", "rate", "start_date"])

        count = 0
        for _, row in df.iterrows():
            self.set_tariff(
                plant_uid=str(row["plant_uid"]),
                tariff_type=str(row["tariff_type"]),
                rate=float(row["rate"]),
                start_date=row["start_date"],
                end_date=row.get("end_date") if pd.notna(row.get("end_date")) else None,
                escalation_pct=float(row.get("escalation_pct", 0.0)),
                currency=str(row.get("currency", "EUR")),
            )
            count += 1

        logger.info("tariffs_imported", filepath=str(filepath), count=count)
        return count

    # ---- internal --------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create plant_tariffs table if it does not exist."""
        if not self.engine.table_exists("plant_tariffs"):
            self.engine.execute(_CREATE_TARIFFS_TABLE)
            logger.info("table_created", table="plant_tariffs")
