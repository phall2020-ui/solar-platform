"""Quick smoke test for services.reporting package imports."""
import sys
try:
    from services.reporting.models import ReportType, SectionType, ReportSection, ReportTemplate, GeneratedReport
    print("models OK")

    from services.reporting.templates import ALL_TEMPLATES, get_template, MONTHLY_REPORT, EXCOM_REPORT, OM_REPORT
    print(f"templates OK - {len(ALL_TEMPLATES)} templates: {list(ALL_TEMPLATES.keys())}")

    from services.reporting.chart_exporter import chart_to_png, cleanup_temp_images
    print("chart_exporter OK")

    from services.reporting.data_fetcher import ReportDataFetcher
    print("data_fetcher OK")

    from services.reporting.pdf_renderer import PDFRenderer
    print("pdf_renderer OK")

    from services.reporting.report_library import ReportLibrary
    print("report_library OK")

    from services.reporting.scheduler import ReportScheduler, REPORT_SCHEDULES
    print(f"scheduler OK - {len(REPORT_SCHEDULES)} schedules")

    from services.reporting import ReportType, SectionType, ALL_TEMPLATES, get_template
    print("__init__ re-exports OK")

    # Quick model instantiation check
    from datetime import UTC, datetime
    section = ReportSection(type=SectionType.COVER, title="Test")
    assert section.type == SectionType.COVER
    tmpl = get_template("monthly_performance")
    assert tmpl is not None
    assert tmpl.name == "Monthly Performance Report"
    print("model instantiation OK")

    print("\nALL IMPORTS PASSED")
except Exception as e:
    print(f"FAILED: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
