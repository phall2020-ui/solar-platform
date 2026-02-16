"""
Comprehensive import and compilation verification for the entire Solar Platform codebase.

Tests that every .py file compiles (no SyntaxError / IndentationError),
that all library modules import cleanly, and that no circular imports exist.

This file is fully self-contained — no external fixtures required.
"""
import ast
import importlib
import os
import py_compile
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
APP_DIR = ROOT / "app"
CLI_DIR = ROOT / "cli"
API_DIR = ROOT / "api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_py_files(directory: Path) -> list[str]:
    """Return sorted list of .py file paths under *directory*."""
    return sorted(
        str(p) for p in directory.rglob("*.py")
        if "__pycache__" not in str(p)
    )


def _rel(path: str) -> str:
    """Return a workspace-relative path for readable test IDs."""
    return os.path.relpath(path, ROOT)


# ---------------------------------------------------------------------------
# Module lists (explicit, for parametrized import tests)
# ---------------------------------------------------------------------------

SOLAR_PLATFORM_LIBRARY_MODULES = [
    # Top-level
    "solar_platform",
    "solar_platform.config",
    "solar_platform.constants",
    "solar_platform.models",
    # analysis
    "solar_platform.analysis",
    "solar_platform.analysis.base",
    "solar_platform.analysis.chart_templates",
    "solar_platform.analysis.clipping",
    "solar_platform.analysis.comparative",
    "solar_platform.analysis.curtailment",
    "solar_platform.analysis.degradation",
    "solar_platform.analysis.fouling",
    "solar_platform.analysis.helpers",
    "solar_platform.analysis.pr_trending",
    "solar_platform.analysis.shading",
    "solar_platform.analysis.thermal",
    "solar_platform.analysis.waterfall",
    # alerts
    "solar_platform.alerts",
    "solar_platform.alerts.models",
    "solar_platform.alerts.engine",
    "solar_platform.alerts.repository",
    "solar_platform.alerts.default_rules",
    "solar_platform.alerts.lifecycle",
    "solar_platform.alerts.notifications",
    "solar_platform.alerts.ticketing",
    # analytics
    "solar_platform.analytics",
    "solar_platform.analytics.anomaly_detection",
    "solar_platform.analytics.forecasting",
    # data_quality
    "solar_platform.data_quality",
    "solar_platform.data_quality.validators",
    "solar_platform.data_quality.quality_scorer",
    "solar_platform.data_quality.gap_detection",
    "solar_platform.data_quality.gap_filling",
    "solar_platform.data_quality.harmonization",
    "solar_platform.data_quality.sensor_health",
    "solar_platform.data_quality.source_priority",
    # db
    "solar_platform.db",
    "solar_platform.db.engine",
    "solar_platform.db.repository",
    "solar_platform.db.utils",
    "solar_platform.db.cache",
    "solar_platform.db.legacy",
    # financial
    "solar_platform.financial",
    "solar_platform.financial.revenue",
    "solar_platform.financial.tariff",
    "solar_platform.financial.budget",
    # ingestion
    "solar_platform.ingestion",
    "solar_platform.ingestion.base",
    "solar_platform.ingestion.coordinator",
    "solar_platform.ingestion.emig_adapter",
    "solar_platform.ingestion.enphase_adapter",
    "solar_platform.ingestion.fronius_adapter",
    "solar_platform.ingestion.generic_csv",
    "solar_platform.ingestion.huawei_adapter",
    "solar_platform.ingestion.juggle_adapter",
    "solar_platform.ingestion.sma_adapter",
    "solar_platform.ingestion.solaredge_adapter",
    "solar_platform.ingestion.solargis_adapter",
    # integrations
    "solar_platform.integrations",
    "solar_platform.integrations.notion_assets",
    "solar_platform.integrations.notion_irradiance",
    "solar_platform.integrations.pvsyst",
    "solar_platform.integrations.solargis",
    # reporting
    "solar_platform.reporting",
    "solar_platform.reporting.models",
    "solar_platform.reporting.pdf_renderer",
    "solar_platform.reporting.templates",
    "solar_platform.reporting.report_library",
    "solar_platform.reporting.scheduler",
    "solar_platform.reporting.chart_exporter",
    "solar_platform.reporting.data_fetcher",
    # services
    "solar_platform.services",
    "solar_platform.services.access_control",
    "solar_platform.services.api_keys",
    "solar_platform.services.auth",
    "solar_platform.services.background_jobs",
    "solar_platform.services.cache_layer",
    "solar_platform.services.data_pull",
    "solar_platform.services.data_quality_legacy",
    "solar_platform.services.error_handler",
    "solar_platform.services.export",
    "solar_platform.services.incremental_etl",
    "solar_platform.services.legacy_toolkit",
    "solar_platform.services.live_data",
    "solar_platform.services.logging",
    "solar_platform.services.materialized_views",
    "solar_platform.services.notifications",
    "solar_platform.services.observability",
    "solar_platform.services.plant",
    "solar_platform.services.portfolio",
    "solar_platform.services.reporting_bridge",
    "solar_platform.services.toolkit_bridge",
    "solar_platform.services.user_preferences",
]

# Streamlit-dependent UI modules (compile-only, no runtime import)
APP_PAGE_MODULES = [
    "app.pages.alerts_dashboard",
    "app.pages.anomaly_detection_ui",
    "app.pages.api_management_ui",
    "app.pages.chart_utils",
    "app.pages.clipping_analysis",
    "app.pages.comparative_analysis",
    "app.pages.curtailment_analysis",
    "app.pages.dashboard",
    "app.pages.data_explorer",
    "app.pages.data_export_ui",
    "app.pages.data_pull_ui",
    "app.pages.data_quality_dashboard",
    "app.pages.degradation_analysis",
    "app.pages.financial_dashboard",
    "app.pages.fouling",
    "app.pages.live_site_data",
    "app.pages.loss_waterfall",
    "app.pages.plant_detail",
    "app.pages.plant_management",
    "app.pages.poa_import",
    "app.pages.portfolio_map",
    "app.pages.pr_trending",
    "app.pages.report_builder",
    "app.pages.report_library_ui",
    "app.pages.shading",
    "app.pages.site_monitor",
    "app.pages.system_health",
    "app.pages.tariff_management",
    "app.pages.thermal_loss",
    "app.pages.ticket_kanban",
]

APP_COMPONENT_MODULES = [
    "app.components.auth_ui",
    "app.components.breadcrumbs",
    "app.components.contextual_help",
    "app.components.data_health",
    "app.components.global_search",
    "app.components.job_monitor",
    "app.components.keyboard_shortcuts",
    "app.components.kpi_cards",
    "app.components.layouts",
    "app.components.notifications_ui",
    "app.components.preferences_ui",
    "app.components.report_button",
    "app.components.sidebar",
    "app.components.ux",
]

CLI_MODULES = [
    "cli.backfill",
    "cli.bulk_historic_pull",
    "cli.data_pull",
    "cli.export_limit_pull",
    "cli.historic_data_pull",
    "cli.import_poa",
    "cli.import_solar_all",
    "cli.import_solar_excom",
    "cli.migrate_to_postgres",
    "cli.retry_failed_pulls",
]

API_MODULES = [
    "api",
    "api.main",
]

# __init__.py modules that should import cleanly
INIT_MODULES = [
    "solar_platform",
    "solar_platform.analysis",
    "solar_platform.alerts",
    "solar_platform.analytics",
    "solar_platform.data_quality",
    "solar_platform.db",
    "solar_platform.financial",
    "solar_platform.ingestion",
    "solar_platform.integrations",
    "solar_platform.reporting",
    "solar_platform.services",
]


def _dotted_to_filepath(dotted: str) -> Path:
    """Convert a dotted module name to its expected source file path."""
    parts = dotted.split(".")
    # Try as package (__init__.py) first, then as module (.py)
    pkg_path = ROOT / Path(*parts) / "__init__.py"
    mod_path = ROOT / Path(*parts[:-1]) / (parts[-1] + ".py") if len(parts) > 1 else ROOT / (parts[0] + ".py")
    # For solar_platform.* modules, look under src/
    if parts[0] == "solar_platform":
        pkg_path = SRC_DIR / Path(*parts) / "__init__.py"
        mod_path = SRC_DIR / Path(*parts[:-1]) / (parts[-1] + ".py") if len(parts) > 1 else SRC_DIR / (parts[0] + ".py")
    for candidate in (mod_path, pkg_path):
        if candidate.exists():
            return candidate
    return mod_path  # fallback for error message


# ═══════════════════════════════════════════════════════════════════════════
# TEST CLASS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.compile
class TestCompileAndImports:
    """Verify every Python source file compiles and all library modules import."""

    # -----------------------------------------------------------------------
    # 1. py_compile — walk ALL .py files across src/, app/, cli/, api/
    # -----------------------------------------------------------------------

    @staticmethod
    def _all_py_files() -> list[str]:
        files: list[str] = []
        for d in (SRC_DIR, APP_DIR, CLI_DIR, API_DIR):
            if d.exists():
                files.extend(_collect_py_files(d))
        return files

    @pytest.mark.parametrize(
        "filepath",
        _all_py_files.__func__(),  # type: ignore[attr-defined]
        ids=lambda p: _rel(p),
    )
    def test_py_compile_all_source_files(self, filepath: str):
        """Every .py file must compile without SyntaxError / IndentationError."""
        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
            py_compile.compile(filepath, cfile=tmp.name, doraise=True)

    # -----------------------------------------------------------------------
    # 2. AST parse — redundant safety net for syntax correctness
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "filepath",
        _all_py_files.__func__(),  # type: ignore[attr-defined]
        ids=lambda p: _rel(p),
    )
    def test_ast_parse_all_source_files(self, filepath: str):
        """Every .py file must be parseable by ast.parse."""
        source = Path(filepath).read_text(encoding="utf-8")
        ast.parse(source, filename=filepath)

    # -----------------------------------------------------------------------
    # 3. Import every solar_platform.* library module
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", SOLAR_PLATFORM_LIBRARY_MODULES)
    def test_import_library_module(self, module: str):
        """All solar_platform.* modules must import without errors."""
        importlib.import_module(module)

    # -----------------------------------------------------------------------
    # 4. Compile (AST) Streamlit page modules (no runtime import)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", APP_PAGE_MODULES)
    def test_compile_app_page(self, module: str):
        """Every Streamlit page must at least parse without syntax errors."""
        filepath = _dotted_to_filepath(module)
        assert filepath.exists(), f"Module file not found: {filepath}"
        source = filepath.read_text(encoding="utf-8")
        ast.parse(source, filename=str(filepath))

    # -----------------------------------------------------------------------
    # 5. Compile (AST) Streamlit component modules
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", APP_COMPONENT_MODULES)
    def test_compile_app_component(self, module: str):
        """Every Streamlit component must at least parse without syntax errors."""
        filepath = _dotted_to_filepath(module)
        assert filepath.exists(), f"Module file not found: {filepath}"
        source = filepath.read_text(encoding="utf-8")
        ast.parse(source, filename=str(filepath))

    # -----------------------------------------------------------------------
    # 6. Compile CLI modules
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", CLI_MODULES)
    def test_compile_cli_module(self, module: str):
        """Every CLI module must compile without syntax errors."""
        filepath = _dotted_to_filepath(module)
        assert filepath.exists(), f"Module file not found: {filepath}"
        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
            py_compile.compile(str(filepath), cfile=tmp.name, doraise=True)

    # -----------------------------------------------------------------------
    # 7. Compile API modules
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", API_MODULES)
    def test_compile_api_module(self, module: str):
        """Every API module must compile without syntax errors."""
        filepath = _dotted_to_filepath(module)
        assert filepath.exists(), f"Module file not found: {filepath}"
        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
            py_compile.compile(str(filepath), cfile=tmp.name, doraise=True)

    # -----------------------------------------------------------------------
    # 8. __init__.py imports
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("module", INIT_MODULES)
    def test_init_imports(self, module: str):
        """All __init__.py files must import without raising."""
        importlib.import_module(module)

    # -----------------------------------------------------------------------
    # 9. Circular import check — import all library modules together
    # -----------------------------------------------------------------------

    def test_no_circular_imports(self):
        """Importing every library module in sequence must not cause circular import errors."""
        errors: list[tuple[str, str]] = []
        for module in SOLAR_PLATFORM_LIBRARY_MODULES:
            try:
                importlib.import_module(module)
            except ImportError as exc:
                if "circular" in str(exc).lower() or "cannot import name" in str(exc).lower():
                    errors.append((module, str(exc)))
            except Exception as exc:
                errors.append((module, str(exc)))
        assert not errors, (
            f"Circular / import errors detected:\n"
            + "\n".join(f"  {mod}: {err}" for mod, err in errors)
        )

    # -----------------------------------------------------------------------
    # 10. Walk entire src/ and app/ — every .py file must compile
    # -----------------------------------------------------------------------

    def test_walk_src_and_app_all_compile(self):
        """Walk src/ and app/ directories and verify every .py file compiles via py_compile."""
        failures: list[tuple[str, str]] = []
        for directory in (SRC_DIR, APP_DIR):
            if not directory.exists():
                continue
            for py_file in _collect_py_files(directory):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                        py_compile.compile(py_file, cfile=tmp.name, doraise=True)
                except py_compile.PyCompileError as exc:
                    failures.append((_rel(py_file), str(exc)))
        assert not failures, (
            f"{len(failures)} file(s) failed to compile:\n"
            + "\n".join(f"  {f}: {e}" for f, e in failures)
        )

    # -----------------------------------------------------------------------
    # 11. Full repo walk — catch stray syntax errors anywhere
    # -----------------------------------------------------------------------

    def test_py_compile_entire_repo(self):
        """Walk the entire repo for .py files and verify compilation via py_compile."""
        skip_dirs = {"__pycache__", ".venv", "venv", ".git", "node_modules", ".eggs",
                     "solar_platform.egg-info", ".tox", ".mypy_cache", ".pytest_cache"}
        failures: list[tuple[str, str]] = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            # prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                        py_compile.compile(full, cfile=tmp.name, doraise=True)
                except py_compile.PyCompileError as exc:
                    failures.append((_rel(full), str(exc)))
        assert not failures, (
            f"{len(failures)} file(s) failed py_compile:\n"
            + "\n".join(f"  {f}: {e}" for f, e in failures)
        )
