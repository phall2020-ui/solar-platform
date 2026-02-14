"""PDF rendering engine using ReportLab.

Takes: ReportTemplate + fetched data → branded PDF file.

Uses existing ReportLab dependency (already in requirements.txt).
Brand styling from styles/design_tokens.py.

DESIGN NOTES FOR EXTRACTION:
- PDF generation is a background task
- When Celery is added: run in Celery worker
- When adding web API: POST /api/reports/generate → returns download URL
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.logging import get_logger
from services.reporting.models import (
    GeneratedReport,
    ReportSection,
    ReportTemplate,
    SectionType,
)
from styles.design_tokens import AMPYR_TEAL, AMPYR_TEAL_LIGHT, STATUS_COLORS

logger = get_logger("reporting.pdf")

# ── Brand colours for ReportLab ──────────────────────────────────────
RL_TEAL = colors.HexColor(AMPYR_TEAL)
RL_TEAL_LIGHT = colors.HexColor(AMPYR_TEAL_LIGHT)
RL_WHITE = colors.white
RL_GRAY = colors.HexColor("#F8F9FA")
RL_TEXT = colors.HexColor("#2C3E50")
RL_BORDER = colors.HexColor("#E8E8E8")
RL_MUTED = colors.HexColor("#7F8C8D")
RL_CONFIDENTIAL = colors.HexColor("#95A5A6")

# Map status names → ReportLab colours
_STATUS_RL: dict[str, colors.HexColor] = {
    name: colors.HexColor(hex_val) for name, hex_val in STATUS_COLORS.items()
}


class PDFRenderer:
    """Generate branded PDF reports."""

    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._styles = self._create_styles()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        template: ReportTemplate,
        data: dict[str, Any],
        filename: str | None = None,
    ) -> GeneratedReport:
        """Render a report template + data to PDF.

        Returns a :class:`GeneratedReport` with ``file_path`` populated.
        """
        t0 = datetime.now(UTC)

        if filename is None:
            period = data.get("period_label", "report").replace(" ", "_")
            ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"{template.type.value}_{period}_{ts_str}.pdf"

        filepath = self.output_dir / filename

        pagesize = landscape(A4) if template.orientation == "landscape" else A4
        page_width = pagesize[0]
        page_height = pagesize[1]

        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=pagesize,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )

        # Capture page dimensions for header/footer callback
        self._page_width = page_width
        self._page_height = page_height

        # Build flowable elements from sections
        elements: list[Any] = []

        for section in template.sections:
            if section.page_break_before and elements:
                elements.append(PageBreak())

            section_key = f"{section.type.value}_{section.title}".replace(" ", "_").lower()
            section_data = data.get(section_key, {})

            section_elements = self._render_section(section, section_data, data)
            elements.extend(section_elements)

        if not elements:
            elements.append(Paragraph("No report content generated.", self._styles["body"]))

        # Build PDF with branded header/footer
        doc.build(
            elements,
            onFirstPage=self._header_footer,
            onLaterPages=self._header_footer,
        )

        file_size = filepath.stat().st_size
        duration = (datetime.now(UTC) - t0).total_seconds()

        logger.info(
            "report_generated",
            template=template.name,
            filepath=str(filepath),
            size_bytes=file_size,
            seconds=round(duration, 2),
        )

        return GeneratedReport(
            template_id=template.id,
            template_name=template.name,
            report_type=template.type,
            period_start=data.get("period_start", datetime.now(UTC)),
            period_end=data.get("period_end", datetime.now(UTC)),
            period_label=data.get("period_label", ""),
            file_path=str(filepath),
            file_size_bytes=file_size,
            status="complete",
            generated_at=datetime.now(UTC),
            generation_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Section dispatch
    # ------------------------------------------------------------------

    def _render_section(
        self,
        section: ReportSection,
        section_data: dict[str, Any],
        all_data: dict[str, Any],
    ) -> list[Any]:
        """Render a single section to ReportLab flowables."""
        renderer_map = {
            SectionType.COVER: self._render_cover,
            SectionType.KPI_SUMMARY: self._render_kpi_summary,
            SectionType.GENERATION_TABLE: self._render_generation_table,
            SectionType.PR_CHART: self._render_chart_image,
            SectionType.GENERATION_CHART: self._render_chart_image,
            SectionType.WATERFALL: self._render_chart_image,
            SectionType.ALERT_SUMMARY: self._render_alert_summary,
            SectionType.TICKET_SUMMARY: self._render_ticket_summary,
            SectionType.PLANT_DETAIL: self._render_plant_detail,
            SectionType.APPENDIX: self._render_appendix,
            SectionType.TEXT: self._render_text,
        }

        renderer = renderer_map.get(section.type)
        if renderer is None:
            return [Paragraph(f"[Unknown section: {section.type.value}]", self._styles["body"])]

        # Cover receives all_data; everything else receives section_data
        if section.type == SectionType.COVER:
            return renderer(all_data)  # type: ignore[arg-type]
        if section.type in (SectionType.PR_CHART, SectionType.GENERATION_CHART, SectionType.WATERFALL):
            return self._render_chart_image(section, section_data)
        return renderer(section_data)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Individual section renderers
    # ------------------------------------------------------------------

    def _render_cover(self, data: dict[str, Any]) -> list[Any]:
        """Render branded cover page."""
        generated_at = data.get("generated_at", datetime.now(UTC))
        if hasattr(generated_at, "strftime"):
            ts_label = generated_at.strftime("%d %B %Y %H:%M")
        else:
            ts_label = str(generated_at)

        return [
            Spacer(1, 6 * cm),
            Paragraph("AMPYR Solar Portfolio Manager", self._styles["title"]),
            Spacer(1, 1 * cm),
            Paragraph(data.get("period_label", "Report"), self._styles["subtitle"]),
            Spacer(1, 2 * cm),
            Paragraph(f"Generated: {ts_label}", self._styles["body_center"]),
            Spacer(1, 1 * cm),
            Paragraph("CONFIDENTIAL", self._styles["confidential"]),
            PageBreak(),
        ]

    def _render_kpi_summary(self, data: dict[str, Any]) -> list[Any]:
        """Render KPI summary as a table row."""
        elements: list[Any] = [
            Paragraph("Executive Summary", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        kpi_data = [
            ["Total Capacity", "Generation", "Fleet PR", "Plants"],
            [
                f"{data.get('total_capacity_mwp', 0):.1f} MWp",
                f"{data.get('total_generation_mwh', 0):.1f} MWh",
                f"{data.get('fleet_pr_pct', 0):.1f}%",
                str(data.get("plant_count", 0)),
            ],
        ]

        table = Table(kpi_data, colWidths=[4 * cm] * 4)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), RL_TEAL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("FONTSIZE", (0, 1), (-1, 1), 14),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, RL_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 1 * cm))
        return elements

    def _render_generation_table(self, data: dict[str, Any]) -> list[Any]:
        """Render plant generation table with alternating row colours."""
        elements: list[Any] = [
            Paragraph("Portfolio Generation", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        plants = data.get("plants", [])
        if not plants:
            elements.append(Paragraph("No plant data available.", self._styles["body"]))
            return elements

        header = ["Plant", "Status", "PR (%)", "Generation (MWh)", "Alerts"]
        rows: list[list[str]] = [header]
        for p in plants:
            rows.append(
                [
                    str(p.get("name", "")),
                    str(p.get("status", "")).title(),
                    f"{p.get('pr', 0) or 0:.1f}",
                    f"{p.get('generation_mwh', 0) or 0:.1f}",
                    str(p.get("alerts", 0)),
                ]
            )

        table = Table(rows, colWidths=[5 * cm, 2.5 * cm, 2.5 * cm, 3.5 * cm, 2 * cm])
        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), RL_TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [RL_WHITE, RL_GRAY]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, RL_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]
        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 1 * cm))
        return elements

    def _render_chart_image(
        self, section: ReportSection, data: dict[str, Any]
    ) -> list[Any]:
        """Render a chart as an embedded image."""
        elements: list[Any] = [
            Paragraph(section.title, self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        image_path = data.get("image_path")
        if image_path and os.path.exists(image_path):
            img = Image(image_path, width=16 * cm, height=8 * cm)
            img.hAlign = "CENTER"
            elements.append(img)
        else:
            elements.append(
                Paragraph("Chart not available.", self._styles["body_muted"])
            )

        elements.append(Spacer(1, 0.5 * cm))
        return elements

    def _render_alert_summary(self, data: dict[str, Any]) -> list[Any]:
        """Render alerts & incidents."""
        elements: list[Any] = [
            Paragraph("Alerts &amp; Incidents", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        alerts = data.get("alerts", [])
        if not alerts:
            elements.append(
                Paragraph("No alerts during this period.", self._styles["body"])
            )
            return elements

        for alert in alerts:
            severity = alert.get("severity", "info")
            icon = {"critical": "\u25cf", "warning": "\u25b2"}.get(severity, "\u25cb")
            text = f"{icon} {alert.get('count', 0)} × {alert.get('type', 'Unknown')}"
            elements.append(Paragraph(text, self._styles["body"]))

        elements.append(Spacer(1, 0.5 * cm))
        return elements

    def _render_ticket_summary(self, data: dict[str, Any]) -> list[Any]:
        """Render ticket / O&M summary."""
        elements: list[Any] = [
            Paragraph("Ticket Summary", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        tickets = data.get("tickets", [])
        if not tickets:
            elements.append(
                Paragraph("No tickets during this period.", self._styles["body"])
            )
            return elements

        header = ["ID", "Plant", "Category", "Status", "Created"]
        rows: list[list[str]] = [header]
        for t in tickets[:20]:  # cap at 20 rows
            rows.append(
                [
                    str(t.get("id", "")),
                    str(t.get("plant", "")),
                    str(t.get("category", "")),
                    str(t.get("status", "")),
                    str(t.get("created_at", "")),
                ]
            )

        table = Table(rows, colWidths=[2 * cm, 4 * cm, 3.5 * cm, 2.5 * cm, 3 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), RL_TEAL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [RL_WHITE, RL_GRAY]),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, RL_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))
        return elements

    def _render_plant_detail(self, data: dict[str, Any]) -> list[Any]:
        """Render per-plant detail cards."""
        elements: list[Any] = [
            Paragraph("Plant Detail", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]

        plants = data.get("plants", [])
        if not plants:
            elements.append(
                Paragraph("No plant detail available.", self._styles["body"])
            )
            return elements

        for p in plants:
            name = p.get("name", p.get("uid", "Unknown"))
            elements.append(Paragraph(name, self._styles["subheading"]))
            details = (
                f"Status: {p.get('status', 'N/A').title()} &nbsp;|&nbsp; "
                f"PR: {p.get('pr', 0) or 0:.1f}% &nbsp;|&nbsp; "
                f"Generation: {p.get('generation_mwh', 0) or 0:.1f} MWh &nbsp;|&nbsp; "
                f"Capacity: {p.get('capacity_kw', 0) or 0:.0f} kW"
            )
            elements.append(Paragraph(details, self._styles["body"]))
            elements.append(Spacer(1, 0.3 * cm))

        return elements

    def _render_appendix(self, data: dict[str, Any]) -> list[Any]:
        """Render appendix text block."""
        elements: list[Any] = [
            Paragraph("Appendix", self._styles["heading"]),
            Spacer(1, 0.3 * cm),
        ]
        text = data.get("text", "")
        if text:
            elements.append(Paragraph(text, self._styles["body"]))
        else:
            elements.append(Paragraph("No appendix content.", self._styles["body_muted"]))
        elements.append(Spacer(1, 0.5 * cm))
        return elements

    def _render_text(self, data: dict[str, Any]) -> list[Any]:
        """Render a free-text section."""
        text = data.get("text", "")
        return [Paragraph(text, self._styles["body"]), Spacer(1, 0.5 * cm)]

    # ------------------------------------------------------------------
    # Header / footer
    # ------------------------------------------------------------------

    def _header_footer(self, canvas: Any, doc: Any) -> None:
        """Add branded header line and footer to every page."""
        canvas.saveState()

        w = self._page_width
        h = self._page_height

        # Header line
        canvas.setStrokeColor(RL_TEAL)
        canvas.setLineWidth(2)
        canvas.line(2 * cm, h - 1.5 * cm, w - 2 * cm, h - 1.5 * cm)

        # Header text (small, right-aligned)
        canvas.setFillColor(RL_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(w - 2 * cm, h - 1.3 * cm, "AMPYR Solar Portfolio Manager")

        # Footer
        canvas.setFillColor(RL_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 1 * cm, "AMPYR Solar Portfolio Manager — Confidential")
        canvas.drawRightString(w - 2 * cm, 1 * cm, f"Page {doc.page}")

        canvas.restoreState()

    # ------------------------------------------------------------------
    # Style factory
    # ------------------------------------------------------------------

    def _create_styles(self) -> dict[str, ParagraphStyle]:
        """Create brand-styled paragraph styles."""
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "BrandTitle",
                parent=base["Title"],
                fontSize=28,
                textColor=RL_TEAL,
                alignment=TA_CENTER,
                spaceAfter=12,
            ),
            "subtitle": ParagraphStyle(
                "BrandSubtitle",
                parent=base["Title"],
                fontSize=18,
                textColor=RL_TEXT,
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
            "heading": ParagraphStyle(
                "BrandHeading",
                parent=base["Heading1"],
                fontSize=16,
                textColor=RL_TEAL,
                spaceAfter=6,
                spaceBefore=12,
            ),
            "subheading": ParagraphStyle(
                "BrandSubheading",
                parent=base["Heading2"],
                fontSize=12,
                textColor=RL_TEAL,
                spaceAfter=4,
                spaceBefore=8,
            ),
            "body": ParagraphStyle(
                "BrandBody",
                parent=base["Normal"],
                fontSize=10,
                textColor=RL_TEXT,
                leading=14,
            ),
            "body_center": ParagraphStyle(
                "BrandBodyCenter",
                parent=base["Normal"],
                fontSize=10,
                textColor=RL_TEXT,
                alignment=TA_CENTER,
            ),
            "body_muted": ParagraphStyle(
                "BrandBodyMuted",
                parent=base["Normal"],
                fontSize=10,
                textColor=RL_MUTED,
                leading=14,
            ),
            "confidential": ParagraphStyle(
                "Confidential",
                parent=base["Normal"],
                fontSize=9,
                textColor=RL_CONFIDENTIAL,
                alignment=TA_CENTER,
            ),
        }
