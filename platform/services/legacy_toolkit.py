"""
Legacy Solar Toolkit Services
Wraps the initialization and shared utilities from the original Solar Toolkit app.
"""
import io
import logging
import sys

import streamlit as st

from unified_config import config

# Ensure toolkit path is available for imports
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
if toolkit_path not in sys.path:
    sys.path.insert(0, toolkit_path)

# Import legacy core modules
try:
    from solar_toolkit.config import settings
    from solar_toolkit.orchestrator import AnalysisOrchestrator
    from solar_toolkit.utils import setup_logging
    
    LEGACY_AVAILABLE = True
except ImportError as e:
    LEGACY_AVAILABLE = False
    print(f"Legacy Toolkit Import Error: {e}")

# Global state for logs
log_capture_string = io.StringIO()

def initialize_logging():
    """Setup logging to capture output."""
    if not LEGACY_AVAILABLE: return
    
    setup_logging(verbose=True, log_to_file=None)
    capture_handler = logging.StreamHandler(log_capture_string)
    capture_handler.setLevel(logging.INFO)
    logging.getLogger("solar_toolkit").addHandler(capture_handler)
    logging.getLogger().addHandler(capture_handler)

@st.cache_resource
def get_orchestrator():
    """Initializes the Orchestrator (cached resource)."""
    if not LEGACY_AVAILABLE: return None
    return AnalysisOrchestrator(db_path=settings.DB_PATH)

def clear_logs():
    """Clears the captured log output."""
    log_capture_string.truncate(0)
    log_capture_string.seek(0)
    
def display_logs():
    """Displays the captured log output in an expander."""
    st.markdown("### 📜 Logs")
    with st.expander("Show Detailed Logs"):
        st.code(log_capture_string.getvalue())

def load_css():
    """Injects the legacy CSS."""
    st.markdown("""
        <style>
        /* [Legacy CSS simplified for unified app integration] */
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stButton > button[kind="primary"] { border: none; }
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.05);
        }
        </style>
    """, unsafe_allow_html=True)
