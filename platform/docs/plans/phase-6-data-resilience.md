# Phase 6: Data Resilience & Quality — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 2 weeks  
**Goal:** Build a data quality framework with per-reading validation, quality scoring, source-priority hierarchy, gap detection and filling, and a quality dashboard. Ensure every reading has a confidence score and no silent data gaps exist in the portfolio.

**Key Principle:** Data quality is not optional — it's infrastructure. Every metric displayed to users should carry a quality indicator. Poor quality data must be flagged, not silently admitted.

**Prerequisite:** Phase 0 (database), Phase 1 (data adapters), Phase 3 (analysis engines).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 6.1: Quality Validation Framework](#task-61-quality-validation-framework)
4. [Task 6.2: Per-Reading Quality Score](#task-62-per-reading-quality-score)
5. [Task 6.3: Source Priority & Hierarchy](#task-63-source-priority--hierarchy)
6. [Task 6.4: Gap Detection Service](#task-64-gap-detection-service)
7. [Task 6.5: Gap Filling Strategies](#task-65-gap-filling-strategies)
8. [Task 6.6: Multi-Source Harmonization](#task-66-multi-source-harmonization)
9. [Task 6.7: Data Quality Dashboard UI](#task-67-data-quality-dashboard-ui)
10. [Task 6.8: Sensor Health Monitoring](#task-68-sensor-health-monitoring)
11. [Task 6.9: Quality Metrics in Analysis](#task-69-quality-metrics-in-analysis)
12. [Risks](#risks)
13. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 6.1 Quality Validation Framework | ✅ Done | 6 | P0 | Phase 0 |
| 6.2 Per-Reading Quality Score | ✅ Done | 4 | P0 | 6.1 |
| 6.3 Source Priority & Hierarchy | ✅ Done | 4 | P0 | Phase 1 |
| 6.4 Gap Detection Service | ✅ Done | 6 | P0 | 6.2, 6.3 |
| 6.5 Gap Filling Strategies | ✅ Done | 6 | P1 | 6.4 |
| 6.6 Multi-Source Harmonization | ✅ Done | 4 | P1 | 6.3 |
| 6.7 Data Quality Dashboard UI | ✅ Done | 6 | P1 | 6.4, 6.5 |
| 6.8 Sensor Health Monitoring | ✅ Done | 4 | P2 | 6.1 |
| 6.9 Quality Metrics in Analysis | ✅ Done | 4 | P1 | 6.2, Phase 3 |
| **TOTAL** | | **44** | | |

---

## 2. Dependency Graph

```
┌──────────────────────┐
│ 6.1 Validation       │
│ Framework            │
└──────┬───────────────┘
       │
  ┌────┼────────────┐
  │    │            │
  ▼    ▼            ▼
┌────┐ ┌──────┐  ┌──────┐
│6.2 │ │ 6.3  │  │ 6.8  │
│Score│ │Source│  │Sensor│
│    │ │Prior.│  │Health│
└──┬─┘ └──┬───┘  └──────┘
   │      │
   ├──────┘
   │
   ▼
┌────────┐
│ 6.4    │
│ Gap    │
│ Detect │
└──┬─────┘
   │
   ├──────────┐
   ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐
│ 6.5  │  │ 6.6  │  │ 6.9  │
│ Gap  │  │Harmon│  │Quality│
│ Fill │  │ize   │  │in     │
└──┬───┘  └──────┘  │Analy.│
   │                └──────┘
   ▼
┌──────────┐
│ 6.7 UI   │
│Dashboard │
└──────────┘
```

---

## Task 6.1: Quality Validation Framework

**Goal:** A rule-based validation pipeline that runs 15+ checks on every reading before it's accepted into the database.

**Estimated Hours:** 6

### `services/data_quality/__init__.py`
```python
"""Data quality package."""
```

### `services/data_quality/validators.py`
```python
"""
Data quality validation rules.

Each validator implements a simple interface:
    validate(reading: dict, plant_config: dict) -> ValidationResult

Validators are composable and run in sequence.
New validators can be added without changing existing code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ValidationSeverity(str, Enum):
    ERROR = "error"       # Data rejected
    WARNING = "warning"   # Data accepted with flag
    INFO = "info"         # Informational only


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    rule_name: str
    passed: bool
    severity: ValidationSeverity = ValidationSeverity.WARNING
    message: str = ""
    value: Any = None
    threshold: Any = None


@dataclass
class ValidationReport:
    """Aggregate of all validation results for a reading."""
    results: list[ValidationResult] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        """Did all ERROR-level checks pass?"""
        return all(r.passed for r in self.results if r.severity == ValidationSeverity.ERROR)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == ValidationSeverity.WARNING)
    
    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == ValidationSeverity.ERROR)
    
    @property
    def quality_score(self) -> float:
        """0-100 quality score. 100 = all checks passed."""
        if not self.results:
            return 100.0
        passed = sum(1 for r in self.results if r.passed)
        return round(100.0 * passed / len(self.results), 1)


class Validator(Protocol):
    """Protocol for validation rules."""
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult: ...


class RangeValidator:
    """Validates that a field value is within a physical range."""
    
    def __init__(self, field: str, min_val: float, max_val: float, severity: ValidationSeverity = ValidationSeverity.WARNING):
        self.field = field
        self.min_val = min_val
        self.max_val = max_val
        self.severity = severity
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        value = reading.get(self.field)
        if value is None:
            return ValidationResult(
                rule_name=f"range_{self.field}",
                passed=True, severity=ValidationSeverity.INFO,
                message=f"Field {self.field} is null (skipped range check)",
            )
        passed = self.min_val <= value <= self.max_val
        return ValidationResult(
            rule_name=f"range_{self.field}",
            passed=passed,
            severity=self.severity,
            message=f"{self.field}={value} outside [{self.min_val}, {self.max_val}]" if not passed else "",
            value=value,
            threshold=(self.min_val, self.max_val),
        )


class CapacityExceedanceValidator:
    """Generation should not exceed AC capacity × hours."""
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        generation_kwh = reading.get("generation_kwh", 0)
        ac_capacity_kw = plant_config.get("ac_capacity_kw", float("inf"))
        hours = reading.get("interval_hours", 1)
        max_possible = ac_capacity_kw * hours * 1.1  # 10% tolerance for clipping
        
        passed = generation_kwh <= max_possible
        return ValidationResult(
            rule_name="capacity_exceedance",
            passed=passed,
            severity=ValidationSeverity.ERROR,
            message=f"Gen {generation_kwh} kWh exceeds AC capacity {max_possible:.0f} kWh" if not passed else "",
            value=generation_kwh,
            threshold=max_possible,
        )


class NegativeValueValidator:
    """Key metrics should never be negative."""
    
    FIELDS = ["generation_kwh", "irradiance_kwh_m2", "pr"]
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        for f in self.FIELDS:
            val = reading.get(f)
            if val is not None and val < 0:
                return ValidationResult(
                    rule_name="negative_value",
                    passed=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"{f} is negative: {val}",
                    value=val,
                )
        return ValidationResult(rule_name="negative_value", passed=True, severity=ValidationSeverity.ERROR)


class NighttimeGenerationValidator:
    """Flags generation reported during nighttime hours."""
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        hour = reading.get("hour")
        generation = reading.get("generation_kwh", 0)
        
        if hour is None:
            return ValidationResult(rule_name="nighttime_gen", passed=True, severity=ValidationSeverity.INFO)
        
        is_night = hour < 5 or hour > 21  # Simple check; pvlib-based is more accurate
        passed = not (is_night and generation > 0.5)  # Small tolerance for meter rounding
        
        return ValidationResult(
            rule_name="nighttime_gen", passed=passed,
            severity=ValidationSeverity.WARNING,
            message=f"Generation {generation} kWh at hour {hour}" if not passed else "",
        )


class StalenessValidator:
    """Flags data that is older than expected."""
    
    def __init__(self, max_age_hours: int = 24):
        self.max_age_hours = max_age_hours
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        from datetime import datetime, timedelta, timezone
        ts = reading.get("timestamp")
        if ts is None:
            return ValidationResult(rule_name="staleness", passed=False, severity=ValidationSeverity.WARNING, message="No timestamp")
        
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        
        age = datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)
        passed = age < timedelta(hours=self.max_age_hours)
        
        return ValidationResult(
            rule_name="staleness", passed=passed,
            severity=ValidationSeverity.WARNING,
            message=f"Data is {age.total_seconds() / 3600:.1f}h old" if not passed else "",
        )


class FlatLineValidator:
    """Detects identical repeated values suggesting a stuck sensor."""
    
    def __init__(self, field: str = "generation_kwh", window: int = 6):
        self.field = field
        self.window = window
    
    def validate(self, reading: dict, plant_config: dict) -> ValidationResult:
        # This validator works on a batch — previous N readings needed
        recent = reading.get("_recent_values", [])
        if len(recent) < self.window:
            return ValidationResult(rule_name="flat_line", passed=True, severity=ValidationSeverity.INFO)
        
        unique = len(set(recent[-self.window:]))
        passed = unique > 1
        
        return ValidationResult(
            rule_name="flat_line", passed=passed,
            severity=ValidationSeverity.WARNING,
            message=f"Flat line detected: {self.window} identical values" if not passed else "",
        )


# Default validator pipeline
DEFAULT_VALIDATORS: list[Validator] = [
    RangeValidator("irradiance_kwh_m2", 0, 1.5),
    RangeValidator("pr", 0, 1.1),
    RangeValidator("temperature_c", -40, 80),
    CapacityExceedanceValidator(),
    NegativeValueValidator(),
    NighttimeGenerationValidator(),
    StalenessValidator(max_age_hours=48),
    FlatLineValidator("generation_kwh", window=6),
]


def run_validation(reading: dict, plant_config: dict, validators: list[Validator] | None = None) -> ValidationReport:
    """Run all validators on a single reading."""
    vs = validators or DEFAULT_VALIDATORS
    report = ValidationReport()
    for v in vs:
        result = v.validate(reading, plant_config)
        report.results.append(result)
    return report
```

### Testing

```bash
# Test validation framework
python -c "
from services.data_quality.validators import run_validation

# Normal reading
reading = {'generation_kwh': 100, 'irradiance_kwh_m2': 0.8, 'pr': 0.82, 'hour': 12}
plant = {'ac_capacity_kw': 500}
report = run_validation(reading, plant)
print(f'Normal: score={report.quality_score}, errors={report.error_count}, warnings={report.warning_count}')

# Bad reading — negative generation
bad = {'generation_kwh': -50, 'irradiance_kwh_m2': 0.8, 'pr': 0.82, 'hour': 12}
report2 = run_validation(bad, plant)
print(f'Bad: score={report2.quality_score}, errors={report2.error_count}')
assert not report2.passed, 'Should fail with negative generation'
print('All checks passed.')
"
```

### Acceptance Criteria

- [ ] 8+ validation rules implemented and tested
- [ ] Quality score computed per reading (0-100)
- [ ] ERROR severity blocks data acceptance; WARNING flags only
- [ ] Validators follow Protocol pattern — pluggable

---

## Task 6.2: Per-Reading Quality Score

**Goal:** Compute and store a quality score for every reading in the database.

**Estimated Hours:** 4

### Database Schema Update

```sql
-- Add quality columns to readings table
ALTER TABLE readings ADD COLUMN IF NOT EXISTS quality_score DOUBLE DEFAULT NULL;
ALTER TABLE readings ADD COLUMN IF NOT EXISTS quality_flags VARCHAR DEFAULT NULL;
-- quality_flags is a comma-separated list of failed rule names
-- e.g., "nighttime_gen,flat_line"
```

### Acceptance Criteria

- [ ] Quality score stored per reading
- [ ] Failed rule names stored as flags
- [ ] Backfill script for existing readings
- [ ] Quality score queryable in DuckDB

---

## Task 6.3: Source Priority & Hierarchy

**Goal:** Define which data source is authoritative when multiple sources have data for the same plant/timestamp.

**Estimated Hours:** 4

### Priority Configuration

```python
# services/data_quality/source_priority.py
"""
Source priority hierarchy for multi-source data.

When multiple sources have data for the same plant + timestamp,
the highest-priority source wins.

Priority order (highest first):
1. Physical meter (revenue-grade)  → source: "meter"
2. SCADA / monitoring portal       → source: "emig", "sma", "huawei", etc.
3. Satellite-based estimates       → source: "solargis"
4. Manual entry / CSV upload       → source: "csv"
"""

SOURCE_PRIORITY: dict[str, int] = {
    "meter": 100,
    "emig": 80,
    "juggle": 80,
    "sma": 70,
    "enphase": 70,
    "solaredge": 70,
    "huawei": 70,
    "fronius": 70,
    "solargis": 50,
    "csv": 30,
    "manual": 10,
}


def pick_best_source(candidates: list[dict]) -> dict:
    """Given multiple readings for the same plant+timestamp,
    return the one from the highest-priority source."""
    if not candidates:
        raise ValueError("No candidates")
    return max(candidates, key=lambda c: SOURCE_PRIORITY.get(c.get("source", ""), 0))
```

### Acceptance Criteria

- [ ] Every source adapter has a source tag
- [ ] When dedup finds conflict, highest-priority source wins
- [ ] Source priority configurable per plant (override defaults)

---

## Task 6.4: Gap Detection Service

**Goal:** Detect missing data periods for any plant at any granularity.

**Estimated Hours:** 6

### `services/data_quality/gap_detection.py`
```python
"""
Gap detection service.

A "gap" is a period where expected readings are missing.
Expected frequency is determined by plant configuration:
- 15-min resolution: expect 96 readings per day
- Hourly: expect 24 per day
- Daily: expect 1 per day

The service scans the readings table and produces a list of Gap objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd
import structlog

logger = structlog.get_logger("data_quality.gaps")


@dataclass
class DataGap:
    """A detected gap in the data."""
    plant_uid: str
    start: datetime
    end: datetime
    expected_readings: int
    actual_readings: int
    gap_type: Literal["missing", "partial", "stale"]
    
    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600
    
    @property
    def completeness_pct(self) -> float:
        if self.expected_readings == 0:
            return 100.0
        return round(100.0 * self.actual_readings / self.expected_readings, 1)


class GapDetector:
    """Detect data gaps for a plant."""
    
    def __init__(self, db_engine):
        self.db = db_engine
    
    def detect_gaps(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        expected_freq_minutes: int = 60,
    ) -> list[DataGap]:
        """Detect gaps in readings for a plant within a time range.
        
        Returns a list of DataGap objects representing periods
        where readings are missing or incomplete.
        """
        # Generate expected timestamps
        expected = pd.date_range(start, end, freq=f"{expected_freq_minutes}min")
        
        # Query actual timestamps
        query = """
            SELECT DISTINCT timestamp 
            FROM readings 
            WHERE plant_uid = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp
        """
        with self.db.connect() as conn:
            actual_df = pd.read_sql(query, conn, params=[plant_uid, start, end])
        
        if actual_df.empty:
            return [DataGap(
                plant_uid=plant_uid,
                start=start, end=end,
                expected_readings=len(expected),
                actual_readings=0,
                gap_type="missing",
            )]
        
        actual_ts = set(pd.to_datetime(actual_df["timestamp"]))
        
        # Find contiguous missing periods
        gaps = []
        gap_start = None
        gap_expected = 0
        
        for ts in expected:
            if ts not in actual_ts:
                if gap_start is None:
                    gap_start = ts
                    gap_expected = 0
                gap_expected += 1
            else:
                if gap_start is not None:
                    gaps.append(DataGap(
                        plant_uid=plant_uid,
                        start=gap_start.to_pydatetime(),
                        end=ts.to_pydatetime(),
                        expected_readings=gap_expected,
                        actual_readings=0,
                        gap_type="missing",
                    ))
                    gap_start = None
                    gap_expected = 0
        
        # Close trailing gap
        if gap_start is not None:
            gaps.append(DataGap(
                plant_uid=plant_uid,
                start=gap_start.to_pydatetime(),
                end=end,
                expected_readings=gap_expected,
                actual_readings=0,
                gap_type="missing",
            ))
        
        return gaps
    
    def daily_completeness(
        self, plant_uid: str, start: datetime, end: datetime,
        expected_per_day: int = 24,
    ) -> pd.DataFrame:
        """Calculate daily data completeness percentage.
        
        Returns DataFrame with columns: date, expected, actual, completeness_pct
        """
        query = """
            SELECT DATE_TRUNC('day', timestamp) AS date, COUNT(*) AS actual
            FROM readings
            WHERE plant_uid = ? AND timestamp BETWEEN ? AND ?
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date
        """
        with self.db.connect() as conn:
            df = pd.read_sql(query, conn, params=[plant_uid, start, end])
        
        # Create full date range
        all_dates = pd.date_range(start.date(), end.date(), freq="D")
        full = pd.DataFrame({"date": all_dates, "expected": expected_per_day})
        
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            full = full.merge(df, on="date", how="left")
        else:
            full["actual"] = 0
        
        full["actual"] = full["actual"].fillna(0).astype(int)
        full["completeness_pct"] = (100.0 * full["actual"] / full["expected"]).round(1).clip(0, 100)
        
        return full
```

### Acceptance Criteria

- [ ] Detects contiguous missing periods
- [ ] Reports daily completeness percentage
- [ ] Works with 15-min, hourly, daily resolution
- [ ] Handles empty data gracefully

---

## Task 6.5: Gap Filling Strategies

**Goal:** Fill detected gaps using interpolation, satellite backfill, or flagged estimates.

**Estimated Hours:** 6

### Strategy Pattern

```python
# services/data_quality/gap_filling.py
"""
Gap filling strategies.

All filled data is marked with source="estimated" and a quality flag
so it's never confused with measured data.

Strategies:
1. Linear interpolation (for short gaps < 4 hours)
2. Satellite backfill (for gaps > 4 hours — uses SolarGIS)
3. Typical day profile (for gaps > 24 hours — uses historical average)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

import pandas as pd
import structlog

from services.data_quality.gap_detection import DataGap

logger = structlog.get_logger("data_quality.gap_filling")


class GapFillingStrategy(ABC):
    """Abstract gap filling strategy."""
    
    @abstractmethod
    def can_fill(self, gap: DataGap) -> bool:
        """Whether this strategy can fill this gap."""
        ...
    
    @abstractmethod
    def fill(self, gap: DataGap, existing_data: pd.DataFrame) -> pd.DataFrame:
        """Generate estimated readings for the gap.
        
        Returns DataFrame with same columns as readings table,
        plus source='estimated' and quality_flags='gap_filled'.
        """
        ...


class LinearInterpolation(GapFillingStrategy):
    """Fill short gaps via linear interpolation of surrounding data."""
    
    MAX_GAP_HOURS = 4
    
    def can_fill(self, gap: DataGap) -> bool:
        return gap.duration_hours <= self.MAX_GAP_HOURS
    
    def fill(self, gap: DataGap, existing_data: pd.DataFrame) -> pd.DataFrame:
        if existing_data.empty:
            return pd.DataFrame()
        
        # Interpolate between last reading before gap and first after
        full_range = pd.date_range(gap.start, gap.end, freq="h")
        filled = existing_data.reindex(full_range).interpolate(method="time")
        
        # Mark as estimated
        filled["source"] = "estimated"
        filled["quality_flags"] = "gap_filled_interpolation"
        filled["quality_score"] = 60.0  # Lower confidence
        
        return filled


class TypicalDayProfile(GapFillingStrategy):
    """Fill longer gaps using historical average daily profile."""
    
    def can_fill(self, gap: DataGap) -> bool:
        return gap.duration_hours > 4
    
    def fill(self, gap: DataGap, existing_data: pd.DataFrame) -> pd.DataFrame:
        if existing_data.empty:
            return pd.DataFrame()
        
        # Build average daily profile from existing data
        existing_data["hour"] = existing_data.index.hour
        profile = existing_data.groupby("hour").mean(numeric_only=True)
        
        # Apply to gap period
        gap_range = pd.date_range(gap.start, gap.end, freq="h")
        filled = pd.DataFrame(index=gap_range)
        filled["hour"] = filled.index.hour
        filled = filled.merge(profile, left_on="hour", right_index=True, how="left")
        filled.index = gap_range[:len(filled)]
        
        filled["source"] = "estimated"
        filled["quality_flags"] = "gap_filled_typical_day"
        filled["quality_score"] = 40.0  # Lower confidence than interpolation
        
        return filled


def auto_fill_gap(gap: DataGap, existing_data: pd.DataFrame) -> pd.DataFrame:
    """Automatically select and apply the best filling strategy."""
    strategies: list[GapFillingStrategy] = [
        LinearInterpolation(),
        TypicalDayProfile(),
    ]
    for strategy in strategies:
        if strategy.can_fill(gap):
            logger.info("gap_filling", strategy=type(strategy).__name__, gap=gap)
            return strategy.fill(gap, existing_data)
    
    logger.warning("no_filling_strategy", gap=gap)
    return pd.DataFrame()
```

### Acceptance Criteria

- [ ] Interpolation for short gaps (< 4h)
- [ ] Typical day profile for longer gaps
- [ ] All gap-filled data has `source='estimated'`
- [ ] Quality score reduced for estimated data
- [ ] Users can distinguish measured vs. estimated in UI

---

## Task 6.6: Multi-Source Harmonization

**Goal:** When multiple sources provide data for the same plant, harmonize into a single canonical timeseries.

**Estimated Hours:** 4

### Rules

1. **Timestamp alignment:** Round all readings to the nearest interval boundary (e.g., hourly → :00)
2. **Unit normalization:** kWh everywhere (convert W, MW if needed)
3. **Dedup & priority:** If two sources have data for the same timestamp, use source priority (Task 6.3)
4. **Merge:** Combine fields from multiple sources (e.g., generation from EMIG, irradiance from SolarGIS)

### Acceptance Criteria

- [ ] Timestamps aligned to consistent intervals
- [ ] Units normalized to kWh/kWh/m²/°C
- [ ] Source priority applied for conflicts
- [ ] Cross-source field merging supported

---

## Task 6.7: Data Quality Dashboard UI

**Goal:** Streamlit page showing quality overview across the portfolio.

**Estimated Hours:** 6

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ 🏥 Data Quality                                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Portfolio Quality Score: ████████████████████░░ 89%          │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐     │
│ │ Data Completeness Heatmap                           │     │
│ │                                                      │     │
│ │ Plant     │ Dec 1 │ Dec 2 │ Dec 3 │ ... │ Dec 31   │     │
│ │ ──────────┼───────┼───────┼───────┼─────┼──────────│     │
│ │ Oakfield  │ 🟢100 │ 🟢 96 │ 🟡 72 │ ... │ 🟢 100   │     │
│ │ Sunderland│ 🟢100 │ 🟢100 │ 🟢100 │ ... │ 🔴   0   │     │
│ │ ...       │       │       │       │     │          │     │
│ └──────────────────────────────────────────────────────┘     │
│                                                              │
│ ┌─────────────────────────────────┐┌─────────────────────┐  │
│ │ Validation Failures (Last 7d)  ││ Gaps Detected        │  │
│ │                                ││                      │  │
│ │ Nighttime gen:     ████ 12     ││ Total: 4 gaps        │  │
│ │ Capacity exceed:   ██ 3        ││ Duration: 18.5h      │  │
│ │ Flat line:         █ 1         ││ Unfilled: 2          │  │
│ └─────────────────────────────────┘└─────────────────────┘  │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Per-Plant Detail (expandable)                           │ │
│ │ ▶ Oakfield Park — 95% quality, 2 warnings               │ │
│ │ ▶ Sunderland — 87% quality, 1 gap (3h)                   │ │
│ │ ▼ Thorpe Marsh — 61% quality ⚠️                          │ │
│ │   - Missing: 2025-01-15 08:00 to 2025-01-15 14:00       │ │
│ │   - Flat line: generation_kwh stuck at 0 for 8h         │ │
│ │   - [Fill Gap] [Suppress Warning]                        │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Acceptance Criteria

- [ ] Portfolio-level quality score
- [ ] Completeness heatmap (plant × day)
- [ ] Validation failure breakdown
- [ ] Gap listing with fill/suppress controls
- [ ] Drill down to per-plant detail

---

## Task 6.8: Sensor Health Monitoring

**Goal:** Track sensor reliability over time and flag degrading sensors.

**Estimated Hours:** 4

### Metrics per Sensor/Plant

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Uptime % | Percentage of expected readings received | < 90% |
| Flat line % | Percentage of readings flagged as flat | > 5% |
| Missing % | Percentage of readings missing | > 10% |
| Latency (hours) | Time since last reading | > 24h |
| Error rate | % of readings failing ERROR-level validation | > 2% |

### Acceptance Criteria

- [ ] Sensor health history stored (daily rollup)
- [ ] Trend over last 30 days
- [ ] Alert when sensor health degrades below threshold

---

## Task 6.9: Quality Metrics in Analysis

**Goal:** Surface data quality alongside analysis results so users know how trustworthy the numbers are.

**Estimated Hours:** 4

### Integration Points

All analysis engines from Phase 3 should include quality metadata in results:

```python
# In AnalysisResult (from Phase 3 Task 3.1)
@dataclass
class AnalysisResult:
    # ... existing fields ...
    data_quality: DataQualityContext = field(default_factory=DataQualityContext)


@dataclass
class DataQualityContext:
    """Quality context for an analysis result."""
    total_readings: int = 0
    valid_readings: int = 0
    estimated_readings: int = 0  # Gap-filled
    avg_quality_score: float = 100.0
    completeness_pct: float = 100.0
    
    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.completeness_pct >= 95 and self.avg_quality_score >= 90:
            return "high"
        elif self.completeness_pct >= 80 and self.avg_quality_score >= 70:
            return "medium"
        else:
            return "low"
```

### UI Display

Every analysis page should show a quality badge:

```python
def quality_badge(quality: DataQualityContext):
    """Render quality indicator in Streamlit."""
    colors = {"high": "🟢", "medium": "🟡", "low": "🔴"}
    icon = colors.get(quality.confidence_level, "⚪")
    st.caption(
        f"{icon} Data confidence: {quality.confidence_level} "
        f"({quality.completeness_pct:.0f}% complete, "
        f"{quality.estimated_readings} estimated readings)"
    )
```

### Acceptance Criteria

- [ ] Every analysis result includes quality context
- [ ] Confidence badge shown on all analysis pages
- [ ] Users can understand trustworthiness of numbers

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Quality scoring too aggressive (falsely rejects good data) | High | Medium | Start with WARNING severity; tune thresholds over time |
| Gap filling introduces bias in PR calculations | Medium | Medium | Flag all estimated data; exclude from PR if requested |
| Performance impact of running 15+ validators on every reading | Medium | Low | Batch validation; only run on ingest |
| DuckDB ALTER TABLE performance with 1.28M rows | Low | Low | Run ALTER during off-peak; test timing |
| Users ignore quality badges | Medium | Medium | Make quality problems visible at portfolio level first |

---

## Definition of Done

- [ ] 8+ validation rules running on all incoming data
- [ ] Quality score stored per reading in database
- [ ] Source priority hierarchy implemented and configurable
- [ ] Gap detection finds all missing periods
- [ ] Gap filling strategies with clear estimated-data markers
- [ ] Data quality dashboard with completeness heatmap
- [ ] Quality badges on all analysis pages
- [ ] 15+ unit tests for validators and gap detection
- [ ] Backfill script updates quality scores for existing readings
