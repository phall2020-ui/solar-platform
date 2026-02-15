"""Report data fetcher — collects all data needed for report generation.

For each section type, fetches the required metrics/charts/tables
using the analysis engines and portfolio service.

This is the bridge between the report template and the data layer.
Fetched data is passed to the PDF renderer.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from solar_platform.services.logging import get_logger
from solar_platform.services.portfolio import PortfolioService
from solar_platform.reporting.models import ReportSection, ReportTemplate, SectionType

logger = get_logger("reporting.data_fetcher")

# Import analysis engines defensively — they may not all exist yet.
try:
    from solar_platform.analysis.clipping import ClippingEngine
except ImportError:
    ClippingEngine = None  # type: ignore[assignment,misc]

try:
    from solar_platform.analysis.curtailment import CurtailmentEngine
except ImportError:
    CurtailmentEngine = None  # type: ignore[assignment,misc]

try:
    from solar_platform.analysis.pr_trending import PRTrendingEngine
except ImportError:
    PRTrendingEngine = None  # type: ignore[assignment,misc]

try:
    from solar_platform.analysis.waterfall import LossWaterfallEngine
except ImportError:
    LossWaterfallEngine = None  # type: ignore[assignment,misc]

try:
    from solar_platform.analysis.degradation import DegradationEngine
except ImportError:
    DegradationEngine = None  # type: ignore[assignment,misc]

try:
    from solar_platform.alerts.repository import AlertRepository
except ImportError:
    AlertRepository = None  # type: ignore[assignment,misc]

try:
    from solar_platform.alerts.ticketing import TicketService
except ImportError:
    TicketService = None  # type: ignore[assignment,misc]


class ReportDataFetcher:
    """Fetch all data needed for a report template."""

    def __init__(self) -> None:
        self._portfolio = PortfolioService()

    def fetch_all(
        self,
        template: ReportTemplate,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch data for every section in *template*.

        Returns a dict keyed by a normalised section key. Metadata keys
        (``period_start``, ``period_end``, ``period_label``, ``generated_at``)
        are always present.
        """
        data: dict[str, Any] = {
            "period_start": start,
            "period_end": end,
            "period_label": start.strftime("%B %Y"),
            "generated_at": datetime.now(UTC),
        }

        for section in template.sections:
            section_key = self._section_key(section)
            try:
                section_data = self._fetch_section(section, start, end, plant_uids)
                data[section_key] = section_data
            except Exception as exc:
                logger.error(
                    "section_fetch_error",
                    section=section.title,
                    section_type=section.type.value,
                    error=str(exc),
                )
                data[section_key] = {"error": str(exc)}

        return data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _section_key(section: ReportSection) -> str:
        return f"{section.type.value}_{section.title}".replace(" ", "_").lower()

    def _fetch_section(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        """Dispatch to the correct handler based on *SectionType*."""
        handler = {
            SectionType.COVER: self._fetch_cover,
            SectionType.KPI_SUMMARY: self._fetch_kpi_summary,
            SectionType.GENERATION_TABLE: self._fetch_generation_table,
            SectionType.PR_CHART: self._fetch_pr_chart,
            SectionType.GENERATION_CHART: self._fetch_generation_chart,
            SectionType.WATERFALL: self._fetch_waterfall,
            SectionType.ALERT_SUMMARY: self._fetch_alert_summary,
            SectionType.TICKET_SUMMARY: self._fetch_ticket_summary,
            SectionType.PLANT_DETAIL: self._fetch_plant_detail,
            SectionType.APPENDIX: self._fetch_appendix,
            SectionType.TEXT: self._fetch_text,
        }.get(section.type)

        if handler is None:
            logger.warning("unknown_section_type", section_type=section.type.value)
            return {}

        return handler(section, start, end, plant_uids)

    # ── Section handlers ─────────────────────────────────────────────

    def _fetch_cover(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        """Cover needs no data beyond metadata already in the top-level dict."""
        return {"title": section.title or "AMPYR Solar Portfolio Manager"}

    def _fetch_kpi_summary(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        summary = self._portfolio.get_summary("Last 30 Days")
        return {
            "total_capacity_mwp": summary.total_capacity_mwp,
            "total_generation_mwh": summary.total_generation_mwh,
            "fleet_pr_pct": summary.fleet_pr_pct,
            "plant_count": summary.plant_count,
            "generation_delta_pct": summary.generation_delta_pct,
            "pr_delta_pct": summary.pr_delta_pct,
            "active_alerts": summary.active_alerts,
            "critical_alerts": summary.critical_alerts,
        }

    def _fetch_generation_table(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        plants = self._portfolio.get_plant_statuses("Last 30 Days")
        if plant_uids:
            plants = [p for p in plants if p.get("uid") in plant_uids]
        return {"plants": plants}

    def _fetch_pr_chart(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        if PRTrendingEngine is None:
            return {"error": "PRTrendingEngine not available"}

        uid = section.plant_uid or (plant_uids[0] if plant_uids else None)
        if not uid:
            return {"error": "No plant_uid specified for PR chart"}

        engine = PRTrendingEngine()
        result = engine.run(uid, start, end)
        ts_data: list[dict[str, Any]] = []
        if result.timeseries is not None and not result.timeseries.empty:
            ts_data = result.timeseries.to_dict(orient="records")
        return {"timeseries": ts_data, "summary": result.summary}

    def _fetch_generation_chart(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        trend = self._portfolio.get_generation_trend(days=(end - start).days or 30)
        return {"trend": trend}

    def _fetch_waterfall(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        if LossWaterfallEngine is None:
            return {"losses": {}}

        uid = section.plant_uid or (plant_uids[0] if plant_uids else None)
        if not uid:
            return {"losses": {}}

        engine = LossWaterfallEngine()
        result = engine.run(uid, start, end)
        return {"losses": result.losses, "summary": result.summary}

    def _fetch_alert_summary(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        alerts = self._portfolio.get_alert_summary()
        return {"alerts": alerts}

    def _fetch_ticket_summary(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        if TicketService is None:
            return {"tickets": [], "error": "TicketService not available"}
        try:
            svc = TicketService()
            tickets = svc.list_tickets() if hasattr(svc, "list_tickets") else []
            return {"tickets": tickets}
        except Exception as exc:
            logger.warning("ticket_fetch_failed", error=str(exc))
            return {"tickets": [], "error": str(exc)}

    def _fetch_plant_detail(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        uids = [section.plant_uid] if section.plant_uid else (plant_uids or [])
        details: list[dict[str, Any]] = []
        for uid in uids:
            statuses = self._portfolio.get_plant_statuses("Last 30 Days")
            plant_info = next((p for p in statuses if p.get("uid") == uid), None)
            if plant_info:
                details.append(plant_info)
        return {"plants": details}

    def _fetch_appendix(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        appendix_type = section.config.get("type", "generic")
        if appendix_type == "data_quality":
            return {
                "text": (
                    "Data quality assessment: readings are sourced from the monitoring "
                    "API. Gaps or anomalies are flagged automatically by the data-quality "
                    "engine. Refer to the Data Health dashboard for granular metrics."
                ),
            }
        if appendix_type == "methodology":
            return {
                "text": (
                    "Performance Ratio (PR) = Actual Energy / (POA Irradiance × "
                    "Capacity × Time). Generation values are meter-reported kWh "
                    "aggregated to the reporting period."
                ),
            }
        return {"text": section.config.get("text", "")}

    def _fetch_text(
        self,
        section: ReportSection,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        return {"text": section.config.get("text", "")}
