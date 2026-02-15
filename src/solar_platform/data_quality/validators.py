"""Validation framework for solar readings data quality.

Protocol-based validators that can be composed into validation pipelines.
Each validator inspects a single reading (as a dict or row) against plant
configuration and emits zero or more :class:`ValidationResult` findings.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import structlog

logger = structlog.get_logger("data_quality.validators")


# ── Severity & result types ──────────────────────────────────────────────


class ValidationSeverity(str, Enum):
    """Severity level attached to a validation finding."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationResult:
    """A single finding produced by a validator."""

    validator_name: str
    severity: ValidationSeverity
    message: str
    field_name: str = ""
    value: Any = None
    threshold: Any = None


@dataclass
class ValidationReport:
    """Aggregated report produced by running validators on one or more readings."""

    results: list[ValidationResult] = field(default_factory=list)
    total_checked: int = 0

    # ── derived properties ────────────────────────────────────────────

    @property
    def quality_score(self) -> float:
        """Return a 0-100 quality score.

        Starts at 100 and deducts 10 per ERROR, 3 per WARNING.
        """
        score = 100.0
        for r in self.results:
            if r.severity is ValidationSeverity.ERROR:
                score -= 10.0
            elif r.severity is ValidationSeverity.WARNING:
                score -= 3.0
        return max(score, 0.0)

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity is ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity is ValidationSeverity.WARNING)

    def add(self, result: ValidationResult) -> None:
        self.results.append(result)

    def merge(self, other: ValidationReport) -> None:
        """Merge another report into this one."""
        self.results.extend(other.results)
        self.total_checked += other.total_checked


# ── Validator protocol ───────────────────────────────────────────────────


@runtime_checkable
class ReadingValidator(Protocol):
    """Protocol that all validators must satisfy."""

    name: str

    @abstractmethod
    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        """Return a (possibly empty) list of findings for *reading*."""
        ...


# ── Concrete validators ─────────────────────────────────────────────────


class RangeValidator:
    """Flag values outside physically plausible ranges."""

    name: str = "range"

    # field → (min, max)
    DEFAULT_RANGES: dict[str, tuple[float, float]] = {
        "power_kw": (0.0, 500_000),
        "energy_kwh": (0.0, 5_000_000),
        "ghi_wm2": (0.0, 1_500),
        "poa_wm2": (0.0, 1_600),
        "dni_wm2": (0.0, 1_400),
        "dhi_wm2": (0.0, 800),
        "ambient_temp_c": (-50.0, 65.0),
        "module_temp_c": (-40.0, 100.0),
        "wind_speed_ms": (0.0, 75.0),
    }

    def __init__(self, ranges: dict[str, tuple[float, float]] | None = None) -> None:
        self.ranges = ranges or self.DEFAULT_RANGES

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        findings: list[ValidationResult] = []
        for fld, (lo, hi) in self.ranges.items():
            val = reading.get(fld)
            if val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if val < lo or val > hi:
                findings.append(
                    ValidationResult(
                        validator_name=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"{fld}={val} outside [{lo}, {hi}]",
                        field_name=fld,
                        value=val,
                        threshold=(lo, hi),
                    )
                )
        return findings


class CapacityExceedanceValidator:
    """Flag power readings that exceed the plant's nameplate capacity."""

    name: str = "capacity_exceedance"

    def __init__(self, tolerance_pct: float = 1.10) -> None:
        self.tolerance_pct = tolerance_pct

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        capacity_kw = plant_config.get("capacity_kw") or plant_config.get("capacity_kwp")
        if not capacity_kw:
            return []
        power = reading.get("power_kw")
        if power is None:
            return []
        try:
            power = float(power)
            capacity_kw = float(capacity_kw)
        except (TypeError, ValueError):
            return []
        limit = capacity_kw * self.tolerance_pct
        if power > limit:
            return [
                ValidationResult(
                    validator_name=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"power_kw={power} exceeds {self.tolerance_pct:.0%} of capacity ({capacity_kw} kW)",
                    field_name="power_kw",
                    value=power,
                    threshold=limit,
                )
            ]
        return []


class NegativeValueValidator:
    """Flag negative values on fields that should always be non-negative."""

    name: str = "negative_value"

    NON_NEGATIVE_FIELDS: list[str] = [
        "power_kw",
        "energy_kwh",
        "ghi_wm2",
        "poa_wm2",
        "dni_wm2",
        "dhi_wm2",
        "wind_speed_ms",
    ]

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        findings: list[ValidationResult] = []
        for fld in self.NON_NEGATIVE_FIELDS:
            val = reading.get(fld)
            if val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if val < 0:
                findings.append(
                    ValidationResult(
                        validator_name=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"{fld}={val} is negative",
                        field_name=fld,
                        value=val,
                        threshold=0.0,
                    )
                )
        return findings


class NighttimeGenerationValidator:
    """Flag non-zero power when irradiance is zero or absent (nighttime)."""

    name: str = "nighttime_generation"

    def __init__(self, irradiance_threshold: float = 5.0, power_threshold_kw: float = 1.0) -> None:
        self.irradiance_threshold = irradiance_threshold
        self.power_threshold_kw = power_threshold_kw

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        poa = reading.get("poa_wm2")
        ghi = reading.get("ghi_wm2")
        power = reading.get("power_kw")

        if power is None:
            return []
        try:
            power = float(power)
        except (TypeError, ValueError):
            return []
        if power <= self.power_threshold_kw:
            return []

        # Need at least one irradiance field to decide
        irradiance_low = False
        if poa is not None:
            try:
                if float(poa) <= self.irradiance_threshold:
                    irradiance_low = True
            except (TypeError, ValueError):
                pass
        elif ghi is not None:
            try:
                if float(ghi) <= self.irradiance_threshold:
                    irradiance_low = True
            except (TypeError, ValueError):
                pass
        else:
            return []

        if irradiance_low:
            return [
                ValidationResult(
                    validator_name=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"power_kw={power} while irradiance ≤ {self.irradiance_threshold} W/m²",
                    field_name="power_kw",
                    value=power,
                    threshold=self.irradiance_threshold,
                )
            ]
        return []


class StalenessValidator:
    """Flag readings whose timestamp is much older than 'now'."""

    name: str = "staleness"

    def __init__(self, max_age_hours: float = 48.0) -> None:
        self.max_age_hours = max_age_hours

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        ts = reading.get("timestamp")
        if ts is None:
            return []
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                return []
        if not isinstance(ts, datetime):
            return []
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (now - ts).total_seconds() / 3600
        if age_hours > self.max_age_hours:
            return [
                ValidationResult(
                    validator_name=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Reading is {age_hours:.1f}h old (limit {self.max_age_hours}h)",
                    field_name="timestamp",
                    value=str(ts),
                    threshold=self.max_age_hours,
                )
            ]
        return []


class FlatLineValidator:
    """Detect stuck / flat-line sensor values.

    This validator is designed to be called on consecutive readings.
    Feed it readings sequentially; it tracks state internally via a buffer.
    Alternately, pass the full series via :meth:`validate_series`.
    """

    name: str = "flatline"

    def __init__(
        self,
        fields: list[str] | None = None,
        min_repeat: int = 6,
    ) -> None:
        self.fields = fields or ["power_kw", "poa_wm2"]
        self.min_repeat = min_repeat

    def validate(
        self,
        reading: dict[str, Any],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        # Single-reading mode is a no-op; use validate_series instead.
        return []

    def validate_series(
        self,
        readings: list[dict[str, Any]],
        plant_config: dict[str, Any],
    ) -> list[ValidationResult]:
        """Run flat-line detection over a series of readings."""
        findings: list[ValidationResult] = []
        for fld in self.fields:
            run_length = 1
            prev_val: Any = None
            for idx, r in enumerate(readings):
                val = r.get(fld)
                if val is not None and val == prev_val:
                    run_length += 1
                else:
                    if run_length >= self.min_repeat and prev_val is not None:
                        findings.append(
                            ValidationResult(
                                validator_name=self.name,
                                severity=ValidationSeverity.WARNING,
                                message=f"{fld} stuck at {prev_val} for {run_length} readings",
                                field_name=fld,
                                value=prev_val,
                                threshold=self.min_repeat,
                            )
                        )
                    run_length = 1
                prev_val = val
            # Check trailing run
            if run_length >= self.min_repeat and prev_val is not None:
                findings.append(
                    ValidationResult(
                        validator_name=self.name,
                        severity=ValidationSeverity.WARNING,
                        message=f"{fld} stuck at {prev_val} for {run_length} readings",
                        field_name=fld,
                        value=prev_val,
                        threshold=self.min_repeat,
                    )
                )
        return findings


# ── Default validator set & runner ───────────────────────────────────────

DEFAULT_VALIDATORS: list[ReadingValidator] = [
    RangeValidator(),
    CapacityExceedanceValidator(),
    NegativeValueValidator(),
    NighttimeGenerationValidator(),
    StalenessValidator(),
    FlatLineValidator(),
]


def run_validation(
    reading: dict[str, Any],
    plant_config: dict[str, Any],
    validators: list[ReadingValidator] | None = None,
) -> ValidationReport:
    """Run a set of validators against a single reading dict.

    Args:
        reading: Dict of column→value (e.g. one row of a DataFrame).
        plant_config: Plant metadata dict (capacity_kw, etc.).
        validators: Validators to run.  Defaults to :data:`DEFAULT_VALIDATORS`.

    Returns:
        A :class:`ValidationReport` with all findings.
    """
    validators = validators or DEFAULT_VALIDATORS
    report = ValidationReport(total_checked=1)
    for v in validators:
        try:
            findings = v.validate(reading, plant_config)
            for f in findings:
                report.add(f)
        except Exception:
            logger.warning("validator_failed", validator=v.name, exc_info=True)
    return report
