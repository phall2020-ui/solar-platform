"""
Plant Management page for Solar Portfolio Manager.
Allows registering new sites from API and managing existing ones.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, success_alert, error_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style, button_primary_style


def plant_card(plant: dict) -> rx.Component:
    """Render a card for a registered plant."""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.heading(plant.get("alias", "Unknown"), size="4"),
                rx.text(plant.get("plant_uid", "No UID"), color=COLORS["text_secondary"], font_size="0.8rem"),
                align_items="start",
                spacing="1",
            ),
            rx.spacer(),
            rx.badge(
                f"{plant.get('dc_size_kw', 0)} kW",
                color_scheme="teal",
                variant="soft",
            ),
            rx.menu.root(
                rx.menu.trigger(
                    rx.button(rx.icon("ellipsis-vertical"), variant="ghost", size="1")
                ),
                rx.menu.content(
                    rx.menu.item("Edit Details", icon="pencil"),
                    rx.menu.separator(),
                    rx.menu.item(
                        "Remove Plant", 
                        icon="trash", 
                        color="red",
                        on_click=lambda: AppState.delete_plant(plant["alias"])
                    ),
                ),
            ),
            align="center",
            width="100%",
        ),
        style=card_style,
    )


def new_plant_item(plant: dict) -> rx.Component:
    """Render an item for a discovered but unregistered plant."""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(plant["name"], font_weight="600"),
                rx.text(plant["uid"], color=COLORS["text_secondary"], font_size="0.8rem"),
                align_items="start",
                spacing="0",
            ),
            rx.spacer(),
            rx.dialog.root(
                rx.dialog.trigger(
                    rx.button("Register", size="2", variant="solid", color_scheme="teal")
                ),
                rx.dialog.content(
                    rx.dialog.title(f"Register {plant['name']}"),
                    rx.dialog.description(
                        "Complete the details below to add this site to the registry."
                    ),
                    rx.form(
                        rx.vstack(
                            rx.text("Alias (Internal Name)", font_size="sm", font_weight="500"),
                            rx.input(placeholder="e.g. My Solar Site", default_value=plant["name"], name="alias"),
                            
                            rx.text("DC Capacity (kW)", font_size="sm", font_weight="500"),
                            rx.input(placeholder="1000.0", type="number", name="dc_size", default_value="1000"),
                            
                            rx.text("Inverter IDs (comma separated)", font_size="sm", font_weight="500"),
                            rx.text_area(placeholder="INV:1, INV:2", name="inv_ids"),
                            
                            rx.text("Cloud POA ID (Optional)", font_size="sm", font_weight="500"),
                            rx.input(placeholder="POA:SITE_1", name="poa_id"),
                            
                            # Hidden field for UID
                            rx.input(type="hidden", name="uid", value=plant["uid"]),
                            
                            spacing="3",
                            width="100%",
                            margin_top="1rem",
                        ),
                        rx.hstack(
                            rx.dialog.close(
                                rx.button("Cancel", variant="soft", color_scheme="gray", type="button")
                            ),
                            rx.button(
                                "Save & Register", 
                                color_scheme="teal",
                                type="submit",
                            ),
                            margin_top="1.5rem",
                            justify="end",
                            spacing="3",
                        ),
                        on_submit=AppState.handle_register_plant_form,
                        reset_on_submit=True,
                    ),
                ),
            ),
            width="100%",
            padding="0.75rem",
            border_bottom=f"1px solid {COLORS['border']}",
        )
    )



def plant_management_page() -> rx.Component:
    """The main Plant Management page."""
    return rx.vstack(
        rx.heading("🔧 Plant Management", style=heading_style, size="8"),
        rx.text("Connect new sites from the API and manage your registered assets.", color=COLORS["text_secondary"]),
        
        divider(),
        
        # Section 1: API Discovery
        section_header("Discover New Sites", "Scan the EMIG API to find sites not yet in your database."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.button(
                        rx.cond(AppState.is_scanning, rx.spinner(size="1"), rx.icon("refresh-cw")),
                        "Scan API for Updates",
                        on_click=AppState.scan_api_for_plants,
                        disabled=AppState.is_scanning,
                        color_scheme="teal",
                    ),
                    rx.cond(
                        AppState.api_scan_results.length() > 0,
                        rx.badge(f"{AppState.api_scan_results.length()} New Found", color_scheme="green"),
                    ),
                    spacing="4",
                    align="center",
                ),
                
                rx.cond(
                    AppState.scan_error != "",
                    error_alert(AppState.scan_error),
                ),
                
                rx.cond(
                    AppState.api_scan_results.length() > 0,
                    rx.box(
                        rx.vstack(
                            rx.foreach(AppState.api_scan_results, new_plant_item),
                            spacing="0",
                            width="100%",
                        ),
                        border=f"1px solid {COLORS['border']}",
                        border_radius="12px",
                        width="100%",
                        margin_top="1rem",
                        overflow="hidden",
                    ),
                ),
                align_items="start",
                width="100%",
            ),
            width="100%",
        ),
        
        divider(),
        
        # Section 2: Registered Sites
        section_header("Registered Assets", "Manage configuration and metadata for your active sites."),
        
        rx.cond(
            AppState.toolkit_plants.length() == 0,
            info_alert("No sites registered yet. Use the scan tool above to get started."),
            rx.grid(
                rx.foreach(AppState.toolkit_plants, plant_card),
                columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                spacing="4",
                width="100%",
            ),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
