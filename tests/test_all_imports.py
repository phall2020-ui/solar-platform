"""Import verification for all core library modules."""
import importlib
import sys


MODULES = [
    "solar_platform.analysis",
    "solar_platform.analysis.base",
    "solar_platform.analysis.clipping",
    "solar_platform.analysis.curtailment",
    "solar_platform.analysis.shading",
    "solar_platform.analysis.fouling",
    "solar_platform.analysis.thermal",
    "solar_platform.analysis.waterfall",
    "solar_platform.analysis.comparative",
    "solar_platform.analysis.pr_trending",
    "solar_platform.analysis.degradation",
    "solar_platform.analysis.chart_templates",
    "solar_platform.analysis.helpers",
    "solar_platform.alerts",
    "solar_platform.alerts.models",
    "solar_platform.alerts.engine",
    "solar_platform.alerts.repository",
    "solar_platform.alerts.default_rules",
    "solar_platform.alerts.lifecycle",
    "solar_platform.alerts.notifications",
    "solar_platform.alerts.ticketing",
    "solar_platform.data_quality",
    "solar_platform.data_quality.validators",
    "solar_platform.data_quality.quality_scorer",
    "solar_platform.data_quality.gap_detection",
    "solar_platform.data_quality.gap_filling",
    "solar_platform.data_quality.harmonization",
    "solar_platform.data_quality.sensor_health",
    "solar_platform.data_quality.source_priority",
    "solar_platform.financial",
    "solar_platform.financial.revenue",
    "solar_platform.financial.tariff",
    "solar_platform.financial.budget",
    "solar_platform.analytics.anomaly_detection",
    "solar_platform.analytics.forecasting",
    "solar_platform.reporting",
    "solar_platform.reporting.models",
    "solar_platform.reporting.pdf_renderer",
    "solar_platform.reporting.templates",
    "solar_platform.reporting.report_library",
    "solar_platform.reporting.scheduler",
    "solar_platform.reporting.chart_exporter",
    "solar_platform.reporting.data_fetcher",
]


def main():
    errors = []
    for mod in MODULES:
        try:
            importlib.import_module(mod)
            print(f"  OK  {mod}")
        except Exception as e:
            errors.append((mod, str(e)))
            print(f"  FAIL {mod}: {e}")

    ok = len(MODULES) - len(errors)
    print(f"\n{ok}/{len(MODULES)} imports OK, {len(errors)} errors")
    return len(errors)


if __name__ == "__main__":
    sys.exit(main())
