"""Framework-agnostic alert and alert-rule models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """Severity levels for generated alerts."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    """Lifecycle statuses for alerts."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class Alert(BaseModel):
    """Alert instance generated from a rule evaluation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plant_uid: str
    rule_id: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    title: str
    description: str = ""
    metric_name: str = ""
    metric_value: float | None = None
    threshold_value: float | None = None
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_by: str | None = None
    ticket_id: str | None = None
    occurrence_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    def acknowledge(self, user: str) -> None:
        """Move alert to acknowledged state."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = user

    def resolve(self, user: str) -> None:
        """Move alert to resolved state."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(UTC)
        self.resolved_by = user

    def suppress(self) -> None:
        """Suppress alert without resolving root cause."""
        self.status = AlertStatus.SUPPRESSED

    @property
    def duration_hours(self) -> float:
        """Duration from first_seen to now/resolution."""
        end = self.resolved_at or datetime.now(UTC)
        return (end - self.first_seen).total_seconds() / 3600

    @property
    def is_active(self) -> bool:
        """True while alert is still operationally open."""
        return self.status in (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


class AlertRule(BaseModel):
    """Rule configuration used by the alert engine."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True

    metric: str
    condition: str
    threshold: float = 0.0

    evaluation_window_minutes: int = 60
    min_consecutive_breaches: int = 1
    cooldown_minutes: int = 60

    applies_to: list[str] = Field(default_factory=list)

    auto_create_ticket: bool = False
    ticket_priority: str = "medium"
    ticket_assignee: str | None = None


class TicketPriority(str, Enum):
    """Ticket priority bands used for SLA calculations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    """Ticket lifecycle states."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Ticket(BaseModel):
    """Operational ticket generated from alert events."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_id: str | None = None
    plant_uid: str
    title: str
    description: str = ""
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.MEDIUM
    assignee: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    resolution_notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def assign(self, assignee: str) -> None:
        self.assignee = assignee
        self.updated_at = datetime.now(UTC)

    def set_status(self, status: TicketStatus) -> None:
        self.status = status
        self.updated_at = datetime.now(UTC)

    def resolve(self, notes: str = "") -> None:
        self.status = TicketStatus.RESOLVED
        self.resolved_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.resolution_notes = notes or self.resolution_notes

    def close(self) -> None:
        self.status = TicketStatus.CLOSED
        self.closed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
