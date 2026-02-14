import sys, os
repo_root = os.path.dirname(__file__)
if repo_root not in sys.path: sys.path.insert(0, repo_root)

# """
# Streamlit Web User Interface for Solar Toolkit.
# Refactored from ui.py to use the central AnalysisOrchestrator.
# 
# To Run: streamlit run solar_toolkit/ui/app.py
# """
import streamlit as st
import pandas as pd
import os
import sys
import logging
import io
import tempfile
from datetime import datetime, timedelta
import altair as alt

# Import pipeline modules
try:
    # Assuming this script is run from the package root or the path is set
    from solar_toolkit.orchestrator import AnalysisOrchestrator
    from solar_toolkit.poa_bulk_importer import PREVIEW_LIMIT
    from solar_toolkit.config import settings
    from solar_toolkit.utils import setup_logging
    from solar_toolkit.data_viewer import DataViewer
    
    # Initialize the global logger instance
    logger = logging.getLogger("solar_toolkit")

except ImportError as e:
    st.error(f"Failed to import core modules. Please ensure all dependencies are installed and the package structure is correct. Error: {e}")
    st.stop()

# --- Setup ---
# Configure logging to capture output to a StringIO buffer
log_capture_string = io.StringIO()
# Use the package's logger but add the StreamHandler for capture
setup_logging(verbose=True, log_to_file=None)
capture_handler = logging.StreamHandler(log_capture_string)
capture_handler.setLevel(logging.INFO)
# Attach only to the main package logger or root logger
logging.getLogger("solar_toolkit").addHandler(capture_handler)
logging.getLogger().addHandler(capture_handler)


st.set_page_config(page_title="Solar Analytics Workbench", layout="wide", page_icon="⚡")

# --- Custom CSS ---
def load_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        /* Global Font & Colors */
        html, body, [class*="css"] {
            font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #334155; /* Slate 700 */
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #0f172a !important; /* Slate 900 */
            font-weight: 600;
            letter-spacing: -0.025em;
        }
        h1 { font-size: 2rem !important; }
        h2 { font-size: 1.5rem !important; margin-top: 1.5rem !important; }
        h3 { font-size: 1.25rem !important; }
        
        /* Metric Cards (KPIs) */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            padding: 16px 20px;
            border-radius: 8px;
            border: 1px solid #e2e8f0; /* Slate 200 */
            box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.05);
            transition: all 0.2s ease;
        }
        div[data-testid="stMetric"]:hover {
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            border-color: #cbd5e1;
        }
        div[data-testid="stMetric"] label {
            color: #64748b; /* Slate 500 */
            font-size: 0.875rem;
            font-weight: 500;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #0f172a;
            font-weight: 700;
        }
        
        /* Tabs Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0;
        }
        .stTabs [data-baseweb="tab"] {
            height: 48px;
            white-space: pre-wrap;
            background-color: transparent;
            border: none;
            color: #64748b;
            font-weight: 500;
            padding: 0 4px;
        }
        .stTabs [aria-selected="true"] {
            background-color: transparent;
            color: #0ea5e9; /* Brand Blue */
            border-bottom: 2px solid #0ea5e9;
        }
        
        /* Button Styling */
        .stButton > button {
            border-radius: 6px;
            font-weight: 500;
            border: 1px solid #e2e8f0;
            background-color: #ffffff;
            color: #334155;
            transition: all 0.15s ease;
        }
        .stButton > button:hover {
            border-color: #cbd5e1;
            background-color: #f8fafc;
            color: #0f172a;
        }
        /* Primary Button Override */
        .stButton > button[kind="primary"] {
            background-color: #0ea5e9;
            color: white;
            border: none;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #0284c7;
        }
        
        /* Expander Styling */
        .streamlit-expanderHeader {
            background-color: #ffffff;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            color: #334155;
        }
        
        /* Dataframe Styling */
        div[data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            overflow: hidden;
        }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
        }
        section[data-testid="stSidebar"] h1 {
            color: #334155 !important;
            font-size: 1.1rem !important;
        }
        
        /* Custom Container Border */
        div[data-testid="stVerticalBlock"] > div[style*="border"] {
            border-color: #e2e8f0 !important;
            box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
            background-color: #ffffff;
        }
        </style>
    """, unsafe_allow_html=True)

load_css()

st.title("⚡ Solar Analytics Workbench")

# Initialize Orchestrator and state
@st.cache_resource
def get_orchestrator():
    """Initializes the Orchestrator (cached resource)."""
    # Version: 1.1 - Forced reload for new methods
    return AnalysisOrchestrator(db_path=settings.DB_PATH)

orch = get_orchestrator()

def clear_logs():
    """Clears the captured log output."""
    log_capture_string.truncate(0)
    log_capture_string.seek(0)
    
def display_logs():
    """Displays the captured log output in an expander."""
    st.markdown("### ðŸ“œ Logs")
    with st.expander("Show Detailed Logs"):
        st.code(log_capture_string.getvalue())

# --- Sidebar Navigation ---
# Load plants for use in pages (globally available)
plant_list = orch.get_plants()
plant_aliases = [p['alias'] for p in plant_list]

# Legacy variable compatibility
selected_alias = None
selected_plant = {}

st.sidebar.markdown("### Navigation")
selection = st.sidebar.radio("Go to", [
    "Plants & Data Fetch", 
    "POA Import", 
    "Fouling Analysis", 
    "Shading Analysis", 
    "Clipping Analysis",
    "Data Overview",
    "Database Viewer"
])

# --- Main Application Pages ---



# --- PAGE 1: Plants & Data Fetch (Combined) ---
