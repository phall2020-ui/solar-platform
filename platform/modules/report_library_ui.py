"""
Report Library — Browse, download, and manage previously generated reports.

Provides a Streamlit page for listing saved reports, filtering by type and
date range, downloading PDFs, and deleting old reports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from components.kpi_cards import render_kpi_row
from components.layouts import page_header, filter_bar

from styles.design_tokens import AMPYR_TEAL, STATUS_COLORS

# ── Guarded service imports ─────────────────────────────────────────────

REPORTING_ENGINE_AVAILABLE = False

try:
    from services.reporting.models import ReportType, GeneratedReport
    from services.reporting.report_library import ReportLibrary

    REPORTING_ENGINE_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

UTC = timezone.utc

# ── Helpers ──────────────────────────────────────────────────────────────


def _format_file_size(size_bytes: int | float | None) -> str:
    """Return a human-readable file size string."""
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _format_duration(seconds: float | None) -> str:
    """Return a human-readable duration string."""
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes}m {secs:.0f}s"


def _report_type_options() -> list[str]:
    """Return filter options for report type, including 'All'."""
    options = ["All"]
    try:
        if REPORTING_ENGINE_AVAILABLE:
            for rt in ReportType:
                options.append(rt.value if hasattr(rt, "value") else str(rt))
    except Exception:
        pass
    return options


# ═══════════════════════════════════════════════════════════════════════
#  Public entry point
# ═══════════════════════════════════════════════════════════════════════


def render() -> None:
    """Render the Report Library page."""
    page_header(
        title="Report Library",
        subtitle="Browse, download, and manage generated reports",
        icon="📚",
    )

    # ── Engine availability gate ────────────────────────────────────────
    if not REPORTING_ENGINE_AVAILABLE:
        st.info(
            "🔧 The reporting engine is not yet available. "
            "Please ensure the `services/reporting` package is installed and "
            "restart the application."
        )
        return

    # ── Initialise library ──────────────────────────────────────────────
    library = ReportLibrary()

    # ── Filters ─────────────────────────────────────────────────────────
    st.subheader("🔍 Filters")
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        type_options = _report_type_options()
        selected_type = st.selectbox(
            "Report Type",
            options=type_options,
            index=0,
            key="rl_type_filter",
        )

    with filter_col2:
        date_from = st.date_input(
            "From Date",
            value=None,
            key="rl_date_from",
        )

    with filter_col3:
        date_to = st.date_input(
            "To Date",
            value=None,
            key="rl_date_to",
        )

    st.divider()

    # ── Fetch reports ───────────────────────────────────────────────────
    try:
        all_reports: list[Any] = library.list_reports()
    except Exception as exc:
        st.error(f"Could not load reports: {exc}")
        logger.exception("Report library list error")
        return

    # ── Apply filters ───────────────────────────────────────────────────
    filtered_reports = list(all_reports)

    if selected_type and selected_type != "All":
        filtered_reports = [
            r
            for r in filtered_reports
            if _get_attr(r, "report_type", "") == selected_type
            or str(_get_attr(r, "report_type", "")) == selected_type
        ]

    if date_from is not None:
        filtered_reports = [
            r
            for r in filtered_reports
            if _report_date(r) is not None and _report_date(r).date() >= date_from
        ]

    if date_to is not None:
        filtered_reports = [
            r
            for r in filtered_reports
            if _report_date(r) is not None and _report_date(r).date() <= date_to
        ]

    # ── Summary KPIs ────────────────────────────────────────────────────
    total_size = sum(_get_attr(r, "file_size", 0) or 0 for r in filtered_reports)
    render_kpi_row(
        [
            {
                "label": "Total Reports",
                "value": str(len(all_reports)),
                "icon": "📚",
            },
            {
                "label": "Showing",
                "value": str(len(filtered_reports)),
                "icon": "📋",
            },
            {
                "label": "Total Size",
                "value": _format_file_size(total_size),
                "icon": "💾",
            },
        ]
    )

    st.divider()

    # ── Empty state ─────────────────────────────────────────────────────
    if not filtered_reports:
        if all_reports:
            st.info("No reports match the current filters. Adjust your criteria above.")
        else:
            st.info(
                "No reports have been generated yet. "
                "Go to the **Report Builder** to create your first report."
            )
        return

    # ── Report list ─────────────────────────────────────────────────────
    # Session state for delete confirmation
    st.session_state.setdefault("rl_confirm_delete", None)

    for idx, report in enumerate(filtered_reports):
        report_id = _get_attr(report, "id", None) or _get_attr(report, "report_id", idx)
        filename = _get_attr(report, "filename", f"report_{idx}.pdf")
        report_type = _get_attr(report, "report_type", "—")
        created_at = _report_date(report)
        file_size = _get_attr(report, "file_size", None)
        page_count = _get_attr(report, "page_count", None)
        gen_time = _get_attr(report, "generation_time", None)
        metadata = _get_attr(report, "metadata", {}) or {}

        created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "—"

        with st.container(border=True):
            col_info, col_meta, col_actions = st.columns([3, 2, 1])

            with col_info:
                st.markdown(f"**{filename}**")
                badge_color = AMPYR_TEAL
                st.markdown(
                    f'<span style="background:{badge_color};color:#fff;padding:2px 8px;'
                    f'border-radius:4px;font-size:0.8rem;">{report_type}</span>',
                    unsafe_allow_html=True,
                )
                if metadata.get("template"):
                    st.caption(f"Template: {metadata['template']}")
                if metadata.get("start_period") and metadata.get("end_period"):
                    st.caption(
                        f"Period: {metadata['start_period']} → {metadata['end_period']}"
                    )

            with col_meta:
                st.caption(f"📅 Created: {created_str}")
                st.caption(f"💾 Size: {_format_file_size(file_size)}")
                if page_count is not None:
                    st.caption(f"📄 Pages: {page_count}")
                if gen_time is not None:
                    st.caption(f"⏱️ Generation: {_format_duration(gen_time)}")

            with col_actions:
                # Download
                pdf_bytes = _get_report_bytes(library, report_id)
                if pdf_bytes is not None:
                    st.download_button(
                        label="⬇️",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                        key=f"rl_dl_{report_id}",
                        help="Download PDF",
                        use_container_width=True,
                    )

                # Delete with confirmation
                if st.session_state["rl_confirm_delete"] == report_id:
                    st.warning("Delete?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes", key=f"rl_yes_{report_id}", type="primary"):
                            try:
                                library.delete(report_id)
                                st.session_state["rl_confirm_delete"] = None
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Delete failed: {exc}")
                                logger.exception("Report delete error")
                    with c2:
                        if st.button("No", key=f"rl_no_{report_id}"):
                            st.session_state["rl_confirm_delete"] = None
                            st.rerun()
                else:
                    if st.button("🗑️", key=f"rl_del_{report_id}", help="Delete report"):
                        st.session_state["rl_confirm_delete"] = report_id
                        st.rerun()


# ── Internal helpers ─────────────────────────────────────────────────────


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Safely get an attribute or dict key from an object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _report_date(report: Any) -> datetime | None:
    """Extract a datetime from a report object."""
    for key in ("created_at", "generated_at", "timestamp"):
        val = _get_attr(report, key)
        if val is None:
            continue
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                pass
    return None


def _get_report_bytes(library: Any, report_id: Any) -> bytes | None:
    """Retrieve PDF bytes for a report, returning None on failure."""
    try:
        report = library.get_by_id(report_id)
        if report is None:
            return None
        # The object may carry bytes directly or expose a path
        pdf = _get_attr(report, "pdf_bytes") or _get_attr(report, "content")
        if isinstance(pdf, bytes):
            return pdf
        path = _get_attr(report, "file_path") or _get_attr(report, "path")
        if path:
            from pathlib import Path

            p = Path(path)
            if p.is_file():
                return p.read_bytes()
    except Exception as exc:
        logger.warning("Could not load report %s: %s", report_id, exc)
    return None
