"""Breadcrumb navigation component."""
import reflex as rx
from solar_portfolio_manager.styles import COLORS


def breadcrumb(items: list) -> rx.Component:
    """
    Render breadcrumb navigation.
    
    Args:
        items: List of breadcrumb items (strings). Last item is active.
    
    Returns:
        Reflex Component
    """
    if not items:
        return rx.fragment()
    
    crumbs = []
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        
        # Add separator if not first item
        if i > 0:
            crumbs.append(
                rx.text(
                    " / ",
                    color=COLORS["text_secondary"],
                    opacity="0.6",
                )
            )
        
        # Add crumb
        if is_last:
            crumbs.append(
                rx.text(
                    item,
                    color=COLORS["primary"],
                    font_weight="600",
                )
            )
        else:
            crumbs.append(
                rx.text(
                    item,
                    color=COLORS["text_secondary"],
                )
            )
    
    return rx.hstack(
        *crumbs,
        spacing="1",
        margin_bottom="0.75rem",
        font_size="0.9rem",
    )
