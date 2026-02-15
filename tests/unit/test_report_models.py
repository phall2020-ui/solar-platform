"""Unit tests for reporting models."""
import pytest
from datetime import datetime, timezone


@pytest.mark.unit
class TestReportType:
    def test_monthly_performance(self):
        from solar_platform.reporting.models import ReportType
        assert ReportType.MONTHLY_PERFORMANCE == "monthly_performance"

    def test_excom_summary(self):
        from solar_platform.reporting.models import ReportType
        assert ReportType.EXCOM_SUMMARY == "excom_summary"

    def test_om_report(self):
        from solar_platform.reporting.models import ReportType
        assert ReportType.OM_REPORT == "om_report"

    def test_custom(self):
        from solar_platform.reporting.models import ReportType
        assert ReportType.CUSTOM == "custom"


@pytest.mark.unit
class TestSectionType:
    def test_cover(self):
        from solar_platform.reporting.models import SectionType
        assert SectionType.COVER == "cover"

    def test_kpi_summary(self):
        from solar_platform.reporting.models import SectionType
        assert SectionType.KPI_SUMMARY == "kpi_summary"

    def test_waterfall(self):
        from solar_platform.reporting.models import SectionType
        assert SectionType.WATERFALL == "waterfall"

    def test_text(self):
        from solar_platform.reporting.models import SectionType
        assert SectionType.TEXT == "text"


@pytest.mark.unit
class TestReportSection:
    def test_minimal_section(self):
        from solar_platform.reporting.models import ReportSection, SectionType
        section = ReportSection(type=SectionType.COVER)
        assert section.type == SectionType.COVER
        assert section.title == ""
        assert section.plant_uid is None
        assert section.config == {}
        assert section.page_break_before is False

    def test_section_with_all_fields(self):
        from solar_platform.reporting.models import ReportSection, SectionType
        section = ReportSection(
            type=SectionType.PLANT_DETAIL,
            title="Plant A Detail",
            plant_uid="p1",
            config={"show_chart": True},
            page_break_before=True,
        )
        assert section.title == "Plant A Detail"
        assert section.plant_uid == "p1"
        assert section.config["show_chart"] is True
        assert section.page_break_before is True


@pytest.mark.unit
class TestReportTemplate:
    def test_minimal_template(self):
        from solar_platform.reporting.models import ReportTemplate, ReportType
        template = ReportTemplate(name="Monthly", type=ReportType.MONTHLY_PERFORMANCE)
        assert template.name == "Monthly"
        assert template.type == ReportType.MONTHLY_PERFORMANCE
        assert template.id  # auto-generated uuid
        assert template.orientation == "portrait"
        assert template.paper_size == "A4"
        assert template.include_cover is True
        assert template.sections == []

    def test_template_with_sections(self):
        from solar_platform.reporting.models import ReportTemplate, ReportType, ReportSection, SectionType
        sections = [
            ReportSection(type=SectionType.COVER, title="Cover"),
            ReportSection(type=SectionType.KPI_SUMMARY, title="KPIs"),
        ]
        template = ReportTemplate(
            name="Full Report",
            type=ReportType.EXCOM_SUMMARY,
            sections=sections,
            orientation="landscape",
        )
        assert len(template.sections) == 2
        assert template.orientation == "landscape"

    def test_template_serialization(self):
        from solar_platform.reporting.models import ReportTemplate, ReportType
        template = ReportTemplate(name="Test", type=ReportType.CUSTOM)
        data = template.model_dump()
        assert data["name"] == "Test"
        assert data["type"] == "custom"
        assert "id" in data


@pytest.mark.unit
class TestGeneratedReport:
    def test_minimal_report(self):
        from solar_platform.reporting.models import GeneratedReport, ReportType
        now = datetime.now(timezone.utc)
        report = GeneratedReport(
            template_id="t1",
            template_name="Monthly",
            report_type=ReportType.MONTHLY_PERFORMANCE,
            period_start=now,
            period_end=now,
        )
        assert report.status == "pending"
        assert report.file_path == ""
        assert report.page_count == 0
        assert report.plant_uids == []

    def test_complete_report(self):
        from solar_platform.reporting.models import GeneratedReport, ReportType
        now = datetime.now(timezone.utc)
        report = GeneratedReport(
            template_id="t1",
            template_name="Monthly",
            report_type=ReportType.MONTHLY_PERFORMANCE,
            period_start=now,
            period_end=now,
            status="complete",
            file_path="/reports/test.pdf",
            page_count=10,
            plant_uids=["p1", "p2"],
            generation_seconds=3.5,
        )
        assert report.status == "complete"
        assert report.page_count == 10
        assert len(report.plant_uids) == 2

    def test_report_serialization(self):
        from solar_platform.reporting.models import GeneratedReport, ReportType
        now = datetime.now(timezone.utc)
        report = GeneratedReport(
            template_id="t1",
            template_name="Test",
            report_type=ReportType.CUSTOM,
            period_start=now,
            period_end=now,
        )
        data = report.model_dump()
        assert data["template_id"] == "t1"
        assert data["report_type"] == "custom"
        assert "id" in data
