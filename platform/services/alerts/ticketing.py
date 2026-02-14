"""Ticket lifecycle and SLA utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.alerts.models import Ticket, TicketPriority, TicketStatus
from services.alerts.repository import AlertRepository


SLA_HOURS_BY_PRIORITY = {
    TicketPriority.LOW: 72,
    TicketPriority.MEDIUM: 48,
    TicketPriority.HIGH: 24,
    TicketPriority.CRITICAL: 8,
}


class TicketService:
    """Handle ticket creation and status transitions."""

    def __init__(self, repository: AlertRepository | None = None):
        self._repo = repository or AlertRepository()

    def create_ticket(
        self,
        *,
        plant_uid: str,
        title: str,
        description: str,
        priority: TicketPriority = TicketPriority.MEDIUM,
        alert_id: str | None = None,
        assignee: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> Ticket:
        created_at = datetime.now(UTC)
        due_at = created_at + timedelta(hours=SLA_HOURS_BY_PRIORITY[priority])
        ticket = Ticket(
            plant_uid=plant_uid,
            title=title,
            description=description,
            priority=priority,
            alert_id=alert_id,
            assignee=assignee,
            created_by=created_by,
            created_at=created_at,
            updated_at=created_at,
            due_at=due_at,
            metadata=metadata or {},
        )
        return self._repo.create_ticket(ticket)

    def transition(self, ticket_id: str, status: TicketStatus, notes: str = "") -> Ticket | None:
        ticket = self._repo.get_ticket(ticket_id)
        if not ticket:
            return None

        allowed = {
            TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.BLOCKED, TicketStatus.RESOLVED, TicketStatus.CLOSED},
            TicketStatus.IN_PROGRESS: {TicketStatus.BLOCKED, TicketStatus.RESOLVED, TicketStatus.CLOSED},
            TicketStatus.BLOCKED: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED},
            TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
            TicketStatus.CLOSED: {TicketStatus.IN_PROGRESS},
        }
        if status not in allowed.get(ticket.status, set()):
            raise ValueError(f"Invalid ticket transition: {ticket.status.value} -> {status.value}")

        if status == TicketStatus.RESOLVED:
            ticket.resolve(notes)
        elif status == TicketStatus.CLOSED:
            ticket.close()
        else:
            ticket.set_status(status)
        ticket.updated_at = datetime.now(UTC)
        return self._repo.upsert_ticket(ticket)

    def assign(self, ticket_id: str, assignee: str) -> Ticket | None:
        ticket = self._repo.get_ticket(ticket_id)
        if not ticket:
            return None
        ticket.assign(assignee)
        return self._repo.upsert_ticket(ticket)

    def list_tickets(self, status: TicketStatus | None = None) -> list[Ticket]:
        return self._repo.list_tickets(status=status)
