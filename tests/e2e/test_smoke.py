"""E2E smoke tests: import every module and verify render() or key exports exist."""

from __future__ import annotations

import importlib
import sys

import pytest


# Modules that should NOT be imported (they require Streamlit at import time)
_STREAMLIT_MODULES = {
    "app",
    "components.auth_ui",
    "components.breadcrumbs",
    "components.contextual_help",
    "components.data_health",
    "components.global_search",
    "components.job_monitor",
    "components.keyboard_shortcuts",
    "components.kpi_cards",
    "components.layouts",
    "components.notifications_ui",
    "components.preferences_ui",
    "components.report_button",
    "components.sidebar",
    "components.ux",
    "modules.alerts_dashboard",
    "modules.anomaly_detection_ui",
    "modules.api_management_ui",
    "modules.chart_utils",
    "modules.clipping_analysis",
    "modules.comparative_analysis",
    "modules.curtailment_analysis",
    "modules.dashboard",
    "modules.data_explorer",
    "modules.data_export_ui",
    "modules.data_quality_dashboard",
    "modules.degradation_analysis",
    "modules.financial_dashboard",
    "modules.fouling",
    "modules.loss_waterfall",
    "modules.plant_detail",
    "modules.plant_management",
    "modules.poa_import",
    "modules.portfolio_map",
    "modules.pr_trending",
    "modules.report_builder",
    "modules.report_library_ui",
    "modules.shading",
    "modules.site_monitor",
    "modules.system_health",
    "modules.tariff_management",
    "modules.thermal_loss",
    "modules.ticket_kanban",
}

# Service modules that should be safely importable without Streamlit
_SERVICE_MODULES = [
    "services.database.engine",
    "services.database.repository",
    "services.alerts.models",
    "services.alerts.repository",
    "services.alerts.ticketing",
    "services.alerts.default_rules",
    "services.alerts.notifications",
    "services.analysis.base",
    "services.analysis.clipping",
    "services.analysis.curtailment",
    "services.analysis.degradation",
    "services.analysis.fouling",
    "services.analysis.shading",
    "services.analysis.thermal",
    "services.analysis.waterfall",
    "services.analysis.pr_trending",
    "services.analysis.comparative",
    "services.data_quality.validators",
    "services.data_quality.quality_scorer",
    "services.data_quality.gap_detection",
    "services.data_quality.gap_filling",
    "services.data_quality.harmonization",
    "services.data_quality.sensor_health",
    "services.data_quality.source_priority",
    "services.ingestion.base",
    "services.ingestion.coordinator",
    "services.reporting.models",
    "services.reporting.templates",
]


@pytest.mark.e2e
class TestServiceImports:
    """Verify all service modules import cleanly without Streamlit."""

    @pytest.mark.parametrize("module_name", _SERVICE_MODULES)
    def test_import_service_module(self, module_name):
        mod = importlib.import_module(module_name)
        assert mod is not None


@pytest.mark.e2e
class TestKeyExports:
    """Verify key classes/functions are accessible from package-level imports."""

    def test_database_engine_exports(self):
        from solar_platform.db.engine import DuckDBEngine, get_engine
        assert callable(get_engine)
        assert DuckDBEngine is not None

    def test_repository_exports(self):
        from solar_platform.db.repository import (
            PlantRepository,
            ReadingsRepository,
            SolarDataRepository,
        )
        assert PlantRepository is not None
        assert ReadingsRepository is not None
        assert SolarDataRepository is not None

    def test_alert_model_exports(self):
        from solar_platform.alerts.models import (
            Alert,
            AlertRule,
            AlertSeverity,
            AlertStatus,
            Ticket,
            TicketPriority,
            TicketStatus,
        )
        assert Alert is not None
        assert AlertRule is not None
        assert len(AlertSeverity) == 3
        assert len(AlertStatus) == 4

    def test_analysis_exports(self):
        from solar_platform.analysis import (
            AnalysisEngine,
            AnalysisResult,
            ClippingEngine,
            CurtailmentEngine,
            DegradationEngine,
            FoulingEngine,
            ThermalLossEngine,
        )
        assert AnalysisResult is not None

    def test_data_quality_exports(self):
        from services.data_quality import (
            DEFAULT_VALIDATORS,
            GapDetector,
            QualityScorer,
            RangeValidator,
            ValidationReport,
            run_validation,
        )
        assert callable(run_validation)
        assert len(DEFAULT_VALIDATORS) >= 5

    def test_ingestion_exports(self):
        from services.ingestion import (
            DataSourceAdapter,
            IngestionCoordinator,
            Reading,
            ReadingBatch,
        )
        assert DataSourceAdapter is not None
        assert IngestionCoordinator is not None

    def test_reporting_exports(self):
        from solar_platform.reporting.models import (
            GeneratedReport,
            ReportSection,
            ReportTemplate,
            ReportType,
            SectionType,
        )
        from solar_platform.reporting.templates import ALL_TEMPLATES, get_template
        assert len(ALL_TEMPLATES) >= 3
        assert callable(get_template)
