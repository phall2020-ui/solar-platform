"""
Unified configuration for the Solar Portfolio Manager.
Now delegates to app_config module for environment-aware settings.

This module maintains backward compatibility while enabling environment-based config.
"""
from pathlib import Path
from typing import Dict

from services.config import Settings, get_settings as _get_settings

# Import all configuration from the new app_config module
from app_config import (
    ENVIRONMENT,
    APP_NAME, APP_VERSION, PAGE_TITLE, PAGE_ICON,
    BASE_PATH, SOLAR_TOOLKIT_PATH, MONTHLY_REPORTING_PATH,
    TOOLKIT_DB, REPORTING_DB,
    EMIG_API_KEY, NREL_API_KEY,
    use_cached_views, enable_background_jobs, enable_observability,
    QUERY_CACHE_TTL, MAX_QUERY_RESULTS,
    LOG_LEVEL, LOG_FORMAT,
    BRAND_COLORS, CHART_COLORS,
    DEFAULT_FISCAL_START, TARGET_AVAILABILITY, DEFAULT_PR_BUDGET,
    DEFAULT_FOULING_CLEAN_DAYS, DEFAULT_SHADING_BASELINE_MONTHS,
    DEFAULT_SHADING_COMPARE_MONTHS,
)

_settings: Settings | None
try:
    _settings = _get_settings()
except Exception:
    _settings = None


class UnifiedConfig:
    """Configuration for the unified Solar Portfolio Manager.
    
    This class provides a unified interface to all configuration values,
    now sourced from the environment-aware config module.
    """
    
    # Application
    APP_NAME = APP_NAME
    APP_VERSION = APP_VERSION
    PAGE_TITLE = PAGE_TITLE
    PAGE_ICON = PAGE_ICON
    
    # Environment
    ENVIRONMENT = _settings.environment if _settings else ENVIRONMENT

    # New validated settings bridge
    settings = _settings
    
    # Paths
    BASE_PATH = BASE_PATH
    SOLAR_TOOLKIT_PATH = SOLAR_TOOLKIT_PATH
    MONTHLY_REPORTING_PATH = MONTHLY_REPORTING_PATH
    
    # Databases
    TOOLKIT_DB = TOOLKIT_DB
    REPORTING_DB = REPORTING_DB
    
    # API Keys
    EMIG_API_KEY = EMIG_API_KEY
    NREL_API_KEY = NREL_API_KEY
    
    # Feature Flags
    use_cached_views = use_cached_views
    enable_background_jobs = enable_background_jobs
    enable_observability = enable_observability
    
    # Performance
    QUERY_CACHE_TTL = QUERY_CACHE_TTL
    MAX_QUERY_RESULTS = MAX_QUERY_RESULTS
    
    # Logging
    LOG_LEVEL = LOG_LEVEL
    LOG_FORMAT = LOG_FORMAT
    
    # Branding
    BRAND_COLORS = BRAND_COLORS
    CHART_COLORS = CHART_COLORS
    
    # Analysis Defaults
    DEFAULT_FISCAL_START = DEFAULT_FISCAL_START
    TARGET_AVAILABILITY = TARGET_AVAILABILITY
    DEFAULT_PR_BUDGET = DEFAULT_PR_BUDGET
    DEFAULT_FOULING_CLEAN_DAYS = DEFAULT_FOULING_CLEAN_DAYS
    DEFAULT_SHADING_BASELINE_MONTHS = DEFAULT_SHADING_BASELINE_MONTHS
    DEFAULT_SHADING_COMPARE_MONTHS = DEFAULT_SHADING_COMPARE_MONTHS

    @classmethod
    def get_css(cls) -> str:
        """Generate custom CSS for AMPYR branding.
        
        Dynamically generates :root CSS variables from BRAND_COLORS,
        then loads the rest of the stylesheet from styles/theme.css.
        """
        # Map of BRAND_COLORS keys to CSS custom property names
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
        
        # Build :root block from config values
        props = "\n".join(
            f"    --{var}: {cls.BRAND_COLORS[key]};"
            for key, var in color_vars.items()
            if key in cls.BRAND_COLORS
        )
        root_css = f":root {{\n{props}\n}}"
        
        # Load external stylesheet
        css_path = Path(__file__).parent / "styles" / "theme.css"
        file_css = css_path.read_text(encoding="utf-8")
        
        return f"<style>\n{root_css}\n\n{file_css}\n</style>"
    
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
        """Return validated settings while preserving legacy UnifiedConfig API."""
        if cls.settings is None:
            cls.settings = _get_settings()
        return cls.settings


def get_settings() -> Settings:
    """Module-level bridge for new configuration access."""
    return _get_settings()


# Singleton instance
config = UnifiedConfig()
