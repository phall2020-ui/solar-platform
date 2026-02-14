"""Import verification for all service modules."""
import importlib
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MODULES = [
    "services.analysis",
    "services.analysis.base",
    "services.analysis.clipping",
    "services.analysis.curtailment",
    "services.analysis.shading",
    "services.analysis.fouling",
    "services.analysis.thermal",
    "services.analysis.waterfall",
    "services.analysis.comparative",
    "services.analysis.pr_trending",
    "services.analysis.degradation",
    "services.analysis.chart_templates",
    "services.analysis.helpers",
    "services.alerts",
    "services.alerts.models",
    "services.alerts.engine",
    "services.alerts.repository",
    "services.alerts.default_rules",
    "services.alerts.lifecycle",
    "services.alerts.notifications",
    "services.alerts.ticketing",
    "services.data_quality",
    "services.data_quality.validators",
    "services.data_quality.quality_scorer",
    "services.data_quality.gap_detection",
    "services.data_quality.gap_filling",
    "services.data_quality.harmonization",
    "services.data_quality.sensor_health",
    "services.data_quality.source_priority",
    "services.financial",
    "services.financial.revenue",
    "services.financial.tariff",
    "services.financial.budget",
    "services.analytics.anomaly_detection",
    "services.analytics.forecasting",
    "services.reporting",
    "services.reporting.models",
    "services.reporting.pdf_renderer",
    "services.reporting.templates",
    "services.reporting.report_library",
    "services.reporting.scheduler",
    "services.reporting.chart_exporter",
    "services.reporting.data_fetcher",
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
