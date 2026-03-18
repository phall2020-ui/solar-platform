"""
Page registry with grouping, role-based visibility, and metadata.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, this becomes a route configuration
- Role-based visibility maps to React Router guards
- Groups map to navigation sections
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
                module="app.pages.dashboard",
                func="render",
                icon="📊",
                roles=["viewer", "engineer", "manager", "admin"],
                description="Portfolio-level KPIs and plant status grid",
            ),
            "Site Monitor": PageConfig(
                module="app.pages.site_monitor",
                func="render",
                icon="📡",
                roles=["viewer", "engineer", "manager", "admin"],
                description="Real-time site monitoring",
            ),
            "Live Site Data": PageConfig(
                module="app.pages.live_site_data",
                func="render",
                icon="📊",
                roles=["viewer", "engineer", "manager", "admin"],
                description="Live generation data with historical day view",
            ),

        },
    ),
    "Analysis": PageGroup(
        icon="🔬",
        pages={
            "Clipping Analysis": PageConfig(
                module="app.pages.clipping_analysis",
                func="render",
                icon="✂️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Inverter clipping loss analysis",
            ),
            "Curtailment Analysis": PageConfig(
                module="app.pages.curtailment_analysis",
                func="render",
                icon="⚡",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Grid curtailment analysis",
            ),
            "Shading Analysis": PageConfig(
                module="app.pages.shading",
                func="render",
                icon="🌤️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Near shading loss analysis",
            ),
            "Fouling Analysis": PageConfig(
                module="app.pages.fouling",
                func="render",
                icon="🧹",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Soiling and fouling analysis",
            ),
            "Thermal Loss": PageConfig(
                module="app.pages.thermal_loss",
                func="render",
                icon="🌡️",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Thermal loss analysis",
            ),
            "Waterfall Analysis": PageConfig(
                module="app.pages.loss_waterfall",
                func="render",
                icon="💧",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Loss waterfall breakdown",
            ),
            "Comparative Analysis": PageConfig(
                module="app.pages.comparative_analysis",
                func="render",
                icon="📈",
                roles=["engineer", "manager", "admin"],
                description="Cross-plant performance comparison",
            ),
            "Anomaly Detection": PageConfig(
                module="app.pages.anomaly_detection_ui",
                func="render",
                icon="🔍",
                roles=["engineer", "manager", "admin"],
                description="Detect anomalous plant behavior",
            ),
            "PR Trending": PageConfig(
                module="app.pages.pr_trending",
                func="render",
                icon="📉",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Performance ratio trend analysis",
            ),
            "Degradation Analysis": PageConfig(
                module="app.pages.degradation_analysis",
                func="render",
                icon="🪫",
                roles=["engineer", "manager", "admin"],
                requires_plant=True,
                description="Long-term degradation estimation",
            ),
        },
    ),
    "Reporting": PageGroup(
        icon="📝",
        pages={

            "Report Builder": PageConfig(
                module="app.pages.report_builder",
                func="render",
                icon="📄",
                roles=["engineer", "manager", "admin"],
                description="Template-driven PDF report builder",
            ),
            "Report Library": PageConfig(
                module="app.pages.report_library_ui",
                func="render",
                icon="📚",
                roles=["engineer", "manager", "admin"],
                description="Browse and download generated reports",
            ),
        },
    ),
    "Financial": PageGroup(
        icon="💰",
        pages={
            "Financial Dashboard": PageConfig(
                module="app.pages.financial_dashboard",
                func="render",
                icon="💷",
                roles=["manager", "admin"],
                description="Revenue, budget, and tariff overview",
            ),
            "Tariff Management": PageConfig(
                module="app.pages.tariff_management",
                func="render",
                icon="📋",
                roles=["manager", "admin"],
                description="Manage plant tariff schedules",
            ),
            "Pipeline Dashboard": PageConfig(
                module="app.pages.pipeline_dashboard",
                func="render",
                icon="📈",
                roles=["manager", "admin"],
                description="Investment opportunity pipeline from Dynamics 365 CRM",
            ),
        },
    ),
    "Data Management": PageGroup(
        icon="🗄️",
        pages={
            "Data Explorer": PageConfig(
                module="app.pages.data_explorer",
                func="render",
                icon="🔍",
                roles=["engineer", "manager", "admin"],
                description="Browse database contents",
            ),
            "Plant Management": PageConfig(
                module="app.pages.plant_management",
                func="render",
                icon="🏗️",
                roles=["manager", "admin"],
                description="Register and configure plants",
            ),
            "POA Import": PageConfig(
                module="app.pages.poa_import",
                func="render",
                icon="📥",
                roles=["engineer", "manager", "admin"],
                description="Import irradiance data",
            ),
            "Data Export": PageConfig(
                module="app.pages.data_export_ui",
                func="render",
                icon="📤",
                roles=["engineer", "manager", "admin"],
                description="Export data in various formats",
            ),
            "Data Pull": PageConfig(
                module="app.pages.data_pull_ui",
                func="render",
                icon="⬇️",
                roles=["engineer", "manager", "admin"],
                description="Pull inverter data from Juggle/EMIG API",
            ),
        },
    ),
    "Admin": PageGroup(
        icon="⚙️",
        pages={
            "Data Quality": PageConfig(
                module="app.pages.data_quality_dashboard",
                func="render",
                icon="🏥",
                roles=["engineer", "manager", "admin"],
                description="Data quality scores and gap detection",
            ),
            "Alerts Dashboard": PageConfig(
                module="app.pages.alerts_dashboard",
                func="render",
                icon="🚨",
                roles=["engineer", "manager", "admin"],
                description="Evaluate alert rules and manage lifecycle",
            ),
            "Ticket Kanban": PageConfig(
                module="app.pages.ticket_kanban",
                func="render",
                icon="🧩",
                roles=["engineer", "manager", "admin"],
                description="Kanban view for operational tickets",
            ),
            "System Health": PageConfig(
                module="app.pages.system_health",
                func="render_system_health_page",
                icon="💚",
                roles=["admin"],
                description="System health and diagnostics",
            ),

            "API Management": PageConfig(
                module="app.pages.api_management_ui",
                func="render",
                icon="🔌",
                roles=["admin"],
                description="API key and endpoint management",
            ),
        },
    ),
}

# Special pages that don't appear in main sidebar navigation
SPECIAL_PAGES: dict[str, PageConfig] = {
    "Plant Detail": PageConfig(
        module="app.pages.plant_detail",
        func="render",
        icon="☀️",
        roles=["viewer", "engineer", "manager", "admin"],
        show_in_nav=False,
        requires_plant=True,
        description="Detailed view of a single plant",
    ),
    "Notifications": PageConfig(
        module="components.notifications_ui",
        func="render_notification_center",
        icon="🔔",
        roles=["viewer", "engineer", "manager", "admin"],
        show_in_nav=False,
    ),
    "User Management": PageConfig(
        module="components.auth_ui",
        func="render_user_management",
        icon="👤",
        roles=["admin"],
        show_in_nav=False,
    ),
    "Settings": PageConfig(
        module="components.preferences_ui",
        func="render_preferences_page",
        icon="⚙️",
        roles=["viewer", "engineer", "manager", "admin"],
        show_in_nav=False,
    ),
}


def get_visible_pages(user_role: str = "admin") -> dict[str, dict[str, PageConfig]]:
    """Get pages visible to a specific role, grouped.

    Args:
        user_role: The role of the current user.

    Returns:
        Dict of group_name -> {page_name: PageConfig} for visible pages.
    """
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
    """Flat list of all page names (including special pages)."""
    names: list[str] = []
    for group in PAGE_GROUPS.values():
        names.extend(group.pages.keys())
    names.extend(SPECIAL_PAGES.keys())
    return names


def find_page(name: str) -> PageConfig | None:
    """Find a page config by name (searches groups and special pages)."""
    for group in PAGE_GROUPS.values():
        if name in group.pages:
            return group.pages[name]
    if name in SPECIAL_PAGES:
        return SPECIAL_PAGES[name]
    return None


def get_group_for_page(name: str) -> str | None:
    """Find the group name a page belongs to."""
    for group_name, group in PAGE_GROUPS.items():
        if name in group.pages:
            return group_name
    return None
