"""
POA Import page for Solar Portfolio Manager.
Upload and import SolarGIS POA irradiance data.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, warning_alert, success_alert, error_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def poa_import_page() -> rx.Component:
    """The POA Import page for uploading irradiance data."""
    return rx.vstack(
        rx.heading("📥 POA Import", style=heading_style, size="8"),
        rx.text(
            "Import Plane of Array (POA) irradiance data from SolarGIS CSV files.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Info section
        rx.box(
            rx.vstack(
                rx.text(
                    "POA data covers system-level irradiance measurements and is stored "
                    "separately from inverter readings. Data can be joined for analysis using timestamps.",
                    color=COLORS["text_secondary"],
                    font_size="0.9rem",
                ),
                spacing="2",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Plant Mapping Section - Move this first so user selects plant before upload
        section_header("Select Plant", "Choose the plant for POA data import."),
        
        rx.cond(
            AppState.toolkit_plants.length() == 0,
            warning_alert("No plants registered. Please register plants in Plant Management first."),
            rx.box(
                rx.vstack(
                    rx.text(
                        "Select a plant to associate with the uploaded POA data.",
                        color=COLORS["text_secondary"],
                    ),
                    rx.select(
                        AppState.registered_plant_aliases,
                        placeholder="Select a plant...",
                        value=AppState.poa_import_plant_alias,
                        on_change=AppState.set_poa_import_plant_alias,
                    ),
                    rx.text("Date Range (optional)", font_weight="600", margin_top="1rem"),
                    rx.hstack(
                        rx.input(
                            type="date",
                            value=AppState.poa_import_start_date,
                            on_change=AppState.set_poa_import_start_date,
                        ),
                        rx.text("to"),
                        rx.input(
                            type="date",
                            value=AppState.poa_import_end_date,
                            on_change=AppState.set_poa_import_end_date,
                        ),
                        spacing="2",
                        align="center",
                    ),
                    spacing="3",
                    width="100%",
                ),
                style=card_style,
                width="100%",
            ),
        ),
        
        divider(),
        
        # Upload Section
        section_header("Upload Files", "Select SolarGIS CSV files to import."),
        
        rx.box(
            rx.vstack(
                rx.upload(
                    rx.vstack(
                        rx.icon("cloud-upload", size=48, color=COLORS["primary"]),
                        rx.text("Drag & drop CSV files here", font_weight="600"),
                        rx.text("or click to browse", color=COLORS["text_secondary"], font_size="0.9rem"),
                        spacing="2",
                        align="center",
                    ),
                    id="poa_upload",
                    accept={".csv": ["text/csv"]},
                    max_files=10,
                    border=f"2px dashed {COLORS['border']}",
                    padding="3rem",
                    border_radius="12px",
                    width="100%",
                ),
                
                rx.cond(
                    rx.selected_files("poa_upload").length() > 0,
                    rx.vstack(
                        rx.text("Selected files:", font_weight="600", margin_top="1rem"),
                        rx.foreach(
                            rx.selected_files("poa_upload"),
                            lambda f: rx.hstack(
                                rx.icon("file-text", size=16),
                                rx.text(f),
                                spacing="2",
                            )
                        ),
                        rx.hstack(
                            rx.button(
                                "Clear",
                                on_click=rx.clear_selected_files("poa_upload"),
                                variant="soft",
                                color_scheme="gray",
                                size="2",
                            ),
                            rx.button(
                                rx.cond(
                                    AppState.poa_import_loading,
                                    rx.spinner(size="1"),
                                    rx.icon("import"),
                                ),
                                "Import POA Data",
                                color_scheme="teal",
                                on_click=AppState.handle_poa_upload(
                                    rx.upload_files(upload_id="poa_upload")
                                ),
                                disabled=AppState.poa_import_loading | (AppState.poa_import_plant_alias == ""),
                            ),
                            spacing="3",
                            margin_top="0.5rem",
                        ),
                        align_items="start",
                        width="100%",
                    ),
                ),
                
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        
        # Success/Error messages
        rx.cond(
            AppState.poa_import_result != "",
            success_alert(AppState.poa_import_result),
            rx.fragment(),
        ),
        rx.cond(
            AppState.poa_import_error != "",
            error_alert(AppState.poa_import_error),
            rx.fragment(),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
