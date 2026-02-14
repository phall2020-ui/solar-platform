"""Page layout wrapper component."""
import reflex as rx
from solar_portfolio_manager.styles import main_content_style, heading_style, divider_style, COLORS
from solar_portfolio_manager.components.breadcrumb import breadcrumb


def page_layout(
    title: str,
    description: str = "",
    icon: str = "",
    breadcrumb_items: list = None,
    children: list = None,
) -> rx.Component:
    """
    Standard page layout wrapper with title, description, and breadcrumbs.
    
    Args:
        title: Page title
        description: Optional page description
        icon: Optional emoji icon for the title
        breadcrumb_items: List of breadcrumb items
        children: Page content components
    
    Returns:
        Reflex Component
    """
    # Build title with icon
    title_text = f"{icon} {title}" if icon else title
    
    # Build breadcrumb
    crumbs = breadcrumb_items or ["Home", title]
    breadcrumb_component = breadcrumb(crumbs)
    
    # Build description
    description_component = rx.fragment()
    if description:
        description_component = rx.text(
            description,
            color=COLORS["text_secondary"],
            font_size="1rem",
            margin_bottom="1.5rem",
        )
    
    # Build content
    content_children = children or []
    
    return rx.box(
        rx.vstack(
            breadcrumb_component,
            rx.heading(
                title_text,
                size="7",
                style=heading_style,
            ),
            description_component,
            *content_children,
            spacing="2",
            align_items="stretch",
            width="100%",
        ),
        style=main_content_style,
    )


def section_header(
    title: str,
    description: str = "",
    icon: str = "",
) -> rx.Component:
    """
    Render a section header within a page.
    
    Args:
        title: Section title
        description: Optional description
        icon: Optional emoji icon
    
    Returns:
        Reflex Component
    """
    title_text = f"{icon} {title}" if icon else title
    
    description_component = rx.fragment()
    if description:
        description_component = rx.text(
            description,
            color=COLORS["text_secondary"],
            font_size="0.95rem",
            margin_top="0",
        )
    
    return rx.box(
        rx.vstack(
            rx.heading(
                title_text,
                size="5",
                color=COLORS["primary"],
            ),
            description_component,
            spacing="2",
            align_items="flex_start",
        ),
        margin_top="2rem",
        margin_bottom="1rem",
    )


def divider() -> rx.Component:
    """Render a styled horizontal divider."""
    return rx.box(
        style=divider_style,
    )
