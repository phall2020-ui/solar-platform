"""Pre-defined report templates.

Each template is a :class:`ReportTemplate` with a curated list of
sections. Use :func:`get_template` to look up a template by name.
"""
from __future__ import annotations

from solar_platform.reporting.models import (
    ReportSection,
    ReportTemplate,
    ReportType,
    SectionType,
)

# ── Monthly Performance Report ───────────────────────────────────────

MONTHLY_REPORT = ReportTemplate(
    name="Monthly Performance Report",
    type=ReportType.MONTHLY_PERFORMANCE,
    description="Comprehensive monthly portfolio performance report with KPIs, generation data, PR trends, loss analysis, and alerts.",
    orientation="portrait",
    sections=[
        ReportSection(type=SectionType.COVER, title="Cover"),
        ReportSection(type=SectionType.KPI_SUMMARY, title="Executive Summary"),
        ReportSection(
            type=SectionType.GENERATION_TABLE,
            title="Portfolio Generation",
            page_break_before=True,
        ),
        ReportSection(type=SectionType.PR_CHART, title="Fleet PR Trend"),
        ReportSection(type=SectionType.GENERATION_CHART, title="Daily Generation"),
        ReportSection(
            type=SectionType.WATERFALL,
            title="Loss Waterfall",
            page_break_before=True,
        ),
        ReportSection(type=SectionType.ALERT_SUMMARY, title="Alerts & Incidents"),
        ReportSection(
            type=SectionType.APPENDIX,
            title="Data Quality",
            config={"type": "data_quality"},
        ),
        ReportSection(
            type=SectionType.APPENDIX,
            title="Methodology",
            config={"type": "methodology"},
        ),
    ],
)

# ── ExCom Summary Report ─────────────────────────────────────────────

EXCOM_REPORT = ReportTemplate(
    name="ExCom Summary Report",
    type=ReportType.EXCOM_SUMMARY,
    description="Condensed executive committee report (2–3 pages) with portfolio KPIs, traffic-light grid, and key issues.",
    orientation="landscape",
    sections=[
        ReportSection(type=SectionType.COVER, title="Cover"),
        ReportSection(type=SectionType.KPI_SUMMARY, title="Portfolio KPIs"),
        ReportSection(
            type=SectionType.GENERATION_TABLE,
            title="Traffic Light Grid",
            page_break_before=True,
        ),
        ReportSection(type=SectionType.ALERT_SUMMARY, title="Key Issues"),
        ReportSection(
            type=SectionType.TEXT,
            title="Outlook",
            config={"text": "Next month outlook and expected generation — to be completed by the reporting team."},
        ),
    ],
)

# ── O&M Report ────────────────────────────────────────────────────────

OM_REPORT = ReportTemplate(
    name="O&M Report",
    type=ReportType.OM_REPORT,
    description="Operations & Maintenance report covering availability, tickets, downtime, and corrective actions.",
    orientation="portrait",
    sections=[
        ReportSection(type=SectionType.COVER, title="Cover"),
        ReportSection(type=SectionType.KPI_SUMMARY, title="Availability Summary"),
        ReportSection(
            type=SectionType.TICKET_SUMMARY,
            title="Ticket Summary",
            page_break_before=True,
        ),
        ReportSection(type=SectionType.ALERT_SUMMARY, title="Downtime Analysis"),
        ReportSection(
            type=SectionType.PLANT_DETAIL,
            title="Plant Detail",
            page_break_before=True,
        ),
        ReportSection(
            type=SectionType.TEXT,
            title="Recommendations",
            config={"text": "Recommendations to be completed by the O&M team."},
        ),
        ReportSection(
            type=SectionType.APPENDIX,
            title="Methodology",
            config={"type": "methodology"},
        ),
    ],
)

# ── Template registry ─────────────────────────────────────────────────

ALL_TEMPLATES: dict[str, ReportTemplate] = {
    MONTHLY_REPORT.type.value: MONTHLY_REPORT,
    EXCOM_REPORT.type.value: EXCOM_REPORT,
    OM_REPORT.type.value: OM_REPORT,
}


def get_template(name: str) -> ReportTemplate | None:
    """Look up a template by its ``ReportType`` value or display name.

    Returns ``None`` if no match is found.
    """
    # Direct key lookup
    if name in ALL_TEMPLATES:
        return ALL_TEMPLATES[name]

    # Fallback: match by display name (case-insensitive)
    name_lower = name.lower()
    for tmpl in ALL_TEMPLATES.values():
        if tmpl.name.lower() == name_lower:
            return tmpl

    return None
