"""Unified configuration — thin wrapper around services.config.

All values now originate from ``services.config.Settings`` (Pydantic
BaseSettings).  This module keeps the ``config`` singleton and the
``UnifiedConfig`` class so that the 60+ existing call-sites continue
to work without modification.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict

from solar_platform.config import (
    APP_NAME,
    APP_VERSION,
    BASE_PATH,
    BRAND_COLORS,
    CHART_COLORS,
    MONTHLY_REPORTING_PATH,
    PAGE_ICON,
    PAGE_TITLE,
    SOLAR_TOOLKIT_PATH,
    Settings,
    get_settings as _get_settings,
)


@functools.lru_cache(maxsize=1)
def _compute_css() -> str:
    """Cached CSS computation — reads theme.css once."""
    color_vars = {
        'background': 'ampyr-bg',
        'surface': 'ampyr-surface',
        'border': 'ampyr-border',
        'primary': 'ampyr-primary',
        'secondary': 'ampyr-secondary',
        'accent': 'ampyr-accent',
        'text': 'ampyr-text',
        'text_secondary': 'ampyr-text-secondary',
        'positive': 'ampyr-positive',
        'negative': 'ampyr-negative',
        'warning': 'ampyr-warning',
    }
    props = "\n".join(
        f"    --{var}: {BRAND_COLORS[key]};"
        for key, var in color_vars.items()
        if key in BRAND_COLORS
    )
    root_css = f":root {{\n{props}\n}}"
    css_path = Path(__file__).parent / "styles" / "theme.css"
    file_css = css_path.read_text(encoding="utf-8")
    return f"<style>\n{root_css}\n\n{file_css}\n</style>"


class UnifiedConfig:
    """Compatibility wrapper providing attribute access to settings."""

    _settings: Settings | None = None

    @classmethod
    def _get(cls) -> Settings:
        if cls._settings is None:
            cls._settings = _get_settings()
        return cls._settings

    # ── Static / brand constants ─────────────────────────────────────
    APP_NAME = APP_NAME
    APP_VERSION = APP_VERSION
    PAGE_TITLE = PAGE_TITLE
    PAGE_ICON = PAGE_ICON
    BASE_PATH = BASE_PATH
    SOLAR_TOOLKIT_PATH = SOLAR_TOOLKIT_PATH
    MONTHLY_REPORTING_PATH = MONTHLY_REPORTING_PATH
    BRAND_COLORS = BRAND_COLORS
    CHART_COLORS = CHART_COLORS

    # ── Delegated properties (read live from Settings) ───────────────
    @property
    def ENVIRONMENT(self) -> str:  # noqa: N802
        return self._get().environment

    @property
    def settings(self) -> Settings:
        return self._get()

    @property
    def TOOLKIT_DB(self) -> Path:  # noqa: N802
        return self._get().db_path

    @property
    def REPORTING_DB(self) -> Path:  # noqa: N802
        return self._get().db_path

    # Alias used in reporting_bridge
    @property
    def UNIFIED_DB(self) -> Path:  # noqa: N802
        return self._get().db_path

    @property
    def EMIG_API_KEY(self) -> str:  # noqa: N802
        return self._get().effective_api_key

    @property
    def NREL_API_KEY(self) -> str:  # noqa: N802
        return self._get().nrel_api_key

    @property
    def use_cached_views(self) -> bool:
        return self._get().use_cached_views

    @property
    def enable_background_jobs(self) -> bool:
        return self._get().enable_background_jobs

    @property
    def enable_observability(self) -> bool:
        return self._get().enable_observability

    @property
    def QUERY_CACHE_TTL(self) -> int:  # noqa: N802
        return self._get().query_cache_ttl

    @property
    def MAX_QUERY_RESULTS(self) -> int:  # noqa: N802
        return self._get().max_query_results

    @property
    def LOG_LEVEL(self) -> str:  # noqa: N802
        return self._get().log_level

    @property
    def LOG_FORMAT(self) -> str:  # noqa: N802
        return self._get().log_format

    # Analysis defaults
    @property
    def DEFAULT_FISCAL_START(self) -> int:  # noqa: N802
        return self._get().default_fiscal_start

    @property
    def TARGET_AVAILABILITY(self) -> float:  # noqa: N802
        return self._get().target_availability

    @property
    def DEFAULT_PR_BUDGET(self) -> float:  # noqa: N802
        return self._get().default_pr_budget

    @property
    def DEFAULT_FOULING_CLEAN_DAYS(self) -> int:  # noqa: N802
        return self._get().default_fouling_clean_days

    @property
    def DEFAULT_SHADING_BASELINE_MONTHS(self) -> list:  # noqa: N802
        return self._get().default_shading_baseline_months

    @property
    def DEFAULT_SHADING_COMPARE_MONTHS(self) -> list:  # noqa: N802
        return self._get().default_shading_compare_months

    # ── Helper methods ───────────────────────────────────────────────
    @classmethod
    def get_css(cls) -> str:
        """Generate custom CSS for AMPYR branding (cached)."""
        return _compute_css()

    @classmethod
    def get_page_config(cls) -> Dict:
        """Get Streamlit page configuration."""
        return {
            "page_title": cls.PAGE_TITLE,
            "page_icon": cls.PAGE_ICON,
            "layout": "wide",
            "initial_sidebar_state": "expanded",
        }

    @classmethod
    def get_settings(cls) -> Settings:
        """Return validated settings via the legacy API."""
        return cls._get()


def get_settings() -> Settings:
    """Module-level bridge to services.config.get_settings()."""
    return _get_settings()


# Singleton instance
config = UnifiedConfig()
