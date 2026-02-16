"""
Report Builder — Template-driven PDF report generation.

Provides a Streamlit page for selecting report templates, configuring
period / plant filters, toggling sections, and generating downloadable
PDF reports via the Phase 5 reporting engine services.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import streamlit as st

from app.components.kpi_cards import render_kpi_row
from app.components.layouts import page_header

from app.styles.design_tokens import AMPYR_TEAL, STATUS_COLORS

# ── Report Item / Registry (used by report_button.py) ──────────────────


@dataclass
class ReportItem:
    """A single item (chart/table/KPI/text) to include in a bespoke report."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    item_type: Literal["chart", "table", "kpi", "text"] = "chart"
    title: str = ""
    description: str = ""
    source_tab: str = ""

    # Chart storage
    figure: Any | None = None
    figure_bytes: bytes | None = None

    # Table storage
    dataframe: Any | None = None

    # KPI storage
    metrics: dict | None = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    site_filter: str | None = None
    date_range: tuple | None = None

    # Layout
    order: int = 0
    page_break_before: bool = False
    width: Literal["full", "half"] = "full"


@dataclass
class ReportConfig:
    """Configuration for the entire bespoke report."""

    title: str = "Monthly Executive Report"
    subtitle: str = ""
    report_month: str = ""
    items: list[ReportItem] = field(default_factory=list)
    include_cover_page: bool = True
    include_table_of_contents: bool = False
    created_at: datetime = field(default_factory=datetime.now)


class ReportRegistry:
    """Manages collections of ReportItem objects in session state."""

    SESSION_KEY = "report_registry"

    @classmethod
    def initialize(cls) -> None:
        if cls.SESSION_KEY not in st.session_state:
            st.session_state[cls.SESSION_KEY] = ReportConfig()

    @classmethod
    def get_config(cls) -> ReportConfig:
        cls.initialize()
        return st.session_state[cls.SESSION_KEY]

    @classmethod
    def add_item(cls, item: ReportItem) -> bool:
        config = cls.get_config()
        item.order = len(config.items)
        config.items.append(item)
        return True

    @classmethod
    def remove_item(cls, item_id: str) -> None:
        config = cls.get_config()
        config.items = [i for i in config.items if i.id != item_id]
        cls._reorder()

    @classmethod
    def reorder_items(cls, new_order: list[str]) -> None:
        config = cls.get_config()
        by_id = {i.id: i for i in config.items}
        config.items = [by_id[uid] for uid in new_order if uid in by_id]
        cls._reorder()

    @classmethod
    def _reorder(cls) -> None:
        for idx, item in enumerate(cls.get_config().items):
            item.order = idx

    @classmethod
    def clear(cls) -> None:
        st.session_state[cls.SESSION_KEY] = ReportConfig()

    @classmethod
    def get_count(cls) -> int:
        return len(cls.get_config().items)

    @classmethod
    def set_report_month(cls, month: str) -> None:
        cls.get_config().report_month = month

    @classmethod
    def set_title(cls, title: str) -> None:
        cls.get_config().title = title

# ── Guarded service imports ─────────────────────────────────────────────

REPORTING_ENGINE_AVAILABLE = False

try:
    from solar_platform.reporting.models import (
        ReportType,
        SectionType,
        ReportSection,
        ReportTemplate,
        GeneratedReport,
    )
    from solar_platform.reporting.templates import ALL_TEMPLATES, get_template
    from solar_platform.reporting.pdf_renderer import PDFRenderer
    from solar_platform.reporting.data_fetcher import ReportDataFetcher
    from solar_platform.reporting.report_library import ReportLibrary

    REPORTING_ENGINE_AVAILABLE = True
except ImportError:
    pass

# Plant repository — also guarded
_PLANT_REPO_AVAILABLE = False
try:
    from solar_platform.db.repository import PlantRepository

    _PLANT_REPO_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

UTC = timezone.utc

# ── Helpers ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _get_plant_options() -> list[dict[str, str]]:
    """Return list of ``{uid, alias}`` dicts from the plant repository."""
    if not _PLANT_REPO_AVAILABLE:
        return []
    try:
        repo = PlantRepository()
        df = repo.get_all()
        if df.empty:
            return []
        plants: list[dict[str, str]] = []
        for _, row in df.iterrows():
            plants.append(
                {
                    "uid": str(row.get("plant_uid", "")),
                    "alias": str(row.get("alias", row.get("plant_uid", "Unknown"))),
                }
            )
        return plants
    except Exception as exc:
        logger.warning("Could not load plants: %s", exc)
        return []


def _month_options(past_months: int = 24) -> list[str]:
    """Generate a list of ``YYYY-MM`` strings for the last *past_months*."""
    now = datetime.now(UTC)
    months: list[str] = []
    for offset in range(past_months):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year:04d}-{month:02d}")
    return months


# ═══════════════════════════════════════════════════════════════════════
#  Public entry point
# ═══════════════════════════════════════════════════════════════════════


def render() -> None:
    """Render the Report Builder page."""
    page_header(
        title="Report Builder",
        subtitle="Generate branded PDF reports from templates",
        icon="📑",
    )

    # ── Engine availability gate ────────────────────────────────────────
    if not REPORTING_ENGINE_AVAILABLE:
        st.info(
            "🔧 The reporting engine is not yet available. "
            "Please ensure the `services/reporting` package is installed and "
            "restart the application."
        )
        return

    # ── Session state defaults ──────────────────────────────────────────
    st.session_state.setdefault("rb_generated_pdf", None)
    st.session_state.setdefault("rb_generated_filename", "")
    st.session_state.setdefault("rb_generation_error", None)

    # ── Layout: config sidebar + preview area ───────────────────────────
    col_config, col_preview = st.columns([1, 2])

    # ── Configuration panel ─────────────────────────────────────────────
    with col_config:
        st.subheader("⚙️ Configuration")

        # Template selector
        template_names = list(ALL_TEMPLATES.keys())
        selected_template_name = st.selectbox(
            "Report Template",
            options=template_names,
            key="rb_template",
            help="Choose the type of report to generate.",
        )
        template: ReportTemplate = get_template(selected_template_name)

        st.caption(f"_{getattr(template, 'description', 'No description')}_")

        st.divider()

        # Period picker
        st.markdown("**Reporting Period**")
        month_opts = _month_options(past_months=24)
        period_col1, period_col2 = st.columns(2)
        with period_col1:
            start_period = st.selectbox(
                "Start Month",
                options=month_opts,
                index=min(1, len(month_opts) - 1),
                key="rb_start_period",
            )
        with period_col2:
            end_period = st.selectbox(
                "End Month",
                options=month_opts,
                index=0,
                key="rb_end_period",
            )

        st.divider()

        # Plant filter
        st.markdown("**Plants**")
        plant_options = _get_plant_options()
        if plant_options:
            alias_to_uid = {p["alias"]: p["uid"] for p in plant_options}
            selected_aliases = st.multiselect(
                "Select Plants",
                options=list(alias_to_uid.keys()),
                default=list(alias_to_uid.keys()),
                key="rb_plants",
                help="Leave empty to include all plants.",
            )
            selected_uids = (
                [alias_to_uid[a] for a in selected_aliases]
                if selected_aliases
                else list(alias_to_uid.values())
            )
        else:
            st.caption("No plants found — report will use all available data.")
            selected_uids: list[str] = []

        st.divider()

        # Section toggles
        st.markdown("**Sections**")
        template_sections: list[Any] = getattr(template, "sections", [])
        enabled_sections: list[Any] = []
        for section in template_sections:
            label = getattr(section, "title", str(section))
            checked = st.checkbox(
                label,
                value=getattr(section, "enabled", True),
                key=f"rb_sec_{label}",
            )
            if checked:
                enabled_sections.append(section)

        if not enabled_sections and template_sections:
            st.warning("Select at least one section to generate a report.")

    # ── Preview / Generation panel ──────────────────────────────────────
    with col_preview:
        st.subheader("📄 Report Preview")

        # Summary KPIs
        render_kpi_row(
            [
                {
                    "label": "Template",
                    "value": selected_template_name,
                    "icon": "📋",
                },
                {
                    "label": "Period",
                    "value": f"{start_period} → {end_period}",
                    "icon": "📅",
                },
                {
                    "label": "Sections",
                    "value": str(len(enabled_sections)),
                    "icon": "📑",
                },
                {
                    "label": "Plants",
                    "value": str(len(selected_uids)) if selected_uids else "All",
                    "icon": "🏭",
                },
            ]
        )

        st.divider()

        # Section outline
        if enabled_sections:
            st.markdown("**Included Sections**")
            for i, section in enumerate(enabled_sections, 1):
                title = getattr(section, "title", str(section))
                st.markdown(f"{i}. {title}")
        else:
            st.caption("No sections selected.")

        st.divider()

        # ── Generate button ─────────────────────────────────────────────
        generate_disabled = len(enabled_sections) == 0
        if st.button(
            "🚀 Generate PDF",
            type="primary",
            use_container_width=True,
            disabled=generate_disabled,
            key="rb_generate_btn",
        ):
            _generate_report(
                template=template,
                start_period=start_period,
                end_period=end_period,
                plant_uids=selected_uids,
                enabled_sections=enabled_sections,
            )

        # ── Show generation result ──────────────────────────────────────
        if st.session_state["rb_generation_error"]:
            st.error(f"Generation failed: {st.session_state['rb_generation_error']}")

        if st.session_state["rb_generated_pdf"] is not None:
            pdf_bytes: bytes = st.session_state["rb_generated_pdf"]
            filename: str = st.session_state["rb_generated_filename"]

            st.success(f"✅ Report generated — **{len(pdf_bytes) / 1024:.1f} KB**")

            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                use_container_width=True,
                key="rb_download_btn",
            )

            # Optionally save to library
            if st.button("💾 Save to Report Library", key="rb_save_lib"):
                try:
                    library = ReportLibrary()
                    library.save(
                        filename=filename,
                        pdf_bytes=pdf_bytes,
                        report_type=getattr(template, "report_type", None),
                        metadata={
                            "template": selected_template_name,
                            "start_period": start_period,
                            "end_period": end_period,
                            "plant_uids": selected_uids,
                            "generated_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    st.success("Report saved to library.")
                except Exception as exc:
                    st.error(f"Could not save report: {exc}")
                    logger.exception("Report library save error")


def _generate_report(
    template: Any,
    start_period: str,
    end_period: str,
    plant_uids: list[str],
    enabled_sections: list[Any],
) -> None:
    """Run the report generation pipeline with a progress spinner."""
    st.session_state["rb_generated_pdf"] = None
    st.session_state["rb_generated_filename"] = ""
    st.session_state["rb_generation_error"] = None

    try:
        with st.spinner("Fetching data and generating report…"):
            # 1. Fetch data
            fetcher = ReportDataFetcher()
            data = fetcher.fetch_all(
                template=template,
                start=start_period,
                end=end_period,
                plant_uids=plant_uids,
            )

            # 2. Build filename
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            safe_name = getattr(template, "name", "report").replace(" ", "_")
            filename = f"{safe_name}_{start_period}_to_{end_period}_{timestamp}.pdf"

            # 3. Render PDF
            renderer = PDFRenderer()
            pdf_bytes = renderer.render(
                template=template,
                data=data,
                filename=filename,
            )

            st.session_state["rb_generated_pdf"] = pdf_bytes
            st.session_state["rb_generated_filename"] = filename

    except Exception as exc:
        logger.exception("Report generation failed")
        st.session_state["rb_generation_error"] = str(exc)
