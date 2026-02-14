"""Report scheduling and orchestration.

Defines cron schedules for automated report generation (ready for Celery
Beat) and provides a :class:`ReportScheduler` that orchestrates the full
pipeline::

    DataFetcher → ChartExporter → PDFRenderer → ReportLibrary.save()
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from services.logging import get_logger
from services.reporting.chart_exporter import chart_to_png, cleanup_temp_images
from services.reporting.data_fetcher import ReportDataFetcher
from services.reporting.models import GeneratedReport, ReportTemplate, SectionType
from services.reporting.pdf_renderer import PDFRenderer
from services.reporting.report_library import ReportLibrary
from services.reporting.templates import ALL_TEMPLATES, get_template

logger = get_logger("reporting.scheduler")

# ── Cron schedules (ready for Celery Beat) ────────────────────────────

REPORT_SCHEDULES: dict[str, dict[str, str]] = {
    "monthly_performance": {
        "template": "monthly_performance",
        "cron": "0 8 1 * *",  # 1st of each month at 08:00
        "description": "Auto-generate monthly performance report",
    },
    "excom_monthly": {
        "template": "excom_summary",
        "cron": "0 8 2 * *",  # 2nd of each month at 08:00
        "description": "Auto-generate ExCom summary report",
    },
    "om_monthly": {
        "template": "om_report",
        "cron": "0 8 3 * *",  # 3rd of each month at 08:00
        "description": "Auto-generate O&M report",
    },
}

# Temporary chart image directory
_CHART_TMP_DIR = Path("reports/tmp")


class ReportScheduler:
    """Orchestrate report generation end-to-end.

    This is the main entry point for both manual "Generate Now" actions
    and future automated (Celery) tasks.
    """

    def __init__(self, output_dir: str = "reports") -> None:
        self._fetcher = ReportDataFetcher()
        self._renderer = PDFRenderer(output_dir=output_dir)
        self._library = ReportLibrary()
        self._output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_now(
        self,
        template_name: str,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None = None,
        generated_by: str = "",
    ) -> GeneratedReport:
        """Generate a report synchronously and save it to the library.

        Parameters
        ----------
        template_name:
            Key in :data:`ALL_TEMPLATES` (e.g. ``"monthly_performance"``).
        start:
            Reporting period start.
        end:
            Reporting period end.
        plant_uids:
            Restrict to specific plants. ``None`` = all plants.
        generated_by:
            Username or identifier of whoever triggered the report.

        Returns
        -------
        GeneratedReport
            The completed report record (also persisted in the library).

        Raises
        ------
        ValueError
            If *template_name* is not found.
        """
        template = get_template(template_name)
        if template is None:
            raise ValueError(f"Unknown template: {template_name!r}")

        logger.info(
            "report_generation_started",
            template=template.name,
            start=str(start),
            end=str(end),
            plants=plant_uids,
        )

        t0 = datetime.now(UTC)

        # 1. Fetch data
        data = self._fetcher.fetch_all(template, start, end, plant_uids)

        # 2. Export chart images (for sections that produce Plotly figures)
        self._export_charts(template, data)

        # 3. Render PDF
        report = self._renderer.render(template, data)

        # 4. Enrich report metadata
        report.plant_uids = plant_uids or []
        report.generated_by = generated_by
        report.generation_seconds = (datetime.now(UTC) - t0).total_seconds()

        # 5. Persist to library
        self._library.save(report)

        # 6. Cleanup temp chart images
        cleanup_temp_images(_CHART_TMP_DIR)

        logger.info(
            "report_generation_complete",
            report_id=report.id,
            filepath=report.file_path,
            seconds=round(report.generation_seconds, 2),
        )

        return report

    def list_schedules(self) -> dict[str, dict[str, str]]:
        """Return the configured report schedules."""
        return REPORT_SCHEDULES

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _export_charts(
        self, template: ReportTemplate, data: dict[str, Any]
    ) -> None:
        """Generate chart PNGs for chart-type sections and inject paths into *data*.

        If section data contains a ``"timeseries"`` or ``"trend"`` key we
        attempt to build a simple Plotly chart and export it.
        """
        _CHART_TMP_DIR.mkdir(parents=True, exist_ok=True)
        chart_sections = {
            SectionType.PR_CHART,
            SectionType.GENERATION_CHART,
            SectionType.WATERFALL,
        }

        for section in template.sections:
            if section.type not in chart_sections:
                continue

            section_key = f"{section.type.value}_{section.title}".replace(" ", "_").lower()
            section_data = data.get(section_key)
            if not section_data or isinstance(section_data, str):
                continue
            if section_data.get("error"):
                continue

            try:
                fig = self._build_chart(section, section_data)
                if fig is not None:
                    img_path = _CHART_TMP_DIR / f"{section_key}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.png"
                    chart_to_png(fig, img_path)
                    section_data["image_path"] = str(img_path)
            except Exception as exc:
                logger.warning(
                    "chart_generation_failed",
                    section=section.title,
                    error=str(exc),
                )

    @staticmethod
    def _build_chart(
        section: Any, section_data: dict[str, Any]
    ) -> go.Figure | None:
        """Build a simple Plotly figure from section data."""
        import plotly.graph_objects as go

        if section.type == SectionType.PR_CHART:
            ts = section_data.get("timeseries", [])
            if not ts:
                return None
            # timeseries may be a list of dicts
            dates = [r.get("date") or r.get("timestamp") for r in ts]
            values = [r.get("pr") or r.get("performance_ratio", 0) for r in ts]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=values, mode="lines+markers", name="PR (%)"))
            fig.update_layout(
                title=section.title,
                xaxis_title="Date",
                yaxis_title="Performance Ratio (%)",
                template="plotly_white",
            )
            return fig

        if section.type == SectionType.GENERATION_CHART:
            trend = section_data.get("trend", [])
            if not trend:
                return None
            dates = [r.get("date") for r in trend]
            values = [r.get("generation_mwh", 0) for r in trend]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=dates, y=values, name="Generation (MWh)"))
            fig.update_layout(
                title=section.title,
                xaxis_title="Date",
                yaxis_title="Generation (MWh)",
                template="plotly_white",
            )
            return fig

        if section.type == SectionType.WATERFALL:
            losses = section_data.get("losses", {})
            if not losses:
                return None
            labels = list(losses.keys())
            values = list(losses.values())
            fig = go.Figure()
            fig.add_trace(
                go.Waterfall(
                    x=labels,
                    y=values,
                    connector={"line": {"color": "rgb(63, 63, 63)"}},
                )
            )
            fig.update_layout(
                title=section.title,
                yaxis_title="Loss (%)",
                template="plotly_white",
            )
            return fig

        return None
