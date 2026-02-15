"""Tests for configuration (unified_config.py and services/config.py).

These tests verify that the configuration singleton exposes all required
attributes, returns expected structures, and that branding data is complete.
"""
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# services.config module-level constants
# ---------------------------------------------------------------------------

class TestBaseConfig:
    """Tests for raw services.config values."""

    def test_app_name_is_set(self):
        from solar_platform.config import APP_NAME
        assert APP_NAME and isinstance(APP_NAME, str)

    def test_app_version_format(self):
        from solar_platform.config import APP_VERSION
        parts = APP_VERSION.split(".")
        assert len(parts) >= 2  # at least major.minor

    def test_base_path_is_path_object(self):
        from solar_platform.config import BASE_PATH
        assert isinstance(BASE_PATH, Path)

    def test_toolkit_db_is_path(self):
        from solar_platform.config import get_settings
        assert isinstance(get_settings().db_path, Path)

    def test_reporting_db_is_path(self):
        from solar_platform.config import get_settings
        assert isinstance(get_settings().db_path, Path)


# ---------------------------------------------------------------------------
# UnifiedConfig singleton
# ---------------------------------------------------------------------------

class TestUnifiedConfig:
    """Tests for the UnifiedConfig class and its singleton."""

    def test_config_singleton_exists(self):
        from app.config_compat import config
        assert config is not None

    def test_required_attributes_present(self):
        from app.config_compat import config
        required = [
            "APP_NAME", "APP_VERSION", "PAGE_TITLE", "PAGE_ICON",
            "BASE_PATH", "SOLAR_TOOLKIT_PATH", "MONTHLY_REPORTING_PATH",
            "TOOLKIT_DB", "REPORTING_DB",
            "BRAND_COLORS", "CHART_COLORS",
            "QUERY_CACHE_TTL", "MAX_QUERY_RESULTS",
        ]
        for attr in required:
            assert hasattr(config, attr), f"Missing attribute: {attr}"

    def test_paths_are_path_objects(self):
        from app.config_compat import config
        for attr in ("BASE_PATH", "SOLAR_TOOLKIT_PATH", "MONTHLY_REPORTING_PATH",
                      "TOOLKIT_DB", "REPORTING_DB"):
            val = getattr(config, attr)
            assert isinstance(val, Path), f"{attr} should be Path, got {type(val)}"


# ---------------------------------------------------------------------------
# get_page_config()
# ---------------------------------------------------------------------------

class TestGetPageConfig:
    """Tests for UnifiedConfig.get_page_config()."""

    def test_returns_dict(self):
        from app.config_compat import config
        pc = config.get_page_config()
        assert isinstance(pc, dict)

    def test_contains_expected_keys(self):
        from app.config_compat import config
        pc = config.get_page_config()
        for key in ("page_title", "page_icon", "layout", "initial_sidebar_state"):
            assert key in pc, f"Missing key: {key}"

    def test_layout_is_wide(self):
        from app.config_compat import config
        assert config.get_page_config()["layout"] == "wide"


# ---------------------------------------------------------------------------
# get_css()
# ---------------------------------------------------------------------------

class TestGetCss:
    """Tests for UnifiedConfig.get_css()."""

    def test_returns_string(self):
        from app.config_compat import config
        css = config.get_css()
        assert isinstance(css, str)

    def test_contains_style_tags(self):
        from app.config_compat import config
        css = config.get_css()
        assert "<style>" in css
        assert "</style>" in css

    def test_contains_root_block(self):
        from app.config_compat import config
        css = config.get_css()
        assert ":root" in css

    def test_contains_brand_css_vars(self):
        from app.config_compat import config
        css = config.get_css()
        assert "--ampyr-primary" in css
        assert "--ampyr-bg" in css


# ---------------------------------------------------------------------------
# BRAND_COLORS
# ---------------------------------------------------------------------------

class TestBrandColors:
    """Tests for BRAND_COLORS dict completeness."""

    def test_all_required_keys_present(self):
        from app.config_compat import config
        required_keys = {
            "primary", "secondary", "accent",
            "positive", "negative", "warning",
            "surface", "background", "border",
            "text", "text_secondary",
        }
        assert required_keys.issubset(set(config.BRAND_COLORS.keys()))

    def test_values_are_hex_strings(self):
        from app.config_compat import config
        for key, value in config.BRAND_COLORS.items():
            assert value.startswith("#"), f"BRAND_COLORS['{key}'] should be hex, got {value}"
            assert len(value) in (4, 7), f"BRAND_COLORS['{key}'] unexpected length: {value}"

    def test_chart_colors_is_list(self):
        from app.config_compat import config
        assert isinstance(config.CHART_COLORS, list)
        assert len(config.CHART_COLORS) > 0
