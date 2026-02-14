"""
Dashboard page - Portfolio overview.
Migrated from modules/dashboard.py
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.kpi_card import kpi_card, kpi_row
from solar_portfolio_manager.components.alert import alert_box, success_alert, error_alert, info_alert
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.styles import heading_style, COLORS


def data_source_status() -> rx.Component:
    """Render data source connectivity status."""
    return rx.hstack(
        rx.cond(
            AppState.toolkit_available,
            success_alert("**Solar Toolkit:** Connected"),
            error_alert("**Solar Toolkit:** Not Available"),
        ),
        rx.cond(
            AppState.reporting_available,
            success_alert("**Monthly Reporting:** Connected"),
            error_alert("**Monthly Reporting:** Not Available"),
        ),
        spacing="4",
        width="100%",
        flex_wrap="wrap",
    )


def portfolio_metrics() -> rx.Component:
    """Render portfolio KPI metrics."""
    return rx.hstack(
        kpi_card(
            title="Registered Plants",
            value=AppState.total_plants_count.to_string(),
            icon="🏭",
        ),
        kpi_card(
            title="Total DC Capacity",
            value=AppState.total_capacity_display,
            icon="⚡",
        ),
        kpi_card(
            title="With Location Data",
            value=rx.cond(
                AppState.total_plants_count > 0,
                f"{AppState.plants_with_location}/{AppState.total_plants_count}",
                "0/0",
            ),
            icon="📍",
        ),
        spacing="4",
        width="100%",
        flex_wrap="wrap",
    )


def plant_list() -> rx.Component:
    """Expandable list of registered plants."""
    return rx.accordion.root(
        rx.accordion.item(
            header=rx.text("📋 View All Registered Plants"),
            content=rx.cond(
                AppState.total_plants_count > 0,
                rx.foreach(
                    AppState.toolkit_plants,
                    lambda plant: rx.hstack(
                        rx.text(
                            plant["alias"],
                            font_weight="bold",
                            min_width="200px",
                        ),
                        rx.text(
                            plant["plant_uid"],
                            font_family="monospace",
                            color=COLORS["text_secondary"],
                            font_size="0.85rem",
                        ),
                        width="100%",
                        padding_y="0.5rem",
                        border_bottom=f"1px solid {COLORS['border']}",
                    ),
                ),
                rx.text("No plants registered.", color=COLORS["text_secondary"]),
            ),
        ),
        width="100%",
        variant="ghost",
    )


def quick_actions() -> rx.Component:
    """Quick action links section."""
    return rx.hstack(
        rx.vstack(
            rx.heading("🔧 Operations", size="4", color=COLORS["primary"]),
            rx.markdown("""
- **Plant Management**: Register and configure plants
- **POA Import**: Import irradiance data
- **Data Explorer**: Browse database contents
            """),
            align_items="flex_start",
            flex="1",
        ),
        rx.vstack(
            rx.heading("📈 Analysis", size="4", color=COLORS["primary"]),
            rx.markdown("""
- **Fouling Analysis**: Detect panel soiling
- **Shading Analysis**: Identify shading losses
- **Clipping Analysis**: Estimate inverter losses
            """),
            align_items="flex_start",
            flex="1",
        ),
        rx.vstack(
            rx.heading("💼 Reporting", size="4", color=COLORS["primary"]),
            rx.markdown("""
- **Monthly Performance**: ExCom reports
- **Waterfall Analysis**: Loss breakdowns
            """),
            align_items="flex_start",
            flex="1",
        ),
        spacing="6",
        width="100%",
        flex_wrap="wrap",
    )


def page() -> rx.Component:
    """Render the portfolio dashboard page."""
    return rx.vstack(
        # Header
        rx.heading(
            "📊 Portfolio Dashboard",
            size="7",
            style=heading_style,
        ),
        rx.text(
            "Executive overview of your solar portfolio health and performance.",
            color=COLORS["text_secondary"],
            font_size="1rem",
        ),
        
        # Loading indicator
        rx.cond(
            AppState.is_loading,
            rx.hstack(
                rx.spinner(size="3"),
                rx.text("Loading data...", color=COLORS["text_secondary"]),
                spacing="2",
            ),
            rx.fragment(),
        ),
        
        # Error message
        rx.cond(
            AppState.error_message != "",
            alert_box(AppState.error_message, "warning"),
            rx.fragment(),
        ),
        
        # Data source status
        data_source_status(),
        
        divider(),
        
        # Operational Portfolio section
        rx.cond(
            AppState.toolkit_available,
            rx.vstack(
                section_header(
                    "Operational Portfolio",
                    description="Plants registered in Solar Toolkit for operational analysis",
                    icon="🔧",
                ),
                rx.cond(
                    AppState.total_plants_count > 0,
                    rx.vstack(
                        portfolio_metrics(),
                        plant_list(),
                        spacing="4",
                        width="100%",
                    ),
                    info_alert("No plants registered in Solar Toolkit yet. Go to **Plant Management** to register plants."),
                ),
                spacing="4",
                width="100%",
                align_items="stretch",
            ),
            rx.fragment(),
        ),
        
        divider(),
        
        # Financial Portfolio section
        rx.cond(
            AppState.reporting_available,
            rx.vstack(
                section_header(
                    "Financial Portfolio",
                    description="Performance data from Monthly Reporting database",
                    icon="💼",
                ),
                rx.cond(
                    AppState.reporting_tables.length() > 0,
                    success_alert(f"Found {AppState.reporting_tables.length()} table(s) in Monthly Reporting database"),
                    info_alert("No tables found in Monthly Reporting database. Upload data to get started."),
                ),
                spacing="4",
                width="100%",
                align_items="stretch",
            ),
            rx.fragment(),
        ),
        
        divider(),
        
        # Quick Actions section
        section_header("Quick Actions", icon="🚀"),
        quick_actions(),
        
        divider(),
        
        # Footer
        rx.text(
            "Navigate using the sidebar to access specific tools and analyses",
            color=COLORS["text_secondary"],
            font_size="0.9rem",
            text_align="center",
            width="100%",
        ),
        
        spacing="4",
        align_items="stretch",
        width="100%",
        padding="2rem",
    )
