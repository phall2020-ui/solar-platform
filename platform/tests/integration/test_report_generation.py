"""Integration tests for report generation: template + data → report objects."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.reporting.models import (
    GeneratedReport,
    ReportSection,
    ReportTemplate,
    ReportType,
    SectionType,
)
from services.reporting.templates import (
    ALL_TEMPLATES,
    EXCOM_REPORT,
    MONTHLY_REPORT,
    OM_REPORT,
    get_template,
)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestReportTemplates:
    """Test report template registry and structure."""

    def test_all_templates_registered(self):
        assert len(ALL_TEMPLATES) >= 3
        assert "monthly_performance" in ALL_TEMPLATES
        assert "excom_summary" in ALL_TEMPLATES
        assert "om_report" in ALL_TEMPLATES

    def test_get_template_by_type(self):
        tmpl = get_template("monthly_performance")
        assert tmpl is not None
        assert tmpl.type == ReportType.MONTHLY_PERFORMANCE

    def test_get_template_by_name(self):
        tmpl = get_template("Monthly Performance Report")
        assert tmpl is not None
        assert tmpl.type == ReportType.MONTHLY_PERFORMANCE

    def test_get_template_returns_none_for_unknown(self):
        assert get_template("nonexistent_template") is None

    def test_monthly_report_has_expected_sections(self):
        sections = MONTHLY_REPORT.sections
        types = [s.type for s in sections]
        assert SectionType.COVER in types
        assert SectionType.KPI_SUMMARY in types
        assert SectionType.GENERATION_TABLE in types

    def test_excom_report_is_landscape(self):
        assert EXCOM_REPORT.orientation == "landscape"

    def test_om_report_has_ticket_section(self):
        types = [s.type for s in OM_REPORT.sections]
        assert SectionType.TICKET_SUMMARY in types


@pytest.mark.integration
class TestGeneratedReport:
    """Test creating GeneratedReport objects from templates."""

    def test_create_report_from_template(self):
        tmpl = MONTHLY_REPORT
        report = GeneratedReport(
            template_id=tmpl.id,
            template_name=tmpl.name,
            report_type=tmpl.type,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
            period_label="January 2026",
            plant_uids=["uid-001", "uid-002"],
            status="pending",
        )
        assert report.template_name == "Monthly Performance Report"
        assert report.report_type == ReportType.MONTHLY_PERFORMANCE
        assert report.status == "pending"
        assert len(report.plant_uids) == 2

    def test_report_default_values(self):
        report = GeneratedReport(
            template_id="t-1",
            template_name="Test",
            report_type=ReportType.CUSTOM,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 1, 31, tzinfo=UTC),
        )
        assert report.status == "pending"
        assert report.file_path == ""
        assert report.page_count == 0
        assert report.id  # should be auto-generated UUID

    def test_report_section_model(self):
        section = ReportSection(
            type=SectionType.PR_CHART,
            title="PR Trend Chart",
            plant_uid="uid-001",
            page_break_before=True,
        )
        assert section.type == SectionType.PR_CHART
        assert section.plant_uid == "uid-001"
        assert section.page_break_before is True

    def test_custom_template_creation(self):
        tmpl = ReportTemplate(
            name="Custom Template",
            type=ReportType.CUSTOM,
            description="A custom report template",
            sections=[
                ReportSection(type=SectionType.COVER, title="Cover"),
                ReportSection(type=SectionType.TEXT, title="Notes",
                              config={"text": "Some custom text"}),
            ],
            orientation="landscape",
        )
        assert len(tmpl.sections) == 2
        assert tmpl.type == ReportType.CUSTOM
        assert tmpl.orientation == "landscape"
