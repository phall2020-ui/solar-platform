"""
Solar Portfolio Manager - Reflex App Entry Point
Main application combining Solar Toolkit and Monthly Reporting.

Migrated from Streamlit app.py to Reflex framework.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.sidebar import sidebar
from solar_portfolio_manager.styles import main_content_style, COLORS, GLOBAL_STYLES

# Import pages
from solar_portfolio_manager.pages import dashboard
from solar_portfolio_manager.pages.plant_management import plant_management_page
from solar_portfolio_manager.pages.poa_import import poa_import_page
from solar_portfolio_manager.pages.database_viewer import database_viewer_page
from solar_portfolio_manager.pages.data_explorer import data_explorer_page
from solar_portfolio_manager.pages.data_overview import data_overview_page
# Phase 3: Analysis Pages
from solar_portfolio_manager.pages.fouling_analysis import fouling_analysis_page
from solar_portfolio_manager.pages.shading_analysis import shading_analysis_page
from solar_portfolio_manager.pages.clipping_analysis import clipping_analysis_page
from solar_portfolio_manager.pages.thermal_loss_analysis import thermal_loss_analysis_page
from solar_portfolio_manager.pages.loss_waterfall import loss_waterfall_page
# Phase 4: Reporting Pages
from solar_portfolio_manager.pages.monthly_performance import monthly_performance_page
from solar_portfolio_manager.pages.waterfall_analysis import waterfall_chart_page
from solar_portfolio_manager.pages.excom_report import excom_report_page
from solar_portfolio_manager.pages.report_builder import report_builder_page
from solar_portfolio_manager.pages.comparative_analysis import comparative_analysis_page
from solar_portfolio_manager.pages.data_export import data_export_page
# Phase 5: Settings Pages
from solar_portfolio_manager.pages.api_management import api_management_page
from solar_portfolio_manager.pages.notifications import notifications_page
from solar_portfolio_manager.pages.settings import settings_page




def page_router() -> rx.Component:
    """Route to appropriate page based on current_page state."""
    return rx.match(
        AppState.current_page,
        ("Dashboard", dashboard.page()),
        ("Plant Management", plant_management_page()),
        ("POA Import", poa_import_page()),
        ("Database Viewer", database_viewer_page()),
        ("Data Explorer", data_explorer_page()),
        ("Data Overview", data_overview_page()),
        ("Fouling Analysis", fouling_analysis_page()),
        ("Shading Analysis", shading_analysis_page()),
        ("Clipping Analysis", clipping_analysis_page()),
        ("Thermal Loss Analysis", thermal_loss_analysis_page()),
        ("Loss Waterfall", loss_waterfall_page()),
        ("Monthly Performance", monthly_performance_page()),
        ("Waterfall Analysis", waterfall_chart_page()),
        ("Excom Report", excom_report_page()),
        ("Report Builder", report_builder_page()),
        ("Comparative Analysis", comparative_analysis_page()),
        ("Data Export", data_export_page()),
        ("API Management", api_management_page()),
        ("Notifications", notifications_page()),
        ("Settings", settings_page()),
        # Default to dashboard
        dashboard.page(),
    )


def index() -> rx.Component:
    """Main application layout with sidebar and content area."""
    return rx.box(
        # Sidebar navigation
        sidebar(),
        
        # Main content area
        rx.box(
            page_router(),
            style=main_content_style,
        ),
        
        # Global styles
        rx.script(f"""
            const style = document.createElement('style');
            style.textContent = `{GLOBAL_STYLES}`;
            document.head.appendChild(style);
        """),
        
        width="100%",
        min_height="100vh",
        background_color=COLORS["background"],
    )


# Create the app
app = rx.App(
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Lato:wght@400;500;600;700&display=swap",
    ],
    style={
        "background_color": COLORS["background"],
        "color": COLORS["text"],
        "font_family": "'Lato', 'Segoe UI', sans-serif",
    },
)

# Add the main page
app.add_page(index, on_load=AppState.on_load, title="AMPYR Solar Portfolio Manager")
