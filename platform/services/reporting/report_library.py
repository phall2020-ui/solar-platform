"""Report library — stores and retrieves GeneratedReport records in DuckDB.

Provides persistent storage for generated report metadata so users can
browse, download, or delete past reports from the UI.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.database import get_engine
from services.logging import get_logger
from services.reporting.models import GeneratedReport, ReportType

logger = get_logger("reporting.library")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generated_reports (
    id                  VARCHAR PRIMARY KEY,
    template_id         VARCHAR,
    template_name       VARCHAR,
    report_type         VARCHAR,
    period_start        TIMESTAMP,
    period_end          TIMESTAMP,
    period_label        VARCHAR,
    plant_uids          VARCHAR,
    file_path           VARCHAR,
    file_size_bytes     INTEGER,
    page_count          INTEGER DEFAULT 0,
    status              VARCHAR DEFAULT 'complete',
    error_message       VARCHAR DEFAULT '',
    generated_by        VARCHAR DEFAULT '',
    generated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generation_seconds  DOUBLE DEFAULT 0.0
);
"""


class ReportLibrary:
    """CRUD interface for the ``generated_reports`` table."""

    def __init__(self) -> None:
        self._engine = get_engine()
        self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, report: GeneratedReport) -> None:
        """Insert or update a generated report record."""
        data = {
            "id": report.id,
            "template_id": report.template_id,
            "template_name": report.template_name,
            "report_type": report.report_type.value,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "period_label": report.period_label,
            "plant_uids": ",".join(report.plant_uids) if report.plant_uids else "",
            "file_path": report.file_path,
            "file_size_bytes": report.file_size_bytes,
            "page_count": report.page_count,
            "status": report.status,
            "error_message": report.error_message,
            "generated_by": report.generated_by,
            "generated_at": report.generated_at,
            "generation_seconds": report.generation_seconds,
        }
        self._engine.execute_upsert("generated_reports", data, ["id"])
        logger.info("report_saved", report_id=report.id, template=report.template_name)

    def list_reports(
        self,
        report_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GeneratedReport]:
        """List generated reports with optional filters.

        Parameters
        ----------
        report_type:
            Filter by ``ReportType`` value (e.g. ``"monthly_performance"``).
        status:
            Filter by status (``"complete"``, ``"failed"``, etc.).
        limit:
            Maximum rows to return.
        offset:
            Pagination offset.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if report_type:
            conditions.append("report_type = ?")
            params.append(report_type)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            f"SELECT * FROM generated_reports{where} "
            f"ORDER BY generated_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        rows = self._engine.execute_df(sql, tuple(params))
        return [self._row_to_report(row) for _, row in rows.iterrows()]

    def get_by_id(self, report_id: str) -> GeneratedReport | None:
        """Fetch a single report by its ID."""
        rows = self._engine.execute(
            "SELECT * FROM generated_reports WHERE id = ?", (report_id,)
        )
        if not rows:
            return None

        # Get column names
        with self._engine.connection(read_only=True) as conn:
            cols = [
                desc[0]
                for desc in conn.execute(
                    "SELECT * FROM generated_reports LIMIT 0"
                ).description
            ]
        return self._dict_to_report(dict(zip(cols, rows[0])))

    def delete(self, report_id: str) -> bool:
        """Delete a report record (does **not** delete the PDF file).

        Returns ``True`` if a row was deleted.
        """
        # Check existence first
        existing = self.get_by_id(report_id)
        if existing is None:
            return False

        self._engine.execute(
            "DELETE FROM generated_reports WHERE id = ?", (report_id,)
        )
        logger.info("report_deleted", report_id=report_id)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create the ``generated_reports`` table if it doesn't exist."""
        if not self._engine.table_exists("generated_reports"):
            self._engine.execute(_CREATE_TABLE_SQL)
            logger.info("created_generated_reports_table")

    @staticmethod
    def _row_to_report(row: Any) -> GeneratedReport:
        """Convert a DataFrame row to a :class:`GeneratedReport`."""
        plant_uids_raw = row.get("plant_uids", "")
        plant_uids = [u for u in str(plant_uids_raw).split(",") if u] if plant_uids_raw else []

        return GeneratedReport(
            id=str(row["id"]),
            template_id=str(row.get("template_id", "")),
            template_name=str(row.get("template_name", "")),
            report_type=ReportType(row.get("report_type", "custom")),
            period_start=row.get("period_start", datetime.now(UTC)),
            period_end=row.get("period_end", datetime.now(UTC)),
            period_label=str(row.get("period_label", "")),
            plant_uids=plant_uids,
            file_path=str(row.get("file_path", "")),
            file_size_bytes=int(row.get("file_size_bytes", 0)),
            page_count=int(row.get("page_count", 0)),
            status=str(row.get("status", "complete")),
            error_message=str(row.get("error_message", "")),
            generated_by=str(row.get("generated_by", "")),
            generated_at=row.get("generated_at", datetime.now(UTC)),
            generation_seconds=float(row.get("generation_seconds", 0.0)),
        )

    @staticmethod
    def _dict_to_report(d: dict[str, Any]) -> GeneratedReport:
        """Convert a dict (from raw rows) to a :class:`GeneratedReport`."""
        plant_uids_raw = d.get("plant_uids", "")
        plant_uids = [u for u in str(plant_uids_raw).split(",") if u] if plant_uids_raw else []

        return GeneratedReport(
            id=str(d["id"]),
            template_id=str(d.get("template_id", "")),
            template_name=str(d.get("template_name", "")),
            report_type=ReportType(d.get("report_type", "custom")),
            period_start=d.get("period_start", datetime.now(UTC)),
            period_end=d.get("period_end", datetime.now(UTC)),
            period_label=str(d.get("period_label", "")),
            plant_uids=plant_uids,
            file_path=str(d.get("file_path", "")),
            file_size_bytes=int(d.get("file_size_bytes", 0)),
            page_count=int(d.get("page_count", 0)),
            status=str(d.get("status", "complete")),
            error_message=str(d.get("error_message", "")),
            generated_by=str(d.get("generated_by", "")),
            generated_at=d.get("generated_at", datetime.now(UTC)),
            generation_seconds=float(d.get("generation_seconds", 0.0)),
        )
