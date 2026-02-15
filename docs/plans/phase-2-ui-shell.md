# Phase 2: Core Platform & UI Shell — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3–4 weeks  
**Goal:** Build the unified Streamlit UI shell — portfolio dashboard, plant detail views, navigation, global search, and design system. Everything renders via Streamlit multi-page, using services layer from Phase 0/1.

**Key Principle:** All data comes from `services/` (never raw SQL in modules). Streamlit components call service functions. UI code stays in `modules/` and `components/`. When we eventually extract to FastAPI + React, the services layer stays untouched.

**Prerequisite:** Phase 0 (database/config), Phase 1 (at least EMIG adapter + coordinator).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 2.1: Design System & Brand Tokens](#task-21-design-system--brand-tokens)
4. [Task 2.2: Navigation & Page Registry Refactor](#task-22-navigation--page-registry-refactor)
5. [Task 2.3: Portfolio Dashboard](#task-23-portfolio-dashboard)
6. [Task 2.4: Portfolio Map View](#task-24-portfolio-map-view)
7. [Task 2.5: Plant Detail View](#task-25-plant-detail-view)
8. [Task 2.6: KPI Cards Component](#task-26-kpi-cards-component)
9. [Task 2.7: Global Search Enhancement](#task-27-global-search-enhancement)
10. [Task 2.8: Dark/Light Theme Toggle](#task-28-darklight-theme-toggle)
11. [Task 2.9: Responsive Layout Patterns](#task-29-responsive-layout-patterns)
12. [Task 2.10: Breadcrumbs & Context Navigation](#task-210-breadcrumbs--context-navigation)
13. [Risks](#risks)
14. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 2.1 Design System & Brand Tokens | ✅ Done | 6 | P0 | Phase 0 |
| 2.2 Navigation & Page Registry Refactor | ✅ Done | 8 | P0 | 2.1 |
| 2.3 Portfolio Dashboard | ✅ Done | 12 | P0 | 2.1, 2.6 |
| 2.4 Portfolio Map View | ✅ Done | 6 | P1 | 2.3 |
| 2.5 Plant Detail View | ✅ Done | 10 | P0 | 2.2, 2.6 |
| 2.6 KPI Cards Component | ✅ Done | 4 | P0 | 2.1 |
| 2.7 Global Search Enhancement | ✅ Done | 4 | P1 | 2.2 |
| 2.8 Dark/Light Theme Toggle | ✅ Done | 4 | P2 | 2.1 |
| 2.9 Responsive Layout Patterns | ✅ Done | 4 | P2 | 2.1 |
| 2.10 Breadcrumbs & Context Nav | ✅ Done | 3 | P1 | 2.2 |
| **TOTAL** | **✅ All Done** | **61** | | |

---

## 2. Dependency Graph

```
┌────────────────────────┐
│ 2.1 Design System      │
│ (Brand Tokens, CSS)    │
└────────┬───────────────┘
         │
    ┌────┼─────────────────┬───────────────────┐
    │    │                 │                   │
    ▼    ▼                 ▼                   ▼
┌───────────┐    ┌──────────────┐    ┌──────────────┐
│ 2.2 Nav   │    │ 2.6 KPI      │    │ 2.8 Dark/    │
│ & Pages   │    │ Cards        │    │ Light Toggle │
└─────┬─────┘    └──────┬───────┘    └──────────────┘
      │                 │
 ┌────┼────┐       ┌────┘
 │    │    │       │
 ▼    ▼    ▼       ▼
┌──┐ ┌──┐ ┌────────────┐    ┌──────────────┐
│2.7│ │2.10│ │2.3 Dashboard│───▶│ 2.4 Map View │
└──┘ └──┘ └────────────┘    └──────────────┘
               │
               ▼
         ┌────────────┐
         │ 2.5 Plant  │
         │ Detail     │
         └────────────┘
```

---

## Task 2.1: Design System & Brand Tokens

**Goal:** Create a single source of truth for all brand colors, typography, spacing, and chart themes. Fix the existing inconsistency (#5FBFA0 vs #1B4D5C) and establish a proper design token system.

**Estimated Hours:** 6

### Current Problems (from Codebase Report)

1. `app_config/base.py` defines `BRAND_COLORS = {"primary": "#5FBFA0", ...}`
2. `components/ux.py` uses `BRAND_COLORS` inconsistently
3. `Solar Toolkit/` has its own `brand_theme.py` with `AMPYR_TEAL = "#1B4D5C"`
4. Chart color palettes are defined in multiple places
5. No CSS custom properties — everything is inline Python dicts

### Files to Create

#### `styles/design_tokens.py`
```python
"""
Design token system for the AMPYR Solar Portfolio Manager.

SINGLE SOURCE OF TRUTH for all visual styling.
Import this — never hardcode colors, font sizes, or spacing.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, these become CSS custom properties / design tokens
- Same values, different format (Python dict → CSS vars / Tailwind config)
"""

# ── Color Palette ────────────────────────────────────────────────────

# Primary brand colors
AMPYR_TEAL = "#1B4D5C"         # Primary teal (from official brand)
AMPYR_TEAL_LIGHT = "#5FBFA0"   # Light teal (secondary/accent)
AMPYR_GREEN = "#6B8E23"        # Olive green (charts)

# Semantic colors
STATUS_COLORS = {
    "excellent": "#2ECC71",     # Green — PR > 85%
    "good": "#5FBFA0",          # Teal — PR 70–85%
    "warning": "#F39C12",       # Amber — PR 50–70%
    "critical": "#E74C3C",      # Red — PR < 50%
    "offline": "#95A5A6",       # Gray — no data
    "unknown": "#BDC3C7",       # Light gray — cannot determine
}

# Chart palette (12 colors for multi-series)
CHART_COLORS = [
    "#1B4D5C",  # AMPYR teal
    "#5FBFA0",  # Light teal
    "#E74C3C",  # Red
    "#F39C12",  # Amber
    "#3498DB",  # Blue
    "#2ECC71",  # Green
    "#9B59B6",  # Purple
    "#E67E22",  # Orange
    "#1ABC9C",  # Turquoise
    "#34495E",  # Dark slate
    "#E91E63",  # Pink
    "#00BCD4",  # Cyan
]

# Background colors
BG_COLORS = {
    "page": "#FFFFFF",
    "card": "#F8F9FA",
    "sidebar": "#F0F2F6",
    "header": AMPYR_TEAL,
    "dark_page": "#0E1117",
    "dark_card": "#1E1E2E",
    "dark_sidebar": "#161625",
}

# ── Typography ──────────────────────────────────────────────────────

FONT_FAMILY = "'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

FONT_SIZES = {
    "xs": "0.75rem",    # 12px — labels, captions
    "sm": "0.875rem",   # 14px — secondary text
    "base": "1rem",     # 16px — body text
    "lg": "1.125rem",   # 18px — subheadings
    "xl": "1.25rem",    # 20px — section titles
    "2xl": "1.5rem",    # 24px — page titles
    "3xl": "2rem",      # 32px — dashboard numbers
    "4xl": "2.5rem",    # 40px — hero KPIs
}

# ── Spacing ─────────────────────────────────────────────────────────

SPACING = {
    "xs": "0.25rem",    # 4px
    "sm": "0.5rem",     # 8px
    "md": "1rem",       # 16px
    "lg": "1.5rem",     # 24px
    "xl": "2rem",       # 32px
    "2xl": "3rem",      # 48px
}

# ── Plotly Chart Theme ──────────────────────────────────────────────

PLOTLY_TEMPLATE = {
    "layout": {
        "font": {"family": FONT_FAMILY, "color": "#2C3E50"},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "colorway": CHART_COLORS,
        "title": {"font": {"size": 16, "color": AMPYR_TEAL}},
        "xaxis": {
            "gridcolor": "#E8E8E8",
            "linecolor": "#E8E8E8",
            "tickfont": {"size": 12},
        },
        "yaxis": {
            "gridcolor": "#E8E8E8",
            "linecolor": "#E8E8E8",
            "tickfont": {"size": 12},
        },
        "legend": {
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "#E8E8E8",
            "borderwidth": 1,
        },
        "margin": {"l": 60, "r": 20, "t": 40, "b": 40},
    },
}
```

#### `styles/theme.css`
```css
/* 
 * AMPYR Solar Portfolio Manager — Global Theme CSS
 * Injected into Streamlit via st.markdown()
 * 
 * DESIGN NOTES FOR EXTRACTION:
 * When moving to React, convert to Tailwind config or CSS-in-JS
 */

/* ── CSS Custom Properties ──────────────────────────────── */

:root {
    --ampyr-teal: #1B4D5C;
    --ampyr-teal-light: #5FBFA0;
    --ampyr-green: #6B8E23;
    
    --status-excellent: #2ECC71;
    --status-good: #5FBFA0;
    --status-warning: #F39C12;
    --status-critical: #E74C3C;
    --status-offline: #95A5A6;
    
    --bg-page: #FFFFFF;
    --bg-card: #F8F9FA;
    --text-primary: #2C3E50;
    --text-secondary: #7F8C8D;
    
    --font-family: 'Inter', 'Segoe UI', sans-serif;
    --border-radius: 0.5rem;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.1);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
}

/* ── Streamlit Overrides ────────────────────────────────── */

/* Main header */
.stApp header[data-testid="stHeader"] {
    background-color: var(--ampyr-teal) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #F0F2F6;
}

/* Metric containers */
[data-testid="stMetric"] {
    padding: 1rem;
    border-radius: var(--border-radius);
    background: var(--bg-card);
    box-shadow: var(--shadow-sm);
}

/* KPI value numbers */
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: var(--ampyr-teal) !important;
}

/* Metric delta arrows */
[data-testid="stMetricDelta"] {
    font-size: 0.875rem !important;
}

/* Tabs */
.stTabs [data-baseweb="tab"] {
    font-weight: 500;
    color: var(--text-secondary);
}

.stTabs [aria-selected="true"] {
    color: var(--ampyr-teal) !important;
    border-bottom-color: var(--ampyr-teal) !important;
}

/* Buttons */
.stButton > button[kind="primary"] {
    background-color: var(--ampyr-teal) !important;
    border-color: var(--ampyr-teal) !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: #164050 !important;
}

/* Cards (custom container) */
.kpi-card {
    background: white;
    border-radius: var(--border-radius);
    padding: 1.25rem;
    box-shadow: var(--shadow-sm);
    border-left: 4px solid var(--ampyr-teal);
    transition: box-shadow 0.2s ease;
}

.kpi-card:hover {
    box-shadow: var(--shadow-md);
}

/* Status badges */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}

.status-excellent { background: #D5F5E3; color: #196F3D; }
.status-good { background: #D1F2EB; color: #0E6655; }
.status-warning { background: #FDEBD0; color: #935116; }
.status-critical { background: #FADBD8; color: #922B21; }
.status-offline { background: #E5E8E8; color: #566573; }
```

### Acceptance Criteria

- [ ] Single `design_tokens.py` imported by all modules (no hardcoded colors anywhere)
- [ ] CSS custom properties in `theme.css` injected once in `app.py`
- [ ] Plotly template used by all chart modules
- [ ] Status colors consistent with IEC 61724 health conventions
- [ ] Migration guide: how to convert these tokens to React/Tailwind

---

## Task 2.2: Navigation & Page Registry Refactor

**Goal:** Refactor `app.py`'s `PAGE_REGISTRY` to support grouped navigation, icons, role-based visibility, and breadcrumbs while keeping the lazy-loading pattern.

**Estimated Hours:** 8

### Current State

`app.py` uses a flat dict `PAGE_REGISTRY` mapping page names to `(module_path, func_name)` tuples. The sidebar renders a flat list of all pages.

### Target State

```python
# New structure: pages grouped into categories with metadata
PAGE_GROUPS = {
    "Portfolio": {
        "icon": "🏠",
        "pages": {
            "Dashboard": PageConfig(
                module="modules.dashboard",
                func="render_dashboard",
                icon="📊",
                roles=["viewer", "engineer", "manager", "admin"],
                description="Portfolio-level KPIs and plant status grid",
            ),
            "Portfolio Map": PageConfig(
                module="modules.portfolio_map",
                func="render_portfolio_map",
                icon="🗺️",
                roles=["viewer", "engineer", "manager", "admin"],
            ),
        },
    },
    "Analysis": {
        "icon": "🔬",
        "pages": {
            "Clipping Analysis": PageConfig(...),
            "Curtailment Analysis": PageConfig(...),
            ...
        },
    },
    ...
}
```

### Files to Create/Modify

#### `services/page_registry.py` (new)
```python
"""
Page registry with grouping, role-based visibility, and metadata.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, this becomes a route configuration
- Role-based visibility maps to React Router guards
- Groups map to navigation sections
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PageConfig:
    """Configuration for a single page."""
    module: str             # Python module path (e.g., "modules.dashboard")
    func: str               # Function name in module
    icon: str = "📄"         # Emoji icon for sidebar
    roles: list[str] = field(default_factory=lambda: ["admin"])
    description: str = ""   # Tooltip/help text
    show_in_nav: bool = True
    requires_plant: bool = False  # True if page needs a plant selected


@dataclass
class PageGroup:
    """A group of pages in the sidebar navigation."""
    icon: str
    pages: dict[str, PageConfig]


# ── Page Registry ───────────────────────────────────────────────────

PAGE_GROUPS: dict[str, PageGroup] = {
    "Portfolio": PageGroup(
        icon="🏠",
        pages={
            "Dashboard": PageConfig(
                module="modules.dashboard",
                func="render_dashboard",
                icon="📊",
                roles=["viewer", "engineer", "manager", "admin"],
                description="Portfolio-level KPIs and plant status grid",
            ),
            "Portfolio Map": PageConfig(
                module="modules.portfolio_map",
                func="render_portfolio_map",
                icon="🗺️",
                roles=["viewer", "engineer", "manager", "admin"],
            ),
            "Data Overview": PageConfig(
                module="modules.data_overview",
                func="render_data_overview_page",
                icon="📋",
                roles=["viewer", "engineer", "manager", "admin"],
            ),
        },
    ),
    "Analysis": PageGroup(
        icon="🔬",
        pages={
            "Clipping Analysis": PageConfig(
                module="modules.clipping_analysis",
                func="render_clipping_analysis",
                icon="✂️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Curtailment Analysis": PageConfig(
                module="modules.curtailment_analysis",
                func="render_curtailment_analysis",
                icon="⚡",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Shading Analysis": PageConfig(
                module="modules.shading",
                func="render_shading",
                icon="🌤️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Fouling Analysis": PageConfig(
                module="modules.fouling",
                func="render_fouling",
                icon="🧹",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Thermal Loss": PageConfig(
                module="modules.thermal_loss",
                func="render_thermal_loss",
                icon="🌡️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Loss Waterfall": PageConfig(
                module="modules.loss_waterfall",
                func="render_loss_waterfall",
                icon="💧",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
            ),
            "Comparative Analysis": PageConfig(
                module="modules.comparative_analysis",
                func="render_comparative_analysis",
                icon="📈",
                roles=["engineer", "manager", "admin"],
            ),
        },
    ),
    "Reporting": PageGroup(
        icon="📝",
        pages={
            "Monthly Reporting": PageConfig(
                module="modules.monthly_reporting",
                func="render_monthly_reporting",
                icon="📅",
                roles=["engineer", "manager", "admin"],
            ),
            "Report Builder": PageConfig(
                module="modules.report_builder",
                func="render_report_builder",
                icon="📄",
                roles=["engineer", "manager", "admin"],
            ),
        },
    ),
    "Data Management": PageGroup(
        icon="🗄️",
        pages={
            "Data Explorer": PageConfig(
                module="modules.data_explorer",
                func="render_data_explorer",
                icon="🔍",
                roles=["engineer", "manager", "admin"],
            ),
            "Plant Management": PageConfig(
                module="modules.plant_management",
                func="render_plant_management",
                icon="🏗️",
                roles=["manager", "admin"],
            ),
            "POA Import": PageConfig(
                module="modules.poa_import",
                func="render_poa_import",
                icon="📥",
                roles=["engineer", "manager", "admin"],
            ),
            "Data Export": PageConfig(
                module="modules.data_export_ui",
                func="render_data_export",
                icon="📤",
                roles=["engineer", "manager", "admin"],
            ),
        },
    ),
    "Admin": PageGroup(
        icon="⚙️",
        pages={
            "System Health": PageConfig(
                module="modules.system_health",
                func="render_system_health",
                icon="💚",
                roles=["admin"],
            ),
            "Database Viewer": PageConfig(
                module="modules.database_viewer",
                func="render_database_viewer",
                icon="🗃️",
                roles=["admin"],
            ),
            "API Management": PageConfig(
                module="modules.api_management_ui",
                func="render_api_management",
                icon="🔌",
                roles=["admin"],
            ),
        },
    ),
}


def get_visible_pages(user_role: str) -> dict[str, dict[str, PageConfig]]:
    """Get pages visible to a specific role, grouped."""
    visible: dict[str, dict[str, PageConfig]] = {}
    for group_name, group in PAGE_GROUPS.items():
        group_pages = {
            name: config
            for name, config in group.pages.items()
            if user_role in config.roles
        }
        if group_pages:
            visible[group_name] = group_pages
    return visible


def get_all_page_names() -> list[str]:
    """Flat list of all page names."""
    names = []
    for group in PAGE_GROUPS.values():
        names.extend(group.pages.keys())
    return names


def find_page(name: str) -> PageConfig | None:
    """Find a page config by name."""
    for group in PAGE_GROUPS.values():
        if name in group.pages:
            return group.pages[name]
    return None
```

### Modify `app.py`

```python
# Replace flat PAGE_REGISTRY with grouped page loading
import importlib
from services.page_registry import get_visible_pages, find_page

def load_page(page_name: str):
    """Lazy-load and render a page."""
    config = find_page(page_name)
    if not config:
        st.error(f"Page not found: {page_name}")
        return
    
    module = importlib.import_module(config.module)
    func = getattr(module, config.func)
    func()
```

### Acceptance Criteria

- [ ] Pages grouped in sidebar with section headers
- [ ] Each page metadata includes icon, roles, description  
- [ ] Role-based visibility works (viewer sees fewer pages than admin)
- [ ] Lazy loading preserved (no performance regression)
- [ ] Existing direct links to pages still work

---

## Task 2.3: Portfolio Dashboard

**Goal:** Redesign the main dashboard with portfolio-level KPIs, plant status grid, alerts summary, and quick actions. This is the landing page after login.

**Estimated Hours:** 12

### Dashboard Layout (ASCII)

```
┌──────────────────────────────────────────────────────────────┐
│  🏠 Portfolio Dashboard                          [Last 24h ▼]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Total    │ │ Total    │ │ Fleet PR │ │ Active   │       │
│  │ Capacity │ │ Gen Today│ │          │ │ Alerts   │       │
│  │ 125 MWp  │ │ 412 MWh  │ │ 82.3%   │ │ 5 ⚠️     │       │
│  │ 20 plants│ │ +3.2% ▲  │ │ -1.1% ▼ │ │ 2 crit   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                              │
│  Plant Status Grid                              [🔍 filter] │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Name          │ Status  │ PR    │ Gen Today │ Alerts   │ │
│  ├───────────────┼─────────┼───────┼───────────┼──────────┤ │
│  │ ☀️ Ashford     │ 🟢 Good  │ 84.2% │ 22.1 MWh  │ 0        │ │
│  │ ☀️ Brightside  │ 🟡 Warn  │ 67.8% │ 18.5 MWh  │ 2        │ │
│  │ ☀️ Cranfield   │ 🔴 Crit  │ 42.1% │ 8.3 MWh   │ 3        │ │
│  │ ☀️ Dawlish     │ ⚫ Off   │ —     │ 0.0 MWh   │ 1        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────┐  ┌────────────────────────────┐ │
│  │ Portfolio Generation   │  │ Alert Summary              │ │
│  │ (7-day trend chart)    │  │ 🔴 2 Underperformance     │ │
│  │ ████████████████████   │  │ 🟡 3 Communication loss    │ │
│  │ ██████████████████     │  │ 📋 View all alerts →       │ │
│  └────────────────────────┘  └────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Files to Create/Modify

#### `modules/dashboard.py` (rewrite)

```python
"""
Portfolio Dashboard — landing page after login.

Shows fleet-level KPIs, plant status grid, generation trend, and alert summary.
All data from services layer — no direct DB queries.

DESIGN NOTES FOR EXTRACTION:
- KPI calculations live in services/portfolio_service.py
- This module only handles Streamlit rendering
- When moving to React: replace st.columns → CSS Grid, st.metric → <KPICard>
"""
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta

from styles.design_tokens import (
    AMPYR_TEAL,
    STATUS_COLORS,
    CHART_COLORS,
    PLOTLY_TEMPLATE,
)
from components.kpi_cards import render_kpi_row
from services.portfolio_service import PortfolioService


def render_dashboard():
    """Main dashboard entry point."""
    st.title("🏠 Portfolio Dashboard")
    
    # Time range selector
    col_title, col_range = st.columns([3, 1])
    with col_range:
        time_range = st.selectbox(
            "Period",
            ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Month to Date", "Year to Date"],
            label_visibility="collapsed",
        )
    
    # Load portfolio summary from service
    portfolio = PortfolioService()
    summary = portfolio.get_summary(time_range)
    
    # ── KPI Row ─────────────────────────────────────────────
    render_kpi_row([
        {
            "label": "Total Capacity",
            "value": f"{summary.total_capacity_mwp:.1f} MWp",
            "delta": f"{summary.plant_count} plants",
            "status": "good",
        },
        {
            "label": "Total Generation",
            "value": f"{summary.total_generation_mwh:.1f} MWh",
            "delta": f"{summary.generation_delta_pct:+.1f}%",
            "status": "good" if summary.generation_delta_pct > 0 else "warning",
        },
        {
            "label": "Fleet Performance Ratio",
            "value": f"{summary.fleet_pr_pct:.1f}%",
            "delta": f"{summary.pr_delta_pct:+.1f}%",
            "status": _pr_status(summary.fleet_pr_pct),
        },
        {
            "label": "Active Alerts",
            "value": str(summary.active_alerts),
            "delta": f"{summary.critical_alerts} critical",
            "status": "critical" if summary.critical_alerts > 0 else "good",
        },
    ])
    
    st.divider()
    
    # ── Plant Status Grid ───────────────────────────────────
    st.subheader("Plant Status")
    
    col_search, col_filter = st.columns([3, 1])
    with col_search:
        search = st.text_input("🔍 Filter plants", label_visibility="collapsed", placeholder="Filter plants...")
    with col_filter:
        status_filter = st.selectbox("Status", ["All", "Excellent", "Good", "Warning", "Critical", "Offline"], label_visibility="collapsed")
    
    plants = portfolio.get_plant_statuses(time_range)
    
    # Apply filters
    if search:
        plants = [p for p in plants if search.lower() in p["name"].lower()]
    if status_filter != "All":
        plants = [p for p in plants if p["status"] == status_filter.lower()]
    
    # Render plant grid
    for plant in plants:
        _render_plant_row(plant)
    
    st.divider()
    
    # ── Charts Row ──────────────────────────────────────────
    col_chart, col_alerts = st.columns([2, 1])
    
    with col_chart:
        st.subheader("Portfolio Generation Trend")
        trend = portfolio.get_generation_trend(days=7)
        fig = _build_trend_chart(trend)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_alerts:
        st.subheader("Alert Summary")
        alerts = portfolio.get_alert_summary()
        for alert in alerts:
            icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "warning" else "ℹ️"
            st.markdown(f"{icon} **{alert['count']}** {alert['type']}")
        
        if alerts:
            st.page_link("pages/alerts", label="📋 View all alerts →")


def _pr_status(pr: float) -> str:
    if pr >= 85: return "excellent"
    if pr >= 70: return "good"
    if pr >= 50: return "warning"
    return "critical"


def _render_plant_row(plant: dict):
    """Render a single plant status row."""
    status = plant["status"]
    status_icon = {"excellent": "🟢", "good": "🟢", "warning": "🟡", "critical": "🔴", "offline": "⚫"}.get(status, "⚪")
    
    cols = st.columns([3, 1, 1, 1, 1])
    with cols[0]:
        st.markdown(f"☀️ **{plant['name']}**")
    with cols[1]:
        st.markdown(f"{status_icon} {status.title()}")
    with cols[2]:
        pr_val = plant.get("pr", None)
        st.markdown(f"{pr_val:.1f}%" if pr_val else "—")
    with cols[3]:
        gen_val = plant.get("generation_mwh", 0)
        st.markdown(f"{gen_val:.1f} MWh")
    with cols[4]:
        alert_count = plant.get("alerts", 0)
        st.markdown(str(alert_count))


def _build_trend_chart(trend: list[dict]) -> go.Figure:
    """Build portfolio generation trend chart."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[t["date"] for t in trend],
        y=[t["generation_mwh"] for t in trend],
        fill="tozeroy",
        fillcolor=f"rgba(27,77,92,0.15)",
        line=dict(color=AMPYR_TEAL, width=2),
        name="Generation",
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        yaxis_title="MWh",
        showlegend=False,
        height=300,
    )
    return fig
```

#### `services/portfolio_service.py` (new)
```python
"""
Portfolio-level business logic.

Provides aggregated KPIs, plant statuses, and trend data.
Called by modules/dashboard.py — never import Streamlit here.

DESIGN NOTES FOR EXTRACTION:
- When adding FastAPI, expose this as GET /api/portfolio/summary
- Same service, different transport
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from services.database.repository import PlantRepository, ReadingsRepository

logger = structlog.get_logger("services.portfolio")


@dataclass
class PortfolioSummary:
    """Portfolio-level KPI summary."""
    total_capacity_mwp: float = 0.0
    plant_count: int = 0
    total_generation_mwh: float = 0.0
    generation_delta_pct: float = 0.0
    fleet_pr_pct: float = 0.0
    pr_delta_pct: float = 0.0
    active_alerts: int = 0
    critical_alerts: int = 0


class PortfolioService:
    """Portfolio-level operations."""
    
    def __init__(self):
        self._plants = PlantRepository()
        self._readings = ReadingsRepository()

    def get_summary(self, time_range: str = "Last 24 Hours") -> PortfolioSummary:
        """Get aggregated portfolio KPIs."""
        start, end = self._parse_time_range(time_range)
        
        # Get all plants
        plants_df = self._plants.list_all()
        if plants_df.empty:
            return PortfolioSummary()
        
        total_capacity = plants_df["capacity_kw"].sum() / 1000  # kW → MWp
        
        # Get generation data
        generation = self._readings.get_total_generation(start, end)
        prev_start = start - (end - start)
        prev_generation = self._readings.get_total_generation(prev_start, start)
        
        gen_delta = (
            ((generation - prev_generation) / prev_generation * 100)
            if prev_generation > 0 else 0.0
        )
        
        # Fleet PR calculation
        fleet_pr = self._calculate_fleet_pr(plants_df, start, end)
        
        return PortfolioSummary(
            total_capacity_mwp=total_capacity,
            plant_count=len(plants_df),
            total_generation_mwh=generation / 1000,  # kWh → MWh
            generation_delta_pct=gen_delta,
            fleet_pr_pct=fleet_pr,
        )
    
    def get_plant_statuses(self, time_range: str = "Last 24 Hours") -> list[dict[str, Any]]:
        """Get status for each plant."""
        start, end = self._parse_time_range(time_range)
        plants = self._plants.list_all()
        statuses = []
        
        for _, plant in plants.iterrows():
            pr = self._readings.get_plant_pr(plant["uid"], start, end)
            gen = self._readings.get_plant_generation(plant["uid"], start, end)
            
            status = "offline"
            if pr is not None:
                if pr >= 85: status = "excellent"
                elif pr >= 70: status = "good"
                elif pr >= 50: status = "warning"
                else: status = "critical"
            
            statuses.append({
                "uid": plant["uid"],
                "name": plant.get("name", plant.get("alias", "Unknown")),
                "status": status,
                "pr": pr,
                "generation_mwh": (gen or 0) / 1000,
                "alerts": 0,  # Placeholder until alert system exists
            })
        
        return sorted(statuses, key=lambda p: p.get("pr") or 0, reverse=True)

    def get_generation_trend(self, days: int = 7) -> list[dict[str, Any]]:
        """Get daily generation trend for the portfolio."""
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        return self._readings.get_daily_generation(start, end)

    def get_alert_summary(self) -> list[dict[str, Any]]:
        """Get alert summary. Placeholder until Phase 4."""
        return []

    def _parse_time_range(self, label: str) -> tuple[datetime, datetime]:
        now = datetime.utcnow()
        if label == "Last 24 Hours":
            return now - timedelta(hours=24), now
        elif label == "Last 7 Days":
            return now - timedelta(days=7), now
        elif label == "Last 30 Days":
            return now - timedelta(days=30), now
        elif label == "Month to Date":
            return now.replace(day=1, hour=0, minute=0, second=0), now
        elif label == "Year to Date":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0), now
        return now - timedelta(hours=24), now

    def _calculate_fleet_pr(self, plants_df, start, end) -> float:
        """Capacity-weighted fleet PR."""
        total_weighted_pr = 0.0
        total_capacity = 0.0
        for _, plant in plants_df.iterrows():
            pr = self._readings.get_plant_pr(plant["uid"], start, end)
            cap = plant.get("capacity_kw", 0)
            if pr is not None and cap > 0:
                total_weighted_pr += pr * cap
                total_capacity += cap
        return total_weighted_pr / total_capacity if total_capacity > 0 else 0.0
```

### Acceptance Criteria

- [ ] Dashboard shows 4 KPI cards in top row
- [ ] Plant status grid sortable and filterable
- [ ] 7-day generation trend chart renders
- [ ] All data from `PortfolioService` (no direct DB queries in dashboard)
- [ ] Color-coded status badges match design tokens
- [ ] Dashboard loads in < 3 seconds with 20 plants

---

## Task 2.4: Portfolio Map View

**Goal:** Add a geographic map view showing all plants with status-colored markers.

**Estimated Hours:** 6

### Implementation

Use `streamlit-folium` or `pydeck` (both support Streamlit natively).

#### `modules/portfolio_map.py` (new)
```python
"""
Portfolio map view — geographic display of all plants.

Uses streamlit-folium for interactive map with:
- Status-colored markers per plant
- Popup with plant KPIs
- Cluster view for zoomed-out portfolio overview
"""
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

from styles.design_tokens import STATUS_COLORS
from services.portfolio_service import PortfolioService


STATUS_MARKER_COLORS = {
    "excellent": "green",
    "good": "blue",
    "warning": "orange",
    "critical": "red",
    "offline": "gray",
}


def render_portfolio_map():
    """Render geographic map of all plants."""
    st.title("🗺️ Portfolio Map")
    
    portfolio = PortfolioService()
    plants = portfolio.get_plant_statuses("Last 24 Hours")
    
    if not plants:
        st.info("No plants found. Add plants in Plant Management.")
        return
    
    # Calculate map center from plant coordinates
    coords = [(p.get("lat", 51.5), p.get("lng", -0.1)) for p in plants if p.get("lat")]
    center_lat = sum(c[0] for c in coords) / len(coords) if coords else 51.5
    center_lng = sum(c[1] for c in coords) / len(coords) if coords else -0.1
    
    # Create map
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6, tiles="CartoDB positron")
    cluster = MarkerCluster()
    
    for plant in plants:
        lat = plant.get("lat")
        lng = plant.get("lng")
        if lat and lng:
            popup_html = f"""
            <b>{plant['name']}</b><br>
            Status: {plant['status'].title()}<br>
            PR: {plant.get('pr', 0):.1f}%<br>
            Generation: {plant.get('generation_mwh', 0):.1f} MWh
            """
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_html, max_width=200),
                icon=folium.Icon(
                    color=STATUS_MARKER_COLORS.get(plant["status"], "gray"),
                    icon="sun-o",
                    prefix="fa",
                ),
            ).add_to(cluster)
    
    cluster.add_to(m)
    st_folium(m, width=None, height=600)
```

### Dependencies to Add

```
# requirements.txt additions
streamlit-folium>=0.20
folium>=0.16
```

### Acceptance Criteria

- [ ] Map shows all plants with status-colored markers
- [ ] Clicking a marker shows plant KPIs in popup
- [ ] Marker clustering at zoomed-out levels
- [ ] Graceful handling of plants without coordinates

---

## Task 2.5: Plant Detail View

**Goal:** Create a comprehensive plant detail page with tabs: Overview, Production, Environmental, Devices, and History.

**Estimated Hours:** 10

### Layout (ASCII)

```
┌──────────────────────────────────────────────────────────────┐
│  ◄ Back to Dashboard    ☀️ Ashford Solar Farm                │
│                         Status: 🟢 Good | PR: 84.2%         │
├──────────────────────────────────────────────────────────────┤
│  [Overview] [Production] [Environmental] [Devices] [History] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  (Tab content renders here based on selection)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Files to Create

#### `modules/plant_detail.py`
```python
"""
Plant detail view with tabbed interface.

Each tab delegates to a function that only uses service layer.
"""
import streamlit as st
from datetime import datetime, timedelta

from services.plant_service import PlantService


def render_plant_detail():
    """Render plant detail view."""
    # Get selected plant from session state or query params
    plant_uid = st.session_state.get("selected_plant_uid")
    if not plant_uid:
        st.warning("No plant selected. Go to Dashboard to select a plant.")
        return
    
    service = PlantService()
    plant = service.get_plant(plant_uid)
    
    if not plant:
        st.error(f"Plant not found: {plant_uid}")
        return
    
    # Header
    st.title(f"☀️ {plant['name']}")
    
    pr = plant.get("current_pr")
    status = _get_status(pr)
    status_icon = {"excellent": "🟢", "good": "🟢", "warning": "🟡", "critical": "🔴", "offline": "⚫"}.get(status, "⚪")
    
    st.caption(f"Status: {status_icon} {status.title()} | PR: {pr:.1f}%" if pr else "Status: Offline")
    
    # Tabs
    tab_overview, tab_production, tab_environmental, tab_devices, tab_history = st.tabs(
        ["📊 Overview", "⚡ Production", "🌤️ Environmental", "🔌 Devices", "📜 History"]
    )
    
    with tab_overview:
        _render_overview(service, plant_uid)
    
    with tab_production:
        _render_production(service, plant_uid)
    
    with tab_environmental:
        _render_environmental(service, plant_uid)
    
    with tab_devices:
        _render_devices(service, plant_uid)
    
    with tab_history:
        _render_history(service, plant_uid)


def _render_overview(service, plant_uid):
    """Plant overview tab with KPIs and daily production chart."""
    summary = service.get_daily_summary(plant_uid)
    
    cols = st.columns(4)
    with cols[0]:
        st.metric("Today's Generation", f"{summary.get('today_mwh', 0):.1f} MWh")
    with cols[1]:
        st.metric("Current Power", f"{summary.get('current_kw', 0):.0f} kW")
    with cols[2]:
        st.metric("Performance Ratio", f"{summary.get('pr', 0):.1f}%")
    with cols[3]:
        st.metric("Availability", f"{summary.get('availability', 0):.1f}%")


def _render_production(service, plant_uid):
    st.info("Production charts — see Clipping/Curtailment analysis for detailed breakdowns")


def _render_environmental(service, plant_uid):
    st.info("Environmental data — irradiance, temperature, wind")


def _render_devices(service, plant_uid):
    st.info("Device list — inverters, meters, sensors")


def _render_history(service, plant_uid):
    st.info("Historical data explorer")


def _get_status(pr):
    if pr is None: return "offline"
    if pr >= 85: return "excellent"
    if pr >= 70: return "good"
    if pr >= 50: return "warning"
    return "critical"
```

#### `services/plant_service.py` (new)
```python
"""
Plant-level business logic.

Single plant operations: detail, daily summary, device list.
Framework-agnostic — no Streamlit imports.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.database.repository import PlantRepository, ReadingsRepository


class PlantService:
    def __init__(self):
        self._plants = PlantRepository()
        self._readings = ReadingsRepository()

    def get_plant(self, uid: str) -> dict[str, Any] | None:
        plant = self._plants.get_by_uid(uid)
        if plant:
            now = datetime.utcnow()
            pr = self._readings.get_plant_pr(uid, now - timedelta(hours=24), now)
            plant["current_pr"] = pr
        return plant

    def get_daily_summary(self, uid: str) -> dict[str, Any]:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0)
        return {
            "today_mwh": (self._readings.get_plant_generation(uid, today_start, now) or 0) / 1000,
            "current_kw": self._readings.get_latest_power(uid) or 0,
            "pr": self._readings.get_plant_pr(uid, today_start, now) or 0,
            "availability": 99.5,  # Placeholder
        }
```

### Acceptance Criteria

- [ ] Plant detail loads with header, status badge, and PR
- [ ] 5 tabs render without error
- [ ] All data from `PlantService` (no direct DB queries)
- [ ] Back navigation works
- [ ] Handles missing plant gracefully

---

## Task 2.6: KPI Cards Component

**Goal:** Create a reusable KPI card component used across all pages.

**Estimated Hours:** 4

### Files to Create

#### `components/kpi_cards.py`
```python
"""
Reusable KPI card component.

Usage:
    from components.kpi_cards import render_kpi_row
    
    render_kpi_row([
        {"label": "Total Capacity", "value": "125 MWp", "delta": "+5%", "status": "good"},
        {"label": "Fleet PR", "value": "82.3%", "delta": "-1.1%", "status": "warning"},
    ])
"""
import streamlit as st
from styles.design_tokens import STATUS_COLORS


def render_kpi_row(kpis: list[dict], columns: int | None = None):
    """Render a row of KPI cards.
    
    Args:
        kpis: List of dicts with keys: label, value, delta (optional), status (optional)
        columns: Number of columns (default: len(kpis))
    """
    n = columns or len(kpis)
    cols = st.columns(n)
    
    for i, kpi in enumerate(kpis):
        if i >= n:
            break
        with cols[i]:
            _render_card(kpi)


def _render_card(kpi: dict):
    """Render a single KPI card with colored left border."""
    status = kpi.get("status", "good")
    color = STATUS_COLORS.get(status, STATUS_COLORS["good"])
    
    st.markdown(
        f"""
        <div style="
            background: white;
            border-radius: 0.5rem;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-left: 4px solid {color};
        ">
            <div style="font-size: 0.8rem; color: #7F8C8D; text-transform: uppercase; font-weight: 500;">
                {kpi["label"]}
            </div>
            <div style="font-size: 1.75rem; font-weight: 700; color: #1B4D5C; margin: 0.25rem 0;">
                {kpi["value"]}
            </div>
            <div style="font-size: 0.85rem; color: {_delta_color(kpi.get('delta', ''))};">
                {kpi.get("delta", "")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _delta_color(delta: str) -> str:
    if not delta:
        return "#7F8C8D"
    if delta.startswith("+") or "▲" in delta:
        return "#2ECC71"
    if delta.startswith("-") or "▼" in delta:
        return "#E74C3C"
    return "#7F8C8D"
```

### Acceptance Criteria

- [ ] Renders N cards in a row with `st.columns`
- [ ] Left border color matches status
- [ ] Delta text colored green/red for positive/negative
- [ ] Responsive across screen sizes
- [ ] Used by Dashboard and Plant Detail

---

## Task 2.7: Global Search Enhancement

**Goal:** Enhance the existing Ctrl+K search to search plants, pages, and analysis modules.

**Estimated Hours:** 4

### Current State

`components/global_search.py` exists but is limited. Enhance to search across:
- Plant names → navigate to Plant Detail
- Page names → navigate to page
- Module features → link to relevant analysis
- Recent items → quick access

### Acceptance Criteria

- [ ] Ctrl+K opens search overlay
- [ ] Searches plants, pages, and features
- [ ] Results categorized (Plants / Pages / Features)
- [ ] Keyboard navigable (arrow keys + Enter)

---

## Task 2.8: Dark/Light Theme Toggle

**Goal:** Add a theme toggle in the sidebar that switches between light and dark modes.

**Estimated Hours:** 4

### Implementation

Streamlit supports `st.get_option("theme.*")` and custom CSS. Store theme preference in `st.session_state` and apply corresponding CSS.

```python
# In sidebar
theme = st.session_state.get("theme", "light")
if st.sidebar.toggle("🌙 Dark Mode", value=theme == "dark"):
    st.session_state.theme = "dark"
else:
    st.session_state.theme = "light"
```

### Acceptance Criteria

- [ ] Toggle in sidebar switches theme
- [ ] Theme persists across page navigation (session state)
- [ ] All KPI cards, charts, and tables respect theme
- [ ] Design tokens include dark mode variants

---

## Task 2.9: Responsive Layout Patterns

**Goal:** Document and implement responsive patterns for Streamlit's layout.

**Estimated Hours:** 4

### Patterns

1. **KPI Row** — 4 columns on wide, 2 on medium, 1 on narrow
2. **Chart + Sidebar** — 2:1 ratio, stack on narrow
3. **Table with Filters** — filter row above, table below
4. **Card Grid** — CSS Grid for plant cards, auto-fill columns

### Acceptance Criteria

- [ ] Layout patterns documented in `components/layouts.py`
- [ ] Dashboard usable on 1024px-wide screens
- [ ] No horizontal scroll on standard monitors

---

## Task 2.10: Breadcrumbs & Context Navigation

**Goal:** Add breadcrumb navigation showing the current page path (e.g., Portfolio > Ashford > Clipping Analysis).

**Estimated Hours:** 3

### Files to Create

#### `components/breadcrumbs.py`
```python
"""Breadcrumb navigation component."""
import streamlit as st


def render_breadcrumbs(crumbs: list[dict]):
    """Render breadcrumb navigation.
    
    Args:
        crumbs: List of {"label": "Dashboard", "page": "Dashboard"} dicts
    """
    parts = []
    for i, crumb in enumerate(crumbs):
        if i < len(crumbs) - 1:
            parts.append(f"[{crumb['label']}](#{crumb.get('page', '')})")
        else:
            parts.append(f"**{crumb['label']}**")
    
    st.markdown(" › ".join(parts))
```

### Acceptance Criteria

- [ ] Breadcrumbs show on every page except Dashboard
- [ ] Clicking breadcrumb navigates to that page
- [ ] Plant name shown when plant is selected

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Streamlit layout limitations for complex dashboards | Medium | High | Use `st.markdown(unsafe_allow_html=True)` for custom layouts; document limitations |
| Theme CSS conflicts with Streamlit updates | Low | Medium | Pin Streamlit version; test after upgrades |
| Performance with 20+ plants in status grid | Low | Low | Use pagination or virtual scrolling for > 50 plants |
| `streamlit-folium` rendering issues | Medium | Medium | Fallback to `pydeck` if folium problematic |
| Dark mode not fully supported by Streamlit widgets | Medium | High | Accept partial dark mode; focus on custom components |

---

## Definition of Done

- [ ] Design tokens system established — all colors, fonts, spacing from one file
- [ ] Page registry supports groups, roles, icons
- [ ] Portfolio Dashboard renders with 4 KPIs, plant grid, trend chart
- [ ] Portfolio Map shows plants with status-colored markers
- [ ] Plant Detail view has 5 tabs with overview KPIs
- [ ] KPI Cards reusable component works on Dashboard and Plant Detail
- [ ] Global search finds plants, pages, and features
- [ ] All data from services layer — zero direct DB queries in modules
- [ ] CSS theme applied consistently
- [ ] Dashboard loads in < 3 seconds (20 plants)
