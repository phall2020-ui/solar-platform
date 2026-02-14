"""
Data quality scoring, gap detection, gap filling, and validation.

Provides four core components:

    :class:`QualityScorer`
        Assigns 0–1 quality score to each reading based on source,
        completeness, and plausibility.

    :class:`GapDetector`
        Identifies gaps in time-series data and classifies them:
        SHORT (< 1 h), MEDIUM (1–24 h), LONG (> 24 h).

    :class:`GapFiller`
        Fills gaps via interpolation (short), satellite fallback (medium),
        or flags them (long).

    :class:`DataValidator`
        Runs 15 validation checks on a batch of readings — extends the
        existing ``incremental_etl.py`` checks with additional solar-specific
        rules.

All classes operate on lists of :class:`Reading` objects from
:mod:`services.ingestion.base`.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from services.ingestion.base import (
    GapSeverity,
    Reading,
    ReadingQuality,
    SOURCE_RELIABILITY,
)

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Quality Scorer
# ═══════════════════════════════════════════════════════════════════════════

class QualityScorer:
    """
    Assigns a composite quality score (0–1) to individual readings.

    The score is a weighted combination of:
        - **Source reliability** (40%): from ``SOURCE_RELIABILITY`` dict.
        - **Completeness** (30%): fraction of key fields that are non-null.
        - **Plausibility** (30%): whether values fall within physically
          realistic ranges.
    """

    # Fields considered "key" for completeness scoring
    KEY_FIELDS: list[str] = [
        "power_kw", "energy_kwh", "poa_wm2", "ambient_temp_c",
    ]

    # Plausibility ranges: (min, max) inclusive
    PLAUSIBILITY_RANGES: dict[str, tuple[float, float]] = {
        "power_kw": (0.0, 500_000),        # 0 – 500 MW
        "energy_kwh": (0.0, 5_000_000),     # 0 – 5 GWh per interval
        "ghi_wm2": (0.0, 1_500),
        "poa_wm2": (0.0, 1_600),
        "dni_wm2": (0.0, 1_400),
        "dhi_wm2": (0.0, 800),
        "ambient_temp_c": (-50.0, 65.0),
        "module_temp_c": (-40.0, 100.0),
        "wind_speed_ms": (0.0, 75.0),
        "voltage_v": (0.0, 2_000),
        "current_a": (0.0, 5_000),
        "frequency_hz": (45.0, 65.0),
        "power_factor": (-1.0, 1.0),
    }

    WEIGHT_SOURCE = 0.40
    WEIGHT_COMPLETENESS = 0.30
    WEIGHT_PLAUSIBILITY = 0.30

    def score(self, reading: Reading) -> float:
        """
        Compute the quality score for a single reading.

        Returns a float in [0, 1] and also sets ``reading.quality_score``.
        """
        s_source = self._source_score(reading)
        s_complete = self._completeness_score(reading)
        s_plausible = self._plausibility_score(reading)

        composite = (
            self.WEIGHT_SOURCE * s_source
            + self.WEIGHT_COMPLETENESS * s_complete
            + self.WEIGHT_PLAUSIBILITY * s_plausible
        )
        composite = round(min(max(composite, 0.0), 1.0), 4)
        reading.quality_score = composite
        return composite

    def score_batch(self, readings: list[Reading]) -> list[float]:
        """Score every reading in a list; returns the list of scores."""
        return [self.score(r) for r in readings]

    # --- Sub-scores ---

    @staticmethod
    def _source_score(reading: Reading) -> float:
        return SOURCE_RELIABILITY.get(reading.source, 0.3)

    def _completeness_score(self, reading: Reading) -> float:
        present = sum(
            1 for f in self.KEY_FIELDS
            if getattr(reading, f, None) is not None
        )
        return present / max(len(self.KEY_FIELDS), 1)

    def _plausibility_score(self, reading: Reading) -> float:
        checked = 0
        passed = 0
        for field, (lo, hi) in self.PLAUSIBILITY_RANGES.items():
            val = getattr(reading, field, None)
            if val is None:
                continue
            checked += 1
            if lo <= val <= hi:
                passed += 1
        if checked == 0:
            return 1.0  # no data to judge
        return passed / checked


# ═══════════════════════════════════════════════════════════════════════════
# Gap Detector
# ═══════════════════════════════════════════════════════════════════════════

class Gap(BaseModel):
    """Describes a single gap in a time series."""
    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    severity: GapSeverity
    duration_minutes: float
    plant_uid: str
    device_id: str = ""
    expected_readings: int = 0


class GapDetector:
    """
    Identifies gaps in a sorted list of ``Reading`` objects.

    Classification:
        - **SHORT**: < 1 hour
        - **MEDIUM**: 1–24 hours
        - **LONG**: > 24 hours
    """

    def detect(
        self,
        readings: list[Reading],
        expected_interval_s: int | None = None,
    ) -> list[Gap]:
        """
        Detect gaps in a timestamp-sorted reading list.

        Args:
            readings: Must be sorted by ``timestamp``.
            expected_interval_s: Override for expected interval.
                If ``None``, auto-detected from the data.

        Returns:
            List of :class:`Gap` objects.
        """
        if len(readings) < 2:
            return []

        interval_s = expected_interval_s or self._auto_interval(readings)
        if interval_s is None or interval_s <= 0:
            return []

        threshold_s = interval_s * 1.5
        gaps: list[Gap] = []

        for i in range(1, len(readings)):
            delta_s = (readings[i].timestamp - readings[i - 1].timestamp).total_seconds()
            if delta_s > threshold_s:
                gap_start = readings[i - 1].timestamp
                gap_end = readings[i].timestamp
                dur_min = delta_s / 60

                if dur_min < 60:
                    sev = GapSeverity.SHORT
                elif dur_min < 24 * 60:
                    sev = GapSeverity.MEDIUM
                else:
                    sev = GapSeverity.LONG

                gaps.append(Gap(
                    start=gap_start,
                    end=gap_end,
                    severity=sev,
                    duration_minutes=round(dur_min, 1),
                    plant_uid=readings[i].plant_uid,
                    device_id=readings[i].device_id,
                    expected_readings=max(int(delta_s / interval_s) - 1, 0),
                ))

        return gaps

    def summary(self, gaps: list[Gap]) -> dict[str, Any]:
        """Return a summary dict for a list of gaps."""
        by_severity = Counter(g.severity for g in gaps)
        return {
            "total_gaps": len(gaps),
            "short": by_severity.get(GapSeverity.SHORT, 0),
            "medium": by_severity.get(GapSeverity.MEDIUM, 0),
            "long": by_severity.get(GapSeverity.LONG, 0),
            "total_missing_minutes": round(sum(g.duration_minutes for g in gaps), 1),
            "total_expected_readings": sum(g.expected_readings for g in gaps),
        }

    @staticmethod
    def _auto_interval(readings: list[Reading]) -> int | None:
        if len(readings) < 2:
            return None
        deltas: list[int] = []
        for i in range(1, min(len(readings), 200)):
            d = int((readings[i].timestamp - readings[i - 1].timestamp).total_seconds())
            if 0 < d < 86400:
                deltas.append(d)
        if not deltas:
            return None
        return Counter(deltas).most_common(1)[0][0]


# ═══════════════════════════════════════════════════════════════════════════
# Gap Filler
# ═══════════════════════════════════════════════════════════════════════════

class GapFiller:
    """
    Fills gaps using a cascade of strategies:

        1. **Interpolation** — for SHORT gaps (< 1 h): linear interpolation
           between boundary readings.
        2. **Satellite fallback** — for MEDIUM gaps (1–24 h): external
           satellite data (caller must provide).
        3. **Flag** — for LONG gaps (> 24 h): insert placeholder readings
           with ``quality=MISSING``.
    """

    def interpolate(
        self,
        readings: list[Reading],
        gap: Gap,
        interval_s: int,
    ) -> list[Reading]:
        """
        Fill a gap by linear interpolation between the boundary readings.

        Returns new ``Reading`` objects with ``quality=INTERPOLATED``.
        """
        before = next((r for r in reversed(readings) if r.timestamp <= gap.start), None)
        after = next((r for r in readings if r.timestamp >= gap.end), None)
        if not before or not after:
            return []

        total_s = (after.timestamp - before.timestamp).total_seconds()
        if total_s <= 0:
            return []

        fills: list[Reading] = []
        numeric_fields = [
            "power_kw", "energy_kwh", "ghi_wm2", "poa_wm2", "dni_wm2",
            "dhi_wm2", "gti_wm2", "ambient_temp_c", "module_temp_c",
            "wind_speed_ms", "voltage_v", "current_a",
        ]

        ts = gap.start + timedelta(seconds=interval_s)
        while ts < gap.end:
            frac = (ts - before.timestamp).total_seconds() / total_s
            kwargs: dict[str, Any] = {}
            for field in numeric_fields:
                vb = getattr(before, field, None)
                va = getattr(after, field, None)
                if vb is not None and va is not None:
                    kwargs[field] = round(vb + (va - vb) * frac, 4)

            fills.append(Reading(
                timestamp=ts,
                plant_uid=gap.plant_uid,
                device_id=gap.device_id,
                source="interpolated",
                quality=ReadingQuality.INTERPOLATED,
                quality_score=SOURCE_RELIABILITY.get("interpolated", 0.5),
                interval_seconds=interval_s,
                **kwargs,
            ))
            ts += timedelta(seconds=interval_s)

        return fills

    def flag_missing(self, gap: Gap, interval_s: int) -> list[Reading]:
        """
        Create placeholder readings flagged as ``MISSING`` for an unfillable gap.
        """
        fills: list[Reading] = []
        ts = gap.start + timedelta(seconds=interval_s)
        while ts < gap.end:
            fills.append(Reading(
                timestamp=ts,
                plant_uid=gap.plant_uid,
                device_id=gap.device_id,
                source="gap_detector",
                quality=ReadingQuality.MISSING,
                quality_score=0.0,
                interval_seconds=interval_s,
            ))
            ts += timedelta(seconds=interval_s)
        return fills


# ═══════════════════════════════════════════════════════════════════════════
# Data Validator
# ═══════════════════════════════════════════════════════════════════════════

class ValidationSeverity(str, Enum):
    """Severity level for a validation finding."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationFinding(BaseModel):
    """A single validation finding."""
    model_config = ConfigDict(frozen=True)

    check_name: str
    severity: ValidationSeverity
    message: str
    affected_count: int = 0
    affected_pct: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """Aggregated validation report for a batch of readings."""
    model_config = ConfigDict(frozen=False)

    plant_uid: str = ""
    total_readings: int = 0
    findings: list[ValidationFinding] = Field(default_factory=list)
    overall_pass: bool = True

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == ValidationSeverity.WARNING)


class DataValidator:
    """
    Runs 15 validation checks on a list of ``Reading`` objects.

    Checks:
        1. Empty batch
        2. Timestamp ordering
        3. Duplicate timestamps
        4. Null power values
        5. Null irradiance values
        6. Numeric range (plausibility)
        7. Rate-of-change (power ramp)
        8. Night-time power (non-zero power when irradiance = 0)
        9. Irradiance consistency (GHI ≈ DNI·cos(z) + DHI)
        10. Stuck sensor (same value repeated > N times)
        11. Timezone validation (timestamps should be UTC)
        12. Capacity exceedance (power > plant capacity)
        13. Cross-sensor validation (all inverters agree ± tolerance)
        14. Future timestamps
        15. Energy–power consistency
    """

    def __init__(
        self,
        plant_capacity_kw: float | None = None,
        stuck_threshold: int = 10,
        ramp_rate_kw_per_min: float | None = None,
    ) -> None:
        """
        Args:
            plant_capacity_kw: Nominal DC capacity for capacity-exceedance check.
            stuck_threshold: Number of identical consecutive readings to flag.
            ramp_rate_kw_per_min: Max expected power change per minute.
        """
        self.plant_capacity_kw = plant_capacity_kw
        self.stuck_threshold = stuck_threshold
        self.ramp_rate_kw_per_min = ramp_rate_kw_per_min

    def validate(self, readings: list[Reading], plant_uid: str = "") -> ValidationReport:
        """
        Run all 15 checks and return a :class:`ValidationReport`.
        """
        report = ValidationReport(plant_uid=plant_uid, total_readings=len(readings))

        if not readings:
            report.findings.append(ValidationFinding(
                check_name="empty_batch",
                severity=ValidationSeverity.ERROR,
                message="No readings to validate",
            ))
            report.overall_pass = False
            return report

        # Run each check
        checks = [
            self._check_timestamp_order,
            self._check_duplicates,
            self._check_null_power,
            self._check_null_irradiance,
            self._check_numeric_ranges,
            self._check_rate_of_change,
            self._check_night_power,
            self._check_irradiance_consistency,
            self._check_stuck_sensor,
            self._check_timezone,
            self._check_capacity_exceedance,
            self._check_cross_sensor,
            self._check_future_timestamps,
            self._check_energy_power_consistency,
        ]

        for check_fn in checks:
            try:
                finding = check_fn(readings)
                if finding:
                    report.findings.append(finding)
                    if finding.severity == ValidationSeverity.ERROR:
                        report.overall_pass = False
            except Exception as exc:
                report.findings.append(ValidationFinding(
                    check_name=check_fn.__name__.replace("_check_", ""),
                    severity=ValidationSeverity.WARNING,
                    message=f"Check failed with error: {exc}",
                ))

        return report

    # --- Individual checks ---

    def _check_timestamp_order(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check timestamps are monotonically non-decreasing."""
        out_of_order = 0
        for i in range(1, len(readings)):
            if readings[i].timestamp < readings[i - 1].timestamp:
                out_of_order += 1
        if out_of_order > 0:
            return ValidationFinding(
                check_name="timestamp_order",
                severity=ValidationSeverity.ERROR,
                message=f"{out_of_order} readings are out of chronological order",
                affected_count=out_of_order,
                affected_pct=round(out_of_order / len(readings) * 100, 2),
            )
        return None

    def _check_duplicates(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check for duplicate (timestamp, device_id) pairs."""
        seen: set[tuple] = set()
        dupes = 0
        for r in readings:
            key = (r.timestamp, r.device_id)
            if key in seen:
                dupes += 1
            seen.add(key)
        if dupes > 0:
            pct = round(dupes / len(readings) * 100, 2)
            sev = ValidationSeverity.ERROR if pct > 5 else ValidationSeverity.WARNING
            return ValidationFinding(
                check_name="duplicates",
                severity=sev,
                message=f"{dupes} duplicate timestamp/device pairs ({pct}%)",
                affected_count=dupes,
                affected_pct=pct,
            )
        return None

    def _check_null_power(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check fraction of readings with null power_kw."""
        nulls = sum(1 for r in readings if r.power_kw is None)
        if nulls == 0:
            return None
        pct = round(nulls / len(readings) * 100, 2)
        sev = ValidationSeverity.WARNING if pct < 20 else ValidationSeverity.ERROR
        return ValidationFinding(
            check_name="null_power",
            severity=sev,
            message=f"{nulls} readings have null power_kw ({pct}%)",
            affected_count=nulls,
            affected_pct=pct,
        )

    def _check_null_irradiance(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check fraction of readings with no irradiance data."""
        no_irr = sum(
            1 for r in readings
            if r.poa_wm2 is None and r.ghi_wm2 is None and r.gti_wm2 is None
        )
        if no_irr == 0:
            return None
        pct = round(no_irr / len(readings) * 100, 2)
        sev = ValidationSeverity.INFO if pct < 50 else ValidationSeverity.WARNING
        return ValidationFinding(
            check_name="null_irradiance",
            severity=sev,
            message=f"{no_irr} readings have no irradiance data ({pct}%)",
            affected_count=no_irr,
            affected_pct=pct,
        )

    def _check_numeric_ranges(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check that numeric values fall within plausible physical ranges."""
        ranges = QualityScorer.PLAUSIBILITY_RANGES
        violations = 0
        detail_counts: dict[str, int] = {}
        for r in readings:
            for field, (lo, hi) in ranges.items():
                val = getattr(r, field, None)
                if val is not None and not (lo <= val <= hi):
                    violations += 1
                    detail_counts[field] = detail_counts.get(field, 0) + 1
        if violations == 0:
            return None
        pct = round(violations / len(readings) * 100, 2)
        sev = ValidationSeverity.WARNING if pct < 5 else ValidationSeverity.ERROR
        return ValidationFinding(
            check_name="numeric_ranges",
            severity=sev,
            message=f"{violations} out-of-range values across {len(detail_counts)} fields ({pct}%)",
            affected_count=violations,
            affected_pct=pct,
            details={"field_counts": detail_counts},
        )

    def _check_rate_of_change(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check for implausible power ramp rates between consecutive readings."""
        if self.ramp_rate_kw_per_min is None:
            # Auto-detect: use 5× median delta as threshold
            deltas = []
            for i in range(1, min(len(readings), 500)):
                p0 = readings[i - 1].power_kw
                p1 = readings[i].power_kw
                dt = (readings[i].timestamp - readings[i - 1].timestamp).total_seconds()
                if p0 is not None and p1 is not None and dt > 0:
                    deltas.append(abs(p1 - p0) / (dt / 60))
            if not deltas:
                return None
            threshold = statistics.median(deltas) * 5
        else:
            threshold = self.ramp_rate_kw_per_min

        if threshold <= 0:
            return None

        violations = 0
        for i in range(1, len(readings)):
            p0 = readings[i - 1].power_kw
            p1 = readings[i].power_kw
            dt = (readings[i].timestamp - readings[i - 1].timestamp).total_seconds()
            if p0 is not None and p1 is not None and dt > 0:
                ramp = abs(p1 - p0) / (dt / 60)
                if ramp > threshold:
                    violations += 1

        if violations == 0:
            return None
        return ValidationFinding(
            check_name="rate_of_change",
            severity=ValidationSeverity.WARNING,
            message=f"{violations} readings exceed ramp-rate threshold ({threshold:.1f} kW/min)",
            affected_count=violations,
            affected_pct=round(violations / max(len(readings) - 1, 1) * 100, 2),
        )

    def _check_night_power(self, readings: list[Reading]) -> ValidationFinding | None:
        """Flag readings where power > 0 but irradiance ≈ 0 (night-time leak)."""
        violations = 0
        for r in readings:
            irr = r.poa_wm2 or r.ghi_wm2 or r.gti_wm2
            if irr is not None and irr < 5 and r.power_kw is not None and r.power_kw > 1:
                violations += 1
        if violations == 0:
            return None
        return ValidationFinding(
            check_name="night_power",
            severity=ValidationSeverity.WARNING,
            message=f"{violations} readings have power > 1 kW with irradiance < 5 W/m²",
            affected_count=violations,
            affected_pct=round(violations / len(readings) * 100, 2),
        )

    def _check_irradiance_consistency(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check GHI ≈ DNI·cos(θ) + DHI where all three are present."""
        violations = 0
        checked = 0
        for r in readings:
            if r.ghi_wm2 is not None and r.dni_wm2 is not None and r.dhi_wm2 is not None:
                checked += 1
                # Simplified check: GHI should be <= DNI + DHI (ignoring cos(z))
                # and GHI should be >= DHI
                if r.ghi_wm2 > r.dni_wm2 + r.dhi_wm2 + 50:
                    violations += 1
                elif r.ghi_wm2 < r.dhi_wm2 - 20:
                    violations += 1
        if checked == 0 or violations == 0:
            return None
        return ValidationFinding(
            check_name="irradiance_consistency",
            severity=ValidationSeverity.WARNING,
            message=f"{violations}/{checked} readings have inconsistent GHI/DNI/DHI",
            affected_count=violations,
            affected_pct=round(violations / checked * 100, 2),
        )

    def _check_stuck_sensor(self, readings: list[Reading]) -> ValidationFinding | None:
        """Detect stuck sensors — same value repeated > N consecutive times."""
        stuck_fields: dict[str, int] = {}
        fields_to_check = ["power_kw", "poa_wm2", "voltage_v"]

        for field in fields_to_check:
            run_length = 1
            max_run = 1
            for i in range(1, len(readings)):
                v_prev = getattr(readings[i - 1], field, None)
                v_curr = getattr(readings[i], field, None)
                if (
                    v_prev is not None
                    and v_curr is not None
                    and v_prev == v_curr
                    and v_curr != 0  # zero runs are normal at night
                ):
                    run_length += 1
                    max_run = max(max_run, run_length)
                else:
                    run_length = 1
            if max_run >= self.stuck_threshold:
                stuck_fields[field] = max_run

        if not stuck_fields:
            return None
        return ValidationFinding(
            check_name="stuck_sensor",
            severity=ValidationSeverity.WARNING,
            message=f"Stuck sensor detected: {stuck_fields}",
            affected_count=sum(stuck_fields.values()),
            details={"stuck_fields": stuck_fields},
        )

    def _check_timezone(self, readings: list[Reading]) -> ValidationFinding | None:
        """Verify all timestamps have timezone info (preferably UTC)."""
        no_tz = sum(1 for r in readings if r.timestamp.tzinfo is None)
        if no_tz == 0:
            return None
        return ValidationFinding(
            check_name="timezone",
            severity=ValidationSeverity.WARNING,
            message=f"{no_tz} readings have timezone-naive timestamps",
            affected_count=no_tz,
            affected_pct=round(no_tz / len(readings) * 100, 2),
        )

    def _check_capacity_exceedance(self, readings: list[Reading]) -> ValidationFinding | None:
        """Check if power exceeds plant capacity (with 10% headroom)."""
        if self.plant_capacity_kw is None or self.plant_capacity_kw <= 0:
            return None
        limit = self.plant_capacity_kw * 1.10  # 10% headroom
        violations = sum(
            1 for r in readings
            if r.power_kw is not None and r.power_kw > limit
        )
        if violations == 0:
            return None
        return ValidationFinding(
            check_name="capacity_exceedance",
            severity=ValidationSeverity.WARNING,
            message=(
                f"{violations} readings exceed plant capacity "
                f"({self.plant_capacity_kw} kW + 10% = {limit:.0f} kW)"
            ),
            affected_count=violations,
            affected_pct=round(violations / len(readings) * 100, 2),
        )

    def _check_cross_sensor(self, readings: list[Reading]) -> ValidationFinding | None:
        """
        Check agreement across devices at each timestamp.

        Groups readings by timestamp, then checks if per-device power values
        are within ±50% of the median (flags outliers).
        """
        from collections import defaultdict
        by_ts: dict[datetime, list[Reading]] = defaultdict(list)
        for r in readings:
            if r.power_kw is not None and r.device_id:
                by_ts[r.timestamp].append(r)

        outliers = 0
        total_groups = 0
        for ts, group in by_ts.items():
            if len(group) < 3:
                continue
            total_groups += 1
            powers = [r.power_kw for r in group if r.power_kw is not None]
            if not powers:
                continue
            med = statistics.median(powers)
            if med == 0:
                continue
            for p in powers:
                if abs(p - med) / med > 0.50:
                    outliers += 1

        if outliers == 0:
            return None
        return ValidationFinding(
            check_name="cross_sensor",
            severity=ValidationSeverity.WARNING,
            message=f"{outliers} device readings deviate > 50% from median at their timestamp",
            affected_count=outliers,
            details={"timestamps_checked": total_groups},
        )

    def _check_future_timestamps(self, readings: list[Reading]) -> ValidationFinding | None:
        """Flag readings with timestamps in the future."""
        now = datetime.now(timezone.utc)
        future = sum(1 for r in readings if r.timestamp > now + timedelta(hours=1))
        if future == 0:
            return None
        return ValidationFinding(
            check_name="future_timestamps",
            severity=ValidationSeverity.ERROR,
            message=f"{future} readings have timestamps in the future",
            affected_count=future,
            affected_pct=round(future / len(readings) * 100, 2),
        )

    def _check_energy_power_consistency(self, readings: list[Reading]) -> ValidationFinding | None:
        """
        Check that energy ≈ power × interval for readings where both are present.

        Tolerance: ±50% (accounts for varying load within interval).
        """
        violations = 0
        checked = 0
        for r in readings:
            if (
                r.power_kw is not None
                and r.energy_kwh is not None
                and r.interval_seconds
                and r.interval_seconds > 0
                and r.power_kw > 0
            ):
                checked += 1
                expected_kwh = r.power_kw * (r.interval_seconds / 3600)
                if expected_kwh > 0:
                    ratio = r.energy_kwh / expected_kwh
                    if ratio < 0.5 or ratio > 2.0:
                        violations += 1
        if checked == 0 or violations == 0:
            return None
        return ValidationFinding(
            check_name="energy_power_consistency",
            severity=ValidationSeverity.WARNING,
            message=f"{violations}/{checked} readings have energy/power mismatch (>2× or <0.5×)",
            affected_count=violations,
            affected_pct=round(violations / checked * 100, 2),
        )
