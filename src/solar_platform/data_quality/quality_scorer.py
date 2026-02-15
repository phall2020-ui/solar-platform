"""Quality scoring for solar readings.

Assigns a 0-100 quality score to individual readings based on completeness,
plausibility, and source reliability, using the validation framework from
:mod:`services.data_quality.validators`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from solar_platform.data_quality.source_priority import SOURCE_PRIORITY
from solar_platform.data_quality.validators import (
    DEFAULT_VALIDATORS,
    ReadingValidator,
    ValidationReport,
    run_validation,
)

logger = structlog.get_logger("data_quality.quality_scorer")


# Key fields whose presence contributes to the completeness sub-score.
_KEY_FIELDS: list[str] = [
    "power_kw",
    "energy_kwh",
    "poa_wm2",
    "ambient_temp_c",
]


class QualityScorer:
    """Score individual readings or batches on a 0-100 scale.

    The final score blends three components:

    * **Validation score** (50 %): derived from :func:`run_validation`.
    * **Completeness score** (25 %): fraction of key fields that are filled.
    * **Source reliability** (25 %): from :data:`SOURCE_PRIORITY`.
    """

    WEIGHT_VALIDATION: float = 0.50
    WEIGHT_COMPLETENESS: float = 0.25
    WEIGHT_SOURCE: float = 0.25

    def __init__(
        self,
        validators: list[ReadingValidator] | None = None,
        key_fields: list[str] | None = None,
    ) -> None:
        self.validators = validators or DEFAULT_VALIDATORS
        self.key_fields = key_fields or _KEY_FIELDS

    # ── public API ────────────────────────────────────────────────────

    def score_reading(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> float:
        """Return a quality score in [0, 100] for one reading row."""
        vr = run_validation(reading, plant_config, self.validators)
        s_val = vr.quality_score  # already 0-100
        s_comp = self._completeness_score(reading) * 100.0
        s_source = self._source_score(reading) * 100.0

        composite = (
            self.WEIGHT_VALIDATION * s_val
            + self.WEIGHT_COMPLETENESS * s_comp
            + self.WEIGHT_SOURCE * s_source
        )
        return round(max(0.0, min(100.0, composite)), 2)

    def score_batch(
        self,
        readings_df: pd.DataFrame,
        plant_config: dict[str, Any],
    ) -> pd.DataFrame:
        """Score every row and return *readings_df* with a ``quality_score`` column.

        The returned DataFrame is a copy so the caller's original is untouched.
        """
        df = readings_df.copy()
        scores: list[float] = []
        for _, row in df.iterrows():
            scores.append(self.score_reading(row.to_dict(), plant_config))
        df["quality_score"] = scores
        logger.info(
            "batch_scored",
            rows=len(df),
            mean_score=round(pd.Series(scores).mean(), 2) if scores else 0.0,
        )
        return df

    def backfill_quality_scores(
        self,
        plant_uid: str,
        plant_config: dict[str, Any],
        batch_size: int = 5_000,
    ) -> int:
        """Re-score existing readings in the database and persist ``quality_score``.

        Returns the number of rows updated.
        """
        from solar_platform.db.engine import get_engine

        engine = get_engine()

        if not engine.table_exists("readings"):
            logger.warning("backfill_skip", reason="readings table missing")
            return 0

        # Read readings for this plant in batches
        offset = 0
        total_updated = 0
        while True:
            df = engine.execute_df(
                "SELECT * FROM readings WHERE plant_uid = ? ORDER BY timestamp LIMIT ? OFFSET ?",
                (plant_uid, batch_size, offset),
            )
            if df.empty:
                break

            scored = self.score_batch(df, plant_config)

            # Build update statements
            with engine.transaction() as conn:
                for _, row in scored.iterrows():
                    conn.execute(
                        "UPDATE readings SET quality_score = ? "
                        "WHERE plant_uid = ? AND timestamp = ? AND device_id = ?",
                        (
                            row["quality_score"],
                            plant_uid,
                            row.get("timestamp"),
                            row.get("device_id", ""),
                        ),
                    )
            total_updated += len(scored)
            offset += batch_size

        logger.info("backfill_complete", plant_uid=plant_uid, rows_updated=total_updated)
        return total_updated

    # ── sub-scores ────────────────────────────────────────────────────

    def _completeness_score(self, reading: dict[str, Any]) -> float:
        """Fraction of key fields that are non-null, in [0, 1]."""
        if not self.key_fields:
            return 1.0
        present = sum(1 for f in self.key_fields if reading.get(f) is not None)
        return present / len(self.key_fields)

    @staticmethod
    def _source_score(reading: dict[str, Any]) -> float:
        """Map source name to a reliability fraction in [0, 1]."""
        source = reading.get("source", "")
        if not source:
            return 0.5
        # Higher priority number → higher reliability
        max_priority = max(SOURCE_PRIORITY.values()) if SOURCE_PRIORITY else 1
        prio = SOURCE_PRIORITY.get(str(source).lower(), 1)
        return prio / max_priority if max_priority else 0.5
