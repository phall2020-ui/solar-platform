"""
Solar Portfolio Manager - Unified Application
Main entry point combining Solar Toolkit and Monthly Reporting.
"""
import importlib
import logging

import streamlit as st

from components import get_navigation_state, render_sidebar
from app.components.breadcrumbs import render_breadcrumbs
from app.components.contextual_help import render_contextual_help_sidebar
from app.components.global_search import init_search_in_session, render_search_dialog
from app.components.keyboard_shortcuts import (
    handle_keyboard_shortcuts,
    init_shortcuts_in_session,
    inject_keyboard_handler,
)
from solar_platform.services.error_handler import get_error_handler
from solar_platform.services.logging import get_logger, setup_logging
from app.page_registry import find_page, get_all_page_names

# Phase 1 Features
from solar_platform.services.user_preferences import init_preferences_in_session
from styles import apply_theme
from app.config_compat import config

try:
    setup_logging()
    get_logger("app.startup").info("structured_logging_initialized")
except Exception:
    logging.getLogger(__name__).exception("Failed to initialize structured logging")

# Configure the page
st.set_page_config(**config.get_page_config())

# Apply AMPYR branding
apply_theme()

# Initialize Phase 1 services
init_preferences_in_session(str(config.REPORTING_DB))
error_handler = get_error_handler()
init_search_in_session(str(config.TOOLKIT_DB), str(config.REPORTING_DB))
init_shortcuts_in_session()

# Inject keyboard shortcuts
inject_keyboard_handler()

# Handle keyboard shortcuts
handle_keyboard_shortcuts()

# Render sidebar and get navigation state
render_sidebar()
nav_state = get_navigation_state()

# Show contextual help in sidebar
render_contextual_help_sidebar()

# Global search dialog (triggered by Ctrl+K)
if st.session_state.get("show_search", False):
    with st.container():
        render_search_dialog()
        if st.button("Close Search"):
            st.session_state["show_search"] = False
            st.rerun()

# ---------------------------------------------------------------------------
# Page Router
# Uses the new page registry from services/page_registry.py
# Pages are lazily imported only when navigated to.
# ---------------------------------------------------------------------------

# Route to appropriate page
page = nav_state["page"]

# Store current page for contextual help
st.session_state["current_page"] = page

# Breadcrumb navigation
render_breadcrumbs()

# Look up the page in the registry and render it
page_config = find_page(page)

if page_config:
    try:
        module = importlib.import_module(page_config.module)
        func = getattr(module, page_config.func)
        func()
    except ImportError as e:
        st.error(f"Could not load module for '{page}': {e}")
    except AttributeError as e:
        st.error(f"Function not found for '{page}': {e}")
    except Exception as e:
        st.error(f"Error rendering '{page}': {e}")
        logging.getLogger(__name__).exception("Page render error for %s", page)
else:
    st.error(f"Unknown page: {page}")
    st.info(f"Available pages: {', '.join(get_all_page_names())}")
