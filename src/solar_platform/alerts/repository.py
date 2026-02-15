"""Persistence layer for alert and alert-rule objects."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from solar_platform.alerts.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from solar_platform.db.repository import BaseRepository


class AlertRepository(BaseRepository):
    """DuckDB-backed repository for alerts and rule configuration."""

    def __init__(self, engine=None):
        super().__init__(engine=engine)
        # Creating tables requires a write lock. When the main DB is being written
        # by a long-running job (e.g. a backfill), DuckDB can refuse the lock.
        # The UI should still be able to render in read-only mode, so we treat
        # "ensure tables" as best-effort and degrade gracefully.
        try:
            self.ensure_tables()
        except Exception:
            # Do not fail initialization; list_* methods will fall back to empty
            # results when tables aren't available.
            pass

    def ensure_tables(self) -> None:
        """Create required alert tables and indexes when absent."""
        # Fast path: if tables already exist, avoid taking a write lock.
        try:
            if (
                self.engine.table_exists("alerts")
                and self.engine.table_exists("alert_rules")
                and self.engine.table_exists("tickets")
            ):
                return
        except Exception:
            # If introspection fails, fall back to attempting creation below.
            pass

        self.engine.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id VARCHAR PRIMARY KEY,
                plant_uid VARCHAR NOT NULL,
                rule_id VARCHAR NOT NULL,
                severity VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'active',
                title VARCHAR NOT NULL,
                description TEXT,
                metric_name VARCHAR,
                metric_value DOUBLE,
                threshold_value DOUBLE,
                first_seen TIMESTAMP NOT NULL,
                last_seen TIMESTAMP NOT NULL,
                acknowledged_at TIMESTAMP,
                resolved_at TIMESTAMP,
                acknowledged_by VARCHAR,
                resolved_by VARCHAR,
                ticket_id VARCHAR,
                occurrence_count INTEGER DEFAULT 1,
                metadata VARCHAR DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.engine.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_rules (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description TEXT,
                severity VARCHAR NOT NULL DEFAULT 'warning',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                metric VARCHAR NOT NULL,
                condition VARCHAR NOT NULL,
                threshold DOUBLE NOT NULL DEFAULT 0,
                evaluation_window_minutes INTEGER NOT NULL DEFAULT 60,
                min_consecutive_breaches INTEGER NOT NULL DEFAULT 1,
                cooldown_minutes INTEGER NOT NULL DEFAULT 60,
                applies_to VARCHAR DEFAULT '[]',
                auto_create_ticket BOOLEAN NOT NULL DEFAULT FALSE,
                ticket_priority VARCHAR NOT NULL DEFAULT 'medium',
                ticket_assignee VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.engine.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id VARCHAR PRIMARY KEY,
                alert_id VARCHAR,
                plant_uid VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                description TEXT,
                status VARCHAR NOT NULL DEFAULT 'open',
                priority VARCHAR NOT NULL DEFAULT 'medium',
                assignee VARCHAR,
                created_by VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_at TIMESTAMP,
                resolved_at TIMESTAMP,
                closed_at TIMESTAMP,
                resolution_notes TEXT,
                metadata VARCHAR DEFAULT '{}'
            )
            """
        )
        self.engine.execute("CREATE INDEX IF NOT EXISTS idx_alerts_plant ON alerts (plant_uid, status)")
        self.engine.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity, status)")
        self.engine.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules (enabled)")
        self.engine.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status, priority)")

    def create_alert(self, alert: Alert) -> Alert:
        """Insert a new alert row."""
        self.engine.execute_insert("alerts", self._alert_to_row(alert))
        return alert

    def upsert_alert(self, alert: Alert) -> Alert:
        """Insert or update an alert row."""
        self.engine.execute_upsert("alerts", self._alert_to_row(alert), conflict_columns=["id"])
        return alert

    def get_alert(self, alert_id: str) -> Alert | None:
        """Load a single alert by ID."""
        df = self.engine.execute_df("SELECT * FROM alerts WHERE id = ? LIMIT 1", (alert_id,))
        if df.empty:
            return None
        return self._record_to_alert(df.iloc[0].to_dict())

    def list_alerts(
        self,
        *,
        plant_uid: str | None = None,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        limit: int | None = None,
    ) -> list[Alert]:
        """Query alerts with optional filters."""
        # If tables are unavailable (e.g. DB locked during startup), treat as no alerts.
        try:
            if not self.engine.table_exists("alerts"):
                return []
        except Exception:
            return []

        conditions: list[str] = []
        params: list[Any] = []

        if plant_uid:
            conditions.append("plant_uid = ?")
            params.append(plant_uid)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if severity:
            conditions.append("severity = ?")
            params.append(severity.value)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM alerts{where} ORDER BY last_seen DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        try:
            df = self.engine.execute_df(sql, tuple(params) if params else None)
            return [self._record_to_alert(record) for record in df.to_dict(orient="records")]
        except Exception:
            return []

    def get_active_alert_by_rule(self, plant_uid: str, rule_id: str) -> Alert | None:
        """Return an active/acknowledged alert for a plant+rule if it exists."""
        df = self.engine.execute_df(
            """
            SELECT * FROM alerts
            WHERE plant_uid = ? AND rule_id = ? AND status IN ('active', 'acknowledged')
            ORDER BY last_seen DESC
            LIMIT 1
            """,
            (plant_uid, rule_id),
        )
        if df.empty:
            return None
        return self._record_to_alert(df.iloc[0].to_dict())

    def upsert_rule(self, rule: AlertRule) -> AlertRule:
        """Insert or update an alert rule."""
        self.engine.execute_upsert("alert_rules", self._rule_to_row(rule), conflict_columns=["id"])
        return rule

    def get_enabled_rules(self) -> list[AlertRule]:
        """Load all enabled rules."""
        df = self.engine.execute_df(
            "SELECT * FROM alert_rules WHERE enabled = TRUE ORDER BY name ASC"
        )
        return [self._record_to_rule(record) for record in df.to_dict(orient="records")]

    def list_rules(self) -> list[AlertRule]:
        """Load all rules regardless of enabled state."""
        df = self.engine.execute_df("SELECT * FROM alert_rules ORDER BY name ASC")
        return [self._record_to_rule(record) for record in df.to_dict(orient="records")]

    def create_ticket(self, ticket: Ticket) -> Ticket:
        """Insert a new ticket."""
        self.engine.execute_insert("tickets", self._ticket_to_row(ticket))
        return ticket

    def upsert_ticket(self, ticket: Ticket) -> Ticket:
        """Insert or update ticket."""
        self.engine.execute_upsert("tickets", self._ticket_to_row(ticket), conflict_columns=["id"])
        return ticket

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        """Load a ticket by id."""
        df = self.engine.execute_df("SELECT * FROM tickets WHERE id = ? LIMIT 1", (ticket_id,))
        if df.empty:
            return None
        return self._record_to_ticket(df.iloc[0].to_dict())

    def list_tickets(
        self,
        *,
        plant_uid: str | None = None,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        limit: int | None = None,
    ) -> list[Ticket]:
        """List tickets with optional filtering."""
        conditions: list[str] = []
        params: list[Any] = []
        if plant_uid:
            conditions.append("plant_uid = ?")
            params.append(plant_uid)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if priority:
            conditions.append("priority = ?")
            params.append(priority.value)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM tickets{where} ORDER BY updated_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        df = self.engine.execute_df(sql, tuple(params) if params else None)
        return [self._record_to_ticket(record) for record in df.to_dict(orient="records")]

    @staticmethod
    def _alert_to_row(alert: Alert) -> dict[str, Any]:
        row = alert.model_dump()
        row["severity"] = alert.severity.value
        row["status"] = alert.status.value
        row["metadata"] = json.dumps(alert.metadata, sort_keys=True)
        row["updated_at"] = datetime.now(UTC)
        return row

    @staticmethod
    def _rule_to_row(rule: AlertRule) -> dict[str, Any]:
        row = rule.model_dump()
        row["severity"] = rule.severity.value
        row["applies_to"] = json.dumps(rule.applies_to)
        row["updated_at"] = datetime.now(UTC)
        return row

    @staticmethod
    def _ticket_to_row(ticket: Ticket) -> dict[str, Any]:
        row = ticket.model_dump()
        row["status"] = ticket.status.value
        row["priority"] = ticket.priority.value
        row["metadata"] = json.dumps(ticket.metadata, sort_keys=True)
        row["updated_at"] = datetime.now(UTC)
        return row

    def _record_to_alert(self, record: dict[str, Any]) -> Alert:
        metadata_raw = self._coerce_str(record.get("metadata"), "{}")
        metadata = self._parse_json_dict(metadata_raw)
        return Alert(
            id=self._coerce_str(record.get("id")),
            plant_uid=self._coerce_str(record.get("plant_uid")),
            rule_id=self._coerce_str(record.get("rule_id")),
            severity=AlertSeverity(self._coerce_str(record.get("severity"))),
            status=AlertStatus(self._coerce_str(record.get("status"), AlertStatus.ACTIVE.value)),
            title=self._coerce_str(record.get("title")),
            description=self._coerce_str(record.get("description"), ""),
            metric_name=self._coerce_str(record.get("metric_name"), ""),
            metric_value=self._coerce_float(record.get("metric_value")),
            threshold_value=self._coerce_float(record.get("threshold_value")),
            first_seen=self._coerce_datetime(record.get("first_seen")) or datetime.now(UTC),
            last_seen=self._coerce_datetime(record.get("last_seen")) or datetime.now(UTC),
            acknowledged_at=self._coerce_datetime(record.get("acknowledged_at")),
            resolved_at=self._coerce_datetime(record.get("resolved_at")),
            acknowledged_by=self._coerce_optional_str(record.get("acknowledged_by")),
            resolved_by=self._coerce_optional_str(record.get("resolved_by")),
            ticket_id=self._coerce_optional_str(record.get("ticket_id")),
            occurrence_count=int(self._coerce_float(record.get("occurrence_count")) or 1),
            metadata=metadata,
        )

    def _record_to_rule(self, record: dict[str, Any]) -> AlertRule:
        applies_to_raw = self._coerce_str(record.get("applies_to"), "[]")
        applies_to = self._parse_json_list(applies_to_raw)
        return AlertRule(
            id=self._coerce_str(record.get("id")),
            name=self._coerce_str(record.get("name")),
            description=self._coerce_str(record.get("description"), ""),
            severity=AlertSeverity(self._coerce_str(record.get("severity"), AlertSeverity.WARNING.value)),
            enabled=bool(record.get("enabled", True)),
            metric=self._coerce_str(record.get("metric")),
            condition=self._coerce_str(record.get("condition")),
            threshold=float(self._coerce_float(record.get("threshold")) or 0.0),
            evaluation_window_minutes=int(
                self._coerce_float(record.get("evaluation_window_minutes")) or 60
            ),
            min_consecutive_breaches=int(
                self._coerce_float(record.get("min_consecutive_breaches")) or 1
            ),
            cooldown_minutes=int(self._coerce_float(record.get("cooldown_minutes")) or 60),
            applies_to=applies_to,
            auto_create_ticket=bool(record.get("auto_create_ticket", False)),
            ticket_priority=self._coerce_str(record.get("ticket_priority"), "medium"),
            ticket_assignee=self._coerce_optional_str(record.get("ticket_assignee")),
        )

    def _record_to_ticket(self, record: dict[str, Any]) -> Ticket:
        metadata_raw = self._coerce_str(record.get("metadata"), "{}")
        return Ticket(
            id=self._coerce_str(record.get("id")),
            alert_id=self._coerce_optional_str(record.get("alert_id")),
            plant_uid=self._coerce_str(record.get("plant_uid")),
            title=self._coerce_str(record.get("title")),
            description=self._coerce_str(record.get("description"), ""),
            status=TicketStatus(self._coerce_str(record.get("status"), TicketStatus.OPEN.value)),
            priority=TicketPriority(self._coerce_str(record.get("priority"), TicketPriority.MEDIUM.value)),
            assignee=self._coerce_optional_str(record.get("assignee")),
            created_by=self._coerce_optional_str(record.get("created_by")),
            created_at=self._coerce_datetime(record.get("created_at")) or datetime.now(UTC),
            updated_at=self._coerce_datetime(record.get("updated_at")) or datetime.now(UTC),
            due_at=self._coerce_datetime(record.get("due_at")),
            resolved_at=self._coerce_datetime(record.get("resolved_at")),
            closed_at=self._coerce_datetime(record.get("closed_at")),
            resolution_notes=self._coerce_str(record.get("resolution_notes"), ""),
            metadata=self._parse_json_dict(metadata_raw),
        )

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
        return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _coerce_optional_str(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        return str(value)

    @staticmethod
    def _coerce_str(value: Any, default: str = "") -> str:
        if value is None or pd.isna(value):
            return default
        return str(value)

    @staticmethod
    def _parse_json_dict(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _parse_json_list(raw: str) -> list[str]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
            return []
        except json.JSONDecodeError:
            return []
