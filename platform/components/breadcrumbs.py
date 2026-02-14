"""
Breadcrumb navigation component.

Shows the current navigation path (e.g., Portfolio > Ashford > Clipping Analysis).
Clicking a breadcrumb navigates to that page.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, this becomes a <Breadcrumbs> component using React Router
"""
import streamlit as st

from styles.design_tokens import AMPYR_TEAL


def render_breadcrumbs(crumbs: list[dict] | list[str] | None = None):
    """Render breadcrumb navigation.

    Args:
        crumbs: List of breadcrumb items. Can be:
            - List of dicts: [{"label": "Dashboard", "page": "Dashboard"}, ...]
            - List of strings: ["Home", "Dashboard"] (page name = label)
            - None: auto-generate from session state
    """
    if crumbs is None:
        crumbs = _auto_breadcrumbs()

    if not crumbs:
        return

    # Normalize string crumbs to dicts
    normalized: list[dict] = []
    for crumb in crumbs:
        if isinstance(crumb, str):
            normalized.append({"label": crumb, "page": crumb})
        else:
            normalized.append(crumb)

    # Don't show breadcrumbs if we're on the Dashboard (root)
    if len(normalized) <= 1:
        return

    parts: list[str] = []
    for i, crumb in enumerate(normalized):
        label = crumb.get("label", "")
        if i < len(normalized) - 1:
            # Clickable breadcrumb
            parts.append(
                f'<a href="#" style="color: {AMPYR_TEAL}; text-decoration: none; '
                f'font-size: 0.85rem; font-weight: 500;">{label}</a>'
            )
        else:
            # Current page (not clickable)
            parts.append(
                f'<span style="color: #7F8C8D; font-size: 0.85rem; font-weight: 600;">{label}</span>'
            )

    breadcrumb_html = ' <span style="color: #BDC3C7; margin: 0 0.5rem;">›</span> '.join(parts)

    st.markdown(
        f'<div style="margin-bottom: 1rem; padding: 0.25rem 0;">{breadcrumb_html}</div>',
        unsafe_allow_html=True,
    )


def _auto_breadcrumbs() -> list[dict]:
    """Auto-generate breadcrumbs from session state."""
    crumbs: list[dict] = [{"label": "Home", "page": "Dashboard"}]

    current_page = st.session_state.get("current_page", "Dashboard")
    if current_page != "Dashboard":
        crumbs.append({"label": current_page, "page": current_page})

    # If a plant is selected, add it
    plant_name = st.session_state.get("selected_plant_name")
    if plant_name:
        crumbs.insert(-1, {"label": plant_name, "page": "Plant Detail"})

    return crumbs
