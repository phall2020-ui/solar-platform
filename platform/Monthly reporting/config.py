"""
Application Configuration Module

This module contains configuration constants, session state initialization,
page setup, and column mapping persistence functions for the Solar Asset
Data Manager application.
"""

import json
from pathlib import Path
from typing import Dict

import streamlit as st

from brand_theme import inject_brand_css, register_plotly_theme


class Config:
    """
    Application configuration constants.

    This class contains all configuration constants used throughout the application,
    including database defaults, performance thresholds, caching parameters, and
    column detection patterns for auto-mapping uploaded data.
    """

    DEFAULT_DB = "solar_assets.db"
    DEFAULT_FISCAL_START = 4  # April
    TARGET_AVAILABILITY = 99.0  # 99% target
    CACHE_TTL = 3600  # 1 hour
    MAX_CACHE_SIZE = 32
    CHUNK_SIZE = 10000  # For large datasets
    PAGE_SIZE = 100  # Default pagination
    MAPPING_FILE = Path(__file__).resolve().parent / "colmap.json"

    # Performance thresholds
    PR_WARNING_THRESHOLD = 2.0  # pp
    PR_ALERT_THRESHOLD = 3.0  # pp
    AVAIL_WARNING_THRESHOLD = 1.0  # pp

    # Defaults
    DEFAULT_PR_BUDGET = 79.0
    DEFAULT_AVAILABILITY = 99.0
    DEFAULT_MONTH_NAME = "October 2025"

    # Column detection patterns
    COLUMN_PATTERNS = {
        "actual_gen": [
            r"actual.*gen",
            r"gen.*actual",
            r"^actual gen",
            r"generation",
            r"energy",
            r"meter",
            r"export",
        ],
        "wab": [
            r"irradiance.*gen",
            r"wab",
            r"weather.*adjusted",
            r"theoretical",
            r"expected.*yield",
            r"calculated.*exp",
            r"irradiance-based",
        ],
        "budget_gen": [
            r"budget.*gen",
            r"p50",
            r"target.*gen",
            r"financial.*budget",
            r"base.*case",
            r"forecast.*gen",
        ],
        "pr_actual": [
            r"actual.*pr",
            r"pr.*actual",
            r"^actual pr",
            r"\\bpr\\b(?!.*forecast)(?!.*budget)",
            r"performance ratio",
        ],
        "pr_budget": [
            r"forecast.*pr",
            r"budget.*pr",
            r"target.*pr",
            r"pr.*forecast",
        ],
        "availability": [r"availability", r"avail", r"uptime"],
        "site": [r"^site$", r"site.*name", r"location", r"plant"],
        "date": [r"date", r"month", r"period", r"time"],
        "capacity": [r"kwp", r"capacity", r"size", r"mw"],
    }


def init_session_state() -> None:
    """
    Initialize all session state variables with default values.

    Sets up required session state variables if they don't already exist,
    including database name, column mapping, and fiscal year settings.
    Also attempts to load any previously saved column mappings.
    """
    defaults = {
        "db_name": Config.DEFAULT_DB,
        "colmap": {},
        "colmap_confirmed": False,
        "fiscal_year_start": Config.DEFAULT_FISCAL_START,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Try loading a saved column mapping if none set yet
    if not st.session_state.get("colmap_confirmed"):
        saved = load_saved_colmap()
        if saved:
            st.session_state.colmap = saved
            st.session_state.colmap_confirmed = True
            st.session_state["colmap_source"] = "persisted"


def setup_page() -> None:
    """
    Configure Streamlit page settings and display application header.

    Sets up the page configuration including title, icon, and layout.
    Applies brand styling and displays the application header with
    getting started guide.
    """
    st.set_page_config(
        page_title="Solar Asset Data Manager",
        page_icon="☀️",
        layout="wide",
    )

    # Apply AMPYR brand styling across the app
    inject_brand_css()
    register_plotly_theme()

    st.title("☀️ Solar Asset Data Manager")
    st.markdown(
        """
**Comprehensive solar portfolio performance analysis tool** - Upload data, calculate losses,
and visualize performance waterfalls.
"""
    )

    with st.expander("📖 Getting Started Guide - Click to expand"):
        st.markdown(
            """
### 🚀 Quick Start (4 Steps):

1. **Configure Fiscal Year** (Sidebar)
   - Set fiscal year start month (default: April)
   - This affects YTD and Quarterly calculations
   - Example: April start means FY2025 = Apr 2024 to Mar 2025

2. **Generate Sample Data** (Sidebar)
   - Click "Create Test Data" button
   - Creates data matching your format: Sites with actual/forecast gen, PR, availability

3. **Set Up Column Mapping** (Upload Tab)
   - Load 'sample_solar_data' from database OR upload your CSV/Excel
   - System auto-detects columns:
     * **Actual Gen (kWh)**  Metered generation
     * **Irradiance-based generation**  Weather-adjusted expectation (WAB)
     * **Forecast Gen (kWh)**  Original P50/budget
     * **Actual PR (%)** & **Forecast PR (%)**  Performance ratios
     * **Availability (%)**  System uptime
     * **kWp**  Capacity for yield calculations
   - Confirm the mappings

4. **Run Analysis** (Calculations Tab)
   - Click "Run Calculations" to compute:
     * Weather Variance (Irradiance-based - Forecast)
     * Technical Losses (Irradiance-based - Actual)
     * PR Variance (Forecast PR - Actual PR)
     * Availability Variance (99% - Actual Availability)
     * Yield (kWh/kWp)
   - Aggregate by Site, Month, Quarter, YTD
   - Generate waterfall charts

---

### 📅 Fiscal Year (April 1st Start):

**Quarterly Breakdown:**
- **Q1:** April - June
- **Q2:** July - September
- **Q3:** October - December
- **Q4:** January - March

**Example:**
- October 2024 data → FY2025-Q3
- YTD in December 2024 → Apr 2024 to Dec 2024 (FY2025 YTD)
- March 2025 data → FY2025-Q4 (end of fiscal year)

**Note:** You can change the fiscal year start month in the sidebar if needed.

---

### 🧠 Understanding Your Metrics:

**Generation Metrics:**
- **Actual Gen**: Metered production (what you actually generated)
- **Forecast Gen**: Original P50/budget forecast
- **Irradiance-based generation**: What you *should* have generated given actual weather (WAB)

**Performance Metrics:**
- **Actual PR**: Realized performance ratio
- **Forecast PR**: Target/budgeted performance ratio
- **Availability**: % of time system was operational
- **Yield**: Normalized production (kWh/kWp)

**Calculated Variances:**
- **Weather Variance**: Irradiance-based - Forecast (positive = better weather than expected)
- **Technical Loss**: Irradiance-based - Actual (controllable losses)
- **PR Variance**: Forecast PR - Actual PR (positive = underperformance)
- **Availability Variance**: 99% - Actual Availability (positive = below target)

---

### 🛠️ Common Analysis Workflows:

**Fiscal YTD Portfolio Review:**
- Time: YTD (starts April 1st)
- Group by: (leave empty)
- Shows total performance since fiscal year start

**Quarterly Site Comparison:**
- Time: Quarterly (fiscal quarters)
- Group by: Site
- Identifies best/worst performers by fiscal quarter

**Monthly Trends:**
- Time: Monthly
- Group by: Site
- Track performance over time
- Visualize with line charts

**Waterfall Analysis:**
- Select fiscal time period (Q1, Q2, Q3, Q4, or YTD)
- Visual breakdown: Forecast → Weather Δ → Irradiance-based → PR Loss → Availability Loss → Actual
"""
        )


def save_colmap(colmap: Dict[str, str]) -> None:
    """
    Persist the confirmed column mapping to disk for future sessions.

    Args:
        colmap: Dictionary mapping canonical column names to actual column names
                in the uploaded data (e.g., {"actual_gen": "Actual Generation"}).
    """
    try:
        Config.MAPPING_FILE.write_text(json.dumps(colmap, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort persistence; ignore failures
        pass


def load_saved_colmap() -> Dict[str, str]:
    """
    Load a previously saved column mapping from disk.

    Returns:
        Dictionary with column mappings if found, empty dict otherwise.
    """
    try:
        if Config.MAPPING_FILE.exists():
            return json.loads(Config.MAPPING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def clear_saved_colmap() -> None:
    """
    Remove any persisted column mapping from disk.

    This function is called when the user resets the column mapping
    through the UI.
    """
    try:
        if Config.MAPPING_FILE.exists():
            Config.MAPPING_FILE.unlink()
    except Exception:
        pass
