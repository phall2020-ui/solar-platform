"""Tests for Phase 4 alert engine and ticketing flow."""

from __future__ import annotations

from solar_platform.alerts import AlertEngine, AlertRepository, AlertStateMachine, AlertStatus, TicketService, TicketStatus


def test_alert_engine_seeds_and_evaluates(seeded_engine):
    repo = AlertRepository(engine=seeded_engine)
    engine = AlertEngine(db_engine=seeded_engine, repository=repo)

    inserted = engine.seed_default_rules()
    assert inserted >= 1

    triggered = engine.evaluate_all()
    assert len(triggered) >= 1

    active = repo.list_alerts(status=AlertStatus.ACTIVE)
    assert len(active) >= 1


def test_alert_lifecycle_actions(seeded_engine):
    repo = AlertRepository(engine=seeded_engine)
    engine = AlertEngine(db_engine=seeded_engine, repository=repo)
    engine.seed_default_rules()
    triggered = engine.evaluate_all()
    alert = triggered[0]

    sm = AlertStateMachine(repository=repo)
    assert sm.acknowledge(alert.id, user="tester")
    assert repo.get_alert(alert.id).status == AlertStatus.ACKNOWLEDGED

    assert sm.resolve(alert.id, user="tester")
    assert repo.get_alert(alert.id).status == AlertStatus.RESOLVED


def test_ticket_service_transition_rules(seeded_engine):
    repo = AlertRepository(engine=seeded_engine)
    tickets = TicketService(repository=repo)

    ticket = tickets.create_ticket(
        plant_uid="uid-001",
        title="Investigate PR drop",
        description="PR fell below threshold",
        created_by="tester",
    )
    assert ticket.status.value == "open"

    progressed = tickets.transition(ticket.id, TicketStatus.IN_PROGRESS)
    assert progressed is not None
    assert progressed.status == TicketStatus.IN_PROGRESS

    resolved = tickets.transition(ticket.id, TicketStatus.RESOLVED)
    assert resolved is not None
    assert resolved.status == TicketStatus.RESOLVED

    closed = tickets.transition(ticket.id, TicketStatus.CLOSED)
    assert closed is not None
    assert closed.status == TicketStatus.CLOSED
