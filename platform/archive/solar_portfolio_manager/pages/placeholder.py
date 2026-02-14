"""
Placeholder page for pages not yet migrated.
"""
import reflex as rx
from solar_portfolio_manager.styles import heading_style, COLORS
from solar_portfolio_manager.components.alert import info_alert


def page(page_name: str) -> rx.Component:
    """
    Render a placeholder page for pages not yet migrated.
    
    Args:
        page_name: Name of the page
    
    Returns:
        Reflex Component
    """
    return rx.vstack(
        rx.heading(
            f"🚧 {page_name}",
            size="7",
            style=heading_style,
        ),
        info_alert(
            f"The **{page_name}** page is being migrated to Reflex. "
            "This functionality will be available soon."
        ),
        rx.text(
            "In the meantime, you can use the Streamlit version by running: "
            "`streamlit run app.py`",
            color=COLORS["text_secondary"],
            font_size="0.9rem",
        ),
        spacing="4",
        align_items="flex_start",
        width="100%",
        padding="2rem",
    )


def plant_management_page() -> rx.Component:
    return page("Plant Management")


def poa_import_page() -> rx.Component:
    return page("POA Import")


def database_viewer_page() -> rx.Component:
    return page("Database Viewer")


def data_explorer_page() -> rx.Component:
    return page("Data Explorer")


def data_overview_page() -> rx.Component:
    return page("Data Overview")


def fouling_page() -> rx.Component:
    return page("Fouling Analysis")


def shading_page() -> rx.Component:
    return page("Shading Analysis")


def clipping_page() -> rx.Component:
    return page("Clipping Analysis")


def thermal_loss_page() -> rx.Component:
    return page("Thermal Loss Analysis")


def monthly_performance_page() -> rx.Component:
    return page("Monthly Performance")


def report_builder_page() -> rx.Component:
    return page("Report Builder")


def comparative_analysis_page() -> rx.Component:
    return page("Comparative Analysis")


def data_export_page() -> rx.Component:
    return page("Data Export")


def api_management_page() -> rx.Component:
    return page("API Management")


def notifications_page() -> rx.Component:
    return page("Notifications")


def settings_page() -> rx.Component:
    return page("Settings")
