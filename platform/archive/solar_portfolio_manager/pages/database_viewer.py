"""
Database Viewer page for Solar Portfolio Manager.
Browse and query data from the DuckDB databases.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, error_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def stat_card(title: str, value: str, icon: str) -> rx.Component:
    """Render a statistics card."""
    return rx.box(
        rx.hstack(
            rx.text(icon, font_size="1.5rem"),
            rx.vstack(
                rx.text(title, color=COLORS["text_secondary"], font_size="0.8rem"),
                rx.text(value, font_weight="700", font_size="1.2rem"),
                spacing="0",
                align_items="start",
            ),
            spacing="3",
            align="center",
        ),
        style=card_style,
        flex="1",
    )


def database_viewer_page() -> rx.Component:
    """The Database Viewer page for exploring stored data."""
    return rx.vstack(
        rx.heading("🗄️ Database Viewer", style=heading_style, size="8"),
        rx.text(
            "Browse, filter, and export data from the plant registry and operational readings.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Statistics Row
        rx.cond(
            AppState.toolkit_available,
            rx.hstack(
                stat_card("Total Plants", AppState.total_plants_count.to_string(), "🏭"),
                stat_card(
                    "Total Readings", 
                    rx.cond(
                        AppState.toolkit_stats.contains("total_readings"),
                        AppState.toolkit_stats["total_readings"].to_string(),
                        "—"
                    ),
                    "📊"
                ),
                stat_card("DC Capacity", AppState.total_capacity_display, "⚡"),
                spacing="4",
                width="100%",
            ),
            info_alert("Solar Toolkit not connected. Statistics unavailable."),
        ),
        
        divider(),
        
        # View Mode Tabs
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Plants Registry", value="plants"),
                rx.tabs.trigger("Operational Readings", value="readings"),
            ),
            rx.tabs.content(
                rx.vstack(
                    section_header("Registered Plants", "View and manage the plant registry."),
                    rx.cond(
                        AppState.toolkit_plants.length() > 0,
                        rx.box(
                            rx.data_table(
                                data=AppState.toolkit_plants,
                                columns=[
                                    {"header": "Alias", "accessorKey": "alias"},
                                    {"header": "Plant UID", "accessorKey": "plant_uid"},
                                    {"header": "DC Size (kW)", "accessorKey": "dc_size_kw"},
                                ],
                                pagination=True,
                                search=True,
                            ),
                            width="100%",
                            overflow_x="auto",
                        ),
                        info_alert("No plants registered yet."),
                    ),
                    spacing="4",
                    width="100%",
                    padding="1rem 0",
                ),
                value="plants",
            ),
            rx.tabs.content(
                rx.vstack(
                    section_header("Operational Readings", "Filter and view inverter and POA readings."),
                    rx.box(
                        rx.vstack(
                            rx.text("Select a plant to view readings:", font_weight="500"),
                            rx.select(
                                AppState.registered_plant_aliases,
                                placeholder="Select plant...",
                            ),
                            rx.hstack(
                                rx.button(
                                    rx.icon("refresh-cw"),
                                    "Load Data",
                                    color_scheme="teal",
                                ),
                                rx.button(
                                    rx.icon("download"),
                                    "Export CSV",
                                    variant="outline",
                                ),
                                spacing="3",
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        style=card_style,
                        width="100%",
                    ),
                    info_alert("Select a plant and click 'Load Data' to view readings."),
                    spacing="4",
                    width="100%",
                    padding="1rem 0",
                ),
                value="readings",
            ),
            default_value="plants",
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
