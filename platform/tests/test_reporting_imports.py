"""Quick smoke test for services.reporting package imports."""

import pytest


def test_reporting_models_import():
    from services.reporting.models import ReportType, SectionType, ReportSection, ReportTemplate, GeneratedReport
    assert ReportType is not None
    assert SectionType is not None


def test_reporting_templates_import():
    from services.reporting.templates import ALL_TEMPLATES, get_template, MONTHLY_REPORT, EXCOM_REPORT, OM_REPORT
    assert len(ALL_TEMPLATES) > 0


def test_reporting_chart_exporter_import():
    from services.reporting.chart_exporter import chart_to_png, cleanup_temp_images
    assert callable(chart_to_png)


def test_reporting_data_fetcher_import():
    from services.reporting.data_fetcher import ReportDataFetcher
    assert ReportDataFetcher is not None


def test_reporting_pdf_renderer_import():
    from services.reporting.pdf_renderer import PDFRenderer
    assert PDFRenderer is not None


def test_reporting_library_import():
    from services.reporting.report_library import ReportLibrary
    assert ReportLibrary is not None


def test_reporting_scheduler_import():
    from services.reporting.scheduler import ReportScheduler, REPORT_SCHEDULES
    assert len(REPORT_SCHEDULES) > 0


def test_reporting_init_reexports():
    from services.reporting import ReportType, SectionType, ALL_TEMPLATES, get_template
    assert ReportType is not None
    assert callable(get_template)


def test_reporting_model_instantiation():
    from datetime import UTC, datetime
    from services.reporting.models import SectionType, ReportSection
    from services.reporting.templates import get_template

    section = ReportSection(type=SectionType.COVER, title="Test")
    assert section.type == SectionType.COVER

    tmpl = get_template("monthly_performance")
    assert tmpl is not None
    assert tmpl.name == "Monthly Performance Report"
