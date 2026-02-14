"""Data quality package (Phase 6 — Data Resilience & Quality).

Exports the main classes and helpers for validation, scoring, gap analysis,
harmonization, and sensor health monitoring.
"""

from __future__ import annotations

# ── Validators ────────────────────────────────────────────────────────────
from services.data_quality.validators import (
    CapacityExceedanceValidator,
    DEFAULT_VALIDATORS,
    FlatLineValidator,
    NegativeValueValidator,
    NighttimeGenerationValidator,
    RangeValidator,
    ReadingValidator,
    StalenessValidator,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    run_validation,
)

# ── Quality scoring ──────────────────────────────────────────────────────
from services.data_quality.quality_scorer import QualityScorer

# ── Source priority ──────────────────────────────────────────────────────
from services.data_quality.source_priority import (
    SOURCE_PRIORITY,
    SourcePriorityManager,
    pick_best_source,
)

# ── Gap detection & filling ──────────────────────────────────────────────
from services.data_quality.gap_detection import DataGap, GapDetector, GapSeverity
from services.data_quality.gap_filling import (
    FilledReading,
    GapFillingStrategy,
    LinearInterpolation,
    TypicalDayProfile,
    auto_fill_gap,
)

# ── Harmonization ────────────────────────────────────────────────────────
from services.data_quality.harmonization import MultiSourceHarmonizer

# ── Sensor health ────────────────────────────────────────────────────────
from services.data_quality.sensor_health import SensorHealthMonitor

# ── Backward compatibility with legacy single-file module ────────────────
try:
    from services.data_quality_legacy import (
        DataValidator as LegacyDataValidator,
        GapDetector as LegacyGapDetector,
        GapFiller as LegacyGapFiller,
        QualityScorer as LegacyQualityScorer,
    )
except ImportError:
    LegacyDataValidator = None  # type: ignore[assignment,misc]
    LegacyGapDetector = None  # type: ignore[assignment,misc]
    LegacyGapFiller = None  # type: ignore[assignment,misc]
    LegacyQualityScorer = None  # type: ignore[assignment,misc]

__all__ = [
    # Validators
    "ValidationSeverity",
    "ValidationResult",
    "ValidationReport",
    "ReadingValidator",
    "RangeValidator",
    "CapacityExceedanceValidator",
    "NegativeValueValidator",
    "NighttimeGenerationValidator",
    "StalenessValidator",
    "FlatLineValidator",
    "DEFAULT_VALIDATORS",
    "run_validation",
    # Scorer
    "QualityScorer",
    # Source priority
    "SOURCE_PRIORITY",
    "pick_best_source",
    "SourcePriorityManager",
    # Gaps
    "DataGap",
    "GapSeverity",
    "GapDetector",
    "GapFillingStrategy",
    "LinearInterpolation",
    "TypicalDayProfile",
    "FilledReading",
    "auto_fill_gap",
    # Harmonization
    "MultiSourceHarmonizer",
    # Sensor health
    "SensorHealthMonitor",
    # Legacy compat
    "LegacyDataValidator",
    "LegacyGapDetector",
    "LegacyGapFiller",
    "LegacyQualityScorer",
]
