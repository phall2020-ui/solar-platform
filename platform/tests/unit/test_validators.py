"""Unit tests for data quality validators."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestValidationSeverity:
    def test_error_value(self):
        from services.data_quality.validators import ValidationSeverity
        assert ValidationSeverity.ERROR == "error"

    def test_warning_value(self):
        from services.data_quality.validators import ValidationSeverity
        assert ValidationSeverity.WARNING == "warning"

    def test_info_value(self):
        from services.data_quality.validators import ValidationSeverity
        assert ValidationSeverity.INFO == "info"


@pytest.mark.unit
class TestValidationResult:
    def test_frozen_dataclass(self):
        from services.data_quality.validators import ValidationResult, ValidationSeverity
        r = ValidationResult(
            validator_name="test",
            severity=ValidationSeverity.ERROR,
            message="bad value",
            field_name="power_kw",
            value=999,
            threshold=500,
        )
        assert r.validator_name == "test"
        assert r.severity == ValidationSeverity.ERROR
        assert r.message == "bad value"
        assert r.field_name == "power_kw"
        assert r.value == 999
        assert r.threshold == 500


@pytest.mark.unit
class TestValidationReport:
    def test_empty_report_quality_score(self):
        from services.data_quality.validators import ValidationReport
        report = ValidationReport()
        assert report.quality_score == 100.0

    def test_quality_score_deducts_errors(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.ERROR, "err"))
        assert report.quality_score == 90.0

    def test_quality_score_deducts_warnings(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.WARNING, "warn"))
        assert report.quality_score == 97.0

    def test_quality_score_min_is_zero(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        for _ in range(15):
            report.add(ValidationResult("t", ValidationSeverity.ERROR, "err"))
        assert report.quality_score == 0.0

    def test_passed_true_when_no_errors(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.WARNING, "w"))
        assert report.passed is True

    def test_passed_false_when_errors(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.ERROR, "e"))
        assert report.passed is False

    def test_error_count(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.ERROR, "e"))
        report.add(ValidationResult("t", ValidationSeverity.ERROR, "e2"))
        report.add(ValidationResult("t", ValidationSeverity.WARNING, "w"))
        assert report.error_count == 2

    def test_warning_count(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        report = ValidationReport()
        report.add(ValidationResult("t", ValidationSeverity.WARNING, "w1"))
        report.add(ValidationResult("t", ValidationSeverity.WARNING, "w2"))
        assert report.warning_count == 2

    def test_merge_combines_reports(self):
        from services.data_quality.validators import ValidationReport, ValidationResult, ValidationSeverity
        r1 = ValidationReport(total_checked=1)
        r1.add(ValidationResult("t", ValidationSeverity.ERROR, "e"))
        r2 = ValidationReport(total_checked=2)
        r2.add(ValidationResult("t", ValidationSeverity.WARNING, "w"))
        r1.merge(r2)
        assert len(r1.results) == 2
        assert r1.total_checked == 3


@pytest.mark.unit
class TestRangeValidator:
    def test_within_range_passes(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"power_kw": 100.0}, {})
        assert results == []

    def test_above_range_flags_error(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"power_kw": 600_000}, {})
        assert len(results) == 1
        assert results[0].severity.value == "error"
        assert results[0].field_name == "power_kw"

    def test_below_range_flags_error(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"ghi_wm2": -10.0}, {})
        assert len(results) == 1
        assert results[0].field_name == "ghi_wm2"

    def test_none_value_skipped(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"power_kw": None}, {})
        assert results == []

    def test_non_numeric_value_skipped(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"power_kw": "not_a_number"}, {})
        assert results == []

    def test_custom_ranges(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator(ranges={"custom_field": (0.0, 10.0)})
        results = v.validate({"custom_field": 15.0}, {})
        assert len(results) == 1

    def test_boundary_value_passes(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        # 0.0 is the lower boundary for power_kw and should pass
        results = v.validate({"power_kw": 0.0}, {})
        assert results == []

    def test_multiple_fields_checked(self):
        from services.data_quality.validators import RangeValidator
        v = RangeValidator()
        results = v.validate({"power_kw": -1.0, "ghi_wm2": 2000.0}, {})
        assert len(results) == 2


@pytest.mark.unit
class TestCapacityExceedanceValidator:
    def test_within_capacity(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator()
        results = v.validate({"power_kw": 4500}, {"capacity_kw": 5000})
        assert results == []

    def test_exceeds_capacity(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator()
        results = v.validate({"power_kw": 6000}, {"capacity_kw": 5000})
        assert len(results) == 1
        assert results[0].severity.value == "warning"

    def test_no_capacity_in_config(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator()
        results = v.validate({"power_kw": 6000}, {})
        assert results == []

    def test_no_power_reading(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator()
        results = v.validate({}, {"capacity_kw": 5000})
        assert results == []

    def test_uses_capacity_kwp_fallback(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator()
        results = v.validate({"power_kw": 6000}, {"capacity_kwp": 5000})
        assert len(results) == 1

    def test_custom_tolerance(self):
        from services.data_quality.validators import CapacityExceedanceValidator
        v = CapacityExceedanceValidator(tolerance_pct=1.50)
        # 6000 is within 150% of 5000 (7500)
        results = v.validate({"power_kw": 6000}, {"capacity_kw": 5000})
        assert results == []


@pytest.mark.unit
class TestNegativeValueValidator:
    def test_positive_value_passes(self):
        from services.data_quality.validators import NegativeValueValidator
        v = NegativeValueValidator()
        results = v.validate({"power_kw": 100.0, "energy_kwh": 50.0}, {})
        assert results == []

    def test_negative_value_flagged(self):
        from services.data_quality.validators import NegativeValueValidator
        v = NegativeValueValidator()
        results = v.validate({"power_kw": -10.0}, {})
        assert len(results) == 1
        assert results[0].severity.value == "error"

    def test_zero_value_passes(self):
        from services.data_quality.validators import NegativeValueValidator
        v = NegativeValueValidator()
        results = v.validate({"power_kw": 0.0}, {})
        assert results == []

    def test_none_value_skipped(self):
        from services.data_quality.validators import NegativeValueValidator
        v = NegativeValueValidator()
        results = v.validate({"power_kw": None}, {})
        assert results == []

    def test_multiple_negatives(self):
        from services.data_quality.validators import NegativeValueValidator
        v = NegativeValueValidator()
        results = v.validate({"power_kw": -5.0, "energy_kwh": -2.0}, {})
        assert len(results) == 2


@pytest.mark.unit
class TestNighttimeGenerationValidator:
    def test_daytime_generation_passes(self):
        from services.data_quality.validators import NighttimeGenerationValidator
        v = NighttimeGenerationValidator()
        results = v.validate({"power_kw": 100.0, "poa_wm2": 500.0}, {})
        assert results == []

    def test_nighttime_generation_flagged(self):
        from services.data_quality.validators import NighttimeGenerationValidator
        v = NighttimeGenerationValidator()
        results = v.validate({"power_kw": 100.0, "poa_wm2": 0.0}, {})
        assert len(results) == 1
        assert results[0].severity.value == "warning"

    def test_no_irradiance_skipped(self):
        from services.data_quality.validators import NighttimeGenerationValidator
        v = NighttimeGenerationValidator()
        results = v.validate({"power_kw": 100.0}, {})
        assert results == []

    def test_low_power_skipped(self):
        from services.data_quality.validators import NighttimeGenerationValidator
        v = NighttimeGenerationValidator()
        results = v.validate({"power_kw": 0.5, "poa_wm2": 0.0}, {})
        assert results == []

    def test_ghi_fallback(self):
        from services.data_quality.validators import NighttimeGenerationValidator
        v = NighttimeGenerationValidator()
        results = v.validate({"power_kw": 100.0, "ghi_wm2": 2.0}, {})
        assert len(results) == 1


@pytest.mark.unit
class TestStalenessValidator:
    def test_recent_reading_passes(self):
        from services.data_quality.validators import StalenessValidator
        v = StalenessValidator()
        ts = datetime.now(timezone.utc) - timedelta(hours=1)
        results = v.validate({"timestamp": ts}, {})
        assert results == []

    def test_stale_reading_flagged(self):
        from services.data_quality.validators import StalenessValidator
        v = StalenessValidator(max_age_hours=24.0)
        ts = datetime.now(timezone.utc) - timedelta(hours=48)
        results = v.validate({"timestamp": ts}, {})
        assert len(results) == 1
        assert results[0].severity.value == "warning"

    def test_no_timestamp_skipped(self):
        from services.data_quality.validators import StalenessValidator
        v = StalenessValidator()
        results = v.validate({}, {})
        assert results == []

    def test_string_timestamp_parsed(self):
        from services.data_quality.validators import StalenessValidator
        v = StalenessValidator(max_age_hours=1.0)
        ts_str = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        results = v.validate({"timestamp": ts_str}, {})
        assert len(results) == 1


@pytest.mark.unit
class TestFlatLineValidator:
    def test_single_reading_noop(self):
        from services.data_quality.validators import FlatLineValidator
        v = FlatLineValidator()
        results = v.validate({"power_kw": 100.0}, {})
        assert results == []

    def test_series_with_flatline(self):
        from services.data_quality.validators import FlatLineValidator
        v = FlatLineValidator(fields=["power_kw"], min_repeat=3)
        readings = [{"power_kw": 100.0} for _ in range(5)]
        results = v.validate_series(readings, {})
        assert len(results) == 1
        assert "stuck" in results[0].message

    def test_series_no_flatline(self):
        from services.data_quality.validators import FlatLineValidator
        v = FlatLineValidator(fields=["power_kw"], min_repeat=3)
        readings = [{"power_kw": float(i)} for i in range(5)]
        results = v.validate_series(readings, {})
        assert results == []

    def test_series_below_threshold(self):
        from services.data_quality.validators import FlatLineValidator
        v = FlatLineValidator(fields=["power_kw"], min_repeat=6)
        readings = [{"power_kw": 100.0} for _ in range(4)]
        results = v.validate_series(readings, {})
        assert results == []


@pytest.mark.unit
class TestRunValidation:
    def test_returns_validation_report(self):
        from services.data_quality.validators import run_validation
        report = run_validation({"power_kw": 100.0}, {"capacity_kw": 5000})
        assert hasattr(report, "quality_score")
        assert report.total_checked == 1

    def test_catches_validator_exceptions(self):
        from services.data_quality.validators import run_validation, ReadingValidator, ValidationResult
        
        class BrokenValidator:
            name = "broken"
            def validate(self, reading, plant_config):
                raise RuntimeError("boom")
        
        report = run_validation({"power_kw": 100.0}, {}, validators=[BrokenValidator()])
        assert report.total_checked == 1
        # Should not raise despite broken validator
