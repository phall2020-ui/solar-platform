"""Import verification for Phase 5, 6, 7 modules."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)).rsplit("scripts", 1)[0])

# Pre-import to avoid circular import issues
import unified_config

errors = []

modules_to_test = [
    # Phase 5 — Reporting
    "services.reporting",
    "services.reporting.models",
    "services.reporting.data_fetcher",
    "services.reporting.pdf_renderer",
    "services.reporting.chart_exporter",
    "services.reporting.templates",
    "services.reporting.report_library",
    "services.reporting.scheduler",
    # Phase 6 — Data Quality
    "services.data_quality",
    "services.data_quality.validators",
    "services.data_quality.quality_scorer",
    "services.data_quality.source_priority",
    "services.data_quality.gap_detection",
    "services.data_quality.gap_filling",
    "services.data_quality.harmonization",
    "services.data_quality.sensor_health",
    # Phase 7 — Analytics
    "services.analytics",
    "services.analytics.anomaly_detection",
    "services.analytics.forecasting",
    # Phase 7 — Financial
    "services.financial",
    "services.financial.revenue",
    "services.financial.tariff",
    "services.financial.budget",
    # Phase 7 — Other services
    "services.pvsyst_import",
    "services.access_control",
    # Phase 7 — API (may fail if fastapi not installed)
    "api",
    # UI modules (need streamlit)
    "modules.report_builder",
    "modules.report_library_ui",
    "modules.data_quality_dashboard",
    "modules.anomaly_detection_ui",
    "modules.financial_dashboard",
    "modules.tariff_management",
    # Page registry (verify new pages registered)
    "services.page_registry",
]

for mod_name in modules_to_test:
    try:
        __import__(mod_name)
        print(f"OK   {mod_name}")
    except Exception as e:
        short = str(e).split("\n")[0][:120]
        errors.append((mod_name, short))
        print(f"FAIL {mod_name}: {short}")

print(f"\nTotal errors: {len(errors)}")
if not errors:
    print("ALL IMPORTS OK")
else:
    print("FAILURES:")
    for mod, err in errors:
        print(f"  {mod}: {err}")
