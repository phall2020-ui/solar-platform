"""E2E test for full alert flow: create rules → evaluate → create tickets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import duckdb
import pytest

from solar_platform.alerts.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from solar_platform.alerts.repository import AlertRepository
from solar_platform.alerts.ticketing import TicketService, SLA_HOURS_BY_PRIORITY
from solar_platform.db.engine import DuckDBEngine


# ── Fixture ──────────────────────────────────────────────────────────────


@pytest.fixture
def alert_db(tmp_path):
    """DuckDB engine pre-seeded for alert E2E tests."""
    db_path = tmp_path / "alert_e2e.duckdb"
    conn = duckdb.connect(str(db_path))

    conn.execute("""
        CREATE TABLE plants (
            plant_uid VARCHAR PRIMARY KEY,
            alias VARCHAR,
            dc_size_kw DOUBLE,
            ac_size_kw DOUBLE,
            latitude DOUBLE,
            longitude DOUBLE,
            tilt DOUBLE,
            azimuth DOUBLE,
            timezone VARCHAR DEFAULT 'UTC'
        )
    """)
    conn.execute("""
        CREATE TABLE readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            apparentPower_value DOUBLE,
            poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE,
            moduleTemperature_value DOUBLE
        )
    """)

    # Two plants
    conn.execute("""
        INSERT INTO plants VALUES
            ('uid-001', 'Plant A', 5000, 4500, 51.5, -0.12, 30, 180, 'UTC'),
            ('uid-002', 'Plant B', 8000, 7200, 52.0, -1.5, 25, 190, 'UTC')
    """)

    # Insert recent readings for uid-001 only — uid-002 has NO DATA
    now = datetime.now(UTC)
    for i in range(8):
        ts = now - timedelta(minutes=i * 15)
        conn.execute(
            "INSERT INTO readings VALUES (?, 'uid-001', 'dev-1', ?, ?, ?, ?)",
            [ts, 3000.0 + i * 100, 800.0, 22.0, 35.0],
        )

    conn.close()
    return DuckDBEngine(str(db_path))


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestFullAlertFlow:
    """E2E: create rules → evaluate alerts → verify lifecycle."""

    def test_rule_creation_and_retrieval(self, alert_db):
        repo = AlertRepository(engine=alert_db)
        rule = AlertRule(
            id="e2e-rule-pr",
            name="E2E Low PR",
            metric="pr",
            condition="below",
            threshold=75.0,
            severity=AlertSeverity.WARNING,
            auto_create_ticket=True,
            ticket_priority="high",
        )
        repo.upsert_rule(rule)
        rules = repo.list_rules()
        assert any(r.id == "e2e-rule-pr" for r in rules)

    def test_alert_lifecycle_acknowledge_resolve(self, alert_db):
        repo = AlertRepository(engine=alert_db)
        alert = Alert(
            id="e2e-lifecycle",
            plant_uid="uid-001",
            rule_id="rule-test",
            severity=AlertSeverity.WARNING,
            title="E2E Lifecycle Alert",
        )
        repo.create_alert(alert)

        # Acknowledge
        alert.acknowledge("operator@test.com")
        repo.upsert_alert(alert)
        fetched = repo.get_alert("e2e-lifecycle")
        assert fetched.status == AlertStatus.ACKNOWLEDGED
        assert fetched.acknowledged_by == "operator@test.com"

        # Resolve
        alert.resolve("operator@test.com")
        repo.upsert_alert(alert)
        fetched = repo.get_alert("e2e-lifecycle")
        assert fetched.status == AlertStatus.RESOLVED
        assert fetched.resolved_by == "operator@test.com"

    def test_ticket_creation_from_alert(self, alert_db):
        repo = AlertRepository(engine=alert_db)
        svc = TicketService(repository=repo)

        # Create alert
        alert = Alert(
            id="e2e-alert-ticket",
            plant_uid="uid-001",
            rule_id="rule-pr",
            severity=AlertSeverity.WARNING,
            title="PR dropped",
            metric_name="pr",
            metric_value=68.0,
        )
        repo.create_alert(alert)

        # Create ticket from alert
        ticket = svc.create_ticket(
            plant_uid="uid-001",
            title=f"PR dropped | uid-001",
            description="Performance ratio below threshold",
            priority=TicketPriority.HIGH,
            alert_id=alert.id,
            created_by="alert_engine",
        )
        assert ticket.alert_id == alert.id
        assert ticket.priority == TicketPriority.HIGH
        assert ticket.due_at is not None

        # SLA check
        expected_hours = SLA_HOURS_BY_PRIORITY[TicketPriority.HIGH]
        delta = ticket.due_at - ticket.created_at
        assert abs(delta.total_seconds() / 3600 - expected_hours) < 1.0

    def test_ticket_full_lifecycle(self, alert_db):
        repo = AlertRepository(engine=alert_db)
        svc = TicketService(repository=repo)

        ticket = svc.create_ticket(
            plant_uid="uid-001",
            title="Full lifecycle",
            description="Test",
        )
        assert ticket.status == TicketStatus.OPEN

        # Open → In Progress
        t = svc.transition(ticket.id, TicketStatus.IN_PROGRESS)
        assert t.status == TicketStatus.IN_PROGRESS

        # In Progress → Resolved
        t = svc.transition(ticket.id, TicketStatus.RESOLVED, notes="Fixed")
        assert t.status == TicketStatus.RESOLVED
        assert t.resolution_notes == "Fixed"

        # Resolved → Closed
        t = svc.transition(ticket.id, TicketStatus.CLOSED)
        assert t.status == TicketStatus.CLOSED

    def test_alert_engine_no_data_rule(self, alert_db):
        """Full E2E: AlertEngine evaluates no_data rule for plant with no readings."""
        with patch("solar_platform.alerts.engine.ClippingEngine"), \
             patch("solar_platform.alerts.engine.CurtailmentEngine"), \
             patch("solar_platform.alerts.engine.FoulingEngine"), \
             patch("solar_platform.alerts.engine.ThermalLossEngine"):
            from solar_platform.alerts.engine import AlertEngine
            engine = AlertEngine(db_engine=alert_db)
            # uid-002 has no readings
            triggered = engine.evaluate_plant("uid-002")

        no_data = [a for a in triggered if a.metric_name == "no_data"]
        assert len(no_data) >= 1
        assert all(a.status == AlertStatus.ACTIVE for a in no_data)

    def test_alert_model_properties(self):
        alert = Alert(
            plant_uid="uid-001",
            rule_id="rule-1",
            severity=AlertSeverity.CRITICAL,
            title="Test",
        )
        assert alert.is_active
        assert alert.duration_hours >= 0
        alert.suppress()
        assert alert.status == AlertStatus.SUPPRESSED
        assert not alert.is_active
