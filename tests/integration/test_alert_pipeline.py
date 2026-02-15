"""Integration tests for the alert pipeline: insert readings → evaluate alerts → verify."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

from solar_platform.alerts.models import Alert, AlertRule, AlertSeverity, AlertStatus, TicketPriority
from solar_platform.alerts.repository import AlertRepository
from solar_platform.alerts.ticketing import TicketService
from solar_platform.db.engine import DuckDBEngine


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def alert_engine_db(tmp_path):
    """Create a DuckDB engine with plants + readings for alert evaluation."""
    db_path = tmp_path / "alert_test.duckdb"
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
    conn.execute("""
        INSERT INTO plants VALUES
            ('uid-001', 'Sunny Acres', 5000, 4500, 51.5, -0.12, 30, 180, 'UTC')
    """)

    # Insert recent readings so alert engine can find them within evaluation window
    now = datetime.now(UTC)
    for i in range(10):
        ts = now - timedelta(minutes=i * 15)
        conn.execute(
            "INSERT INTO readings VALUES (?, 'uid-001', 'dev-1', ?, ?, ?, ?)",
            [ts, 100.0 + i, 500.0 + i * 10, 25.0, 45.0 + i],
        )

    conn.close()
    return DuckDBEngine(str(db_path))


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestAlertRepository:
    """Test AlertRepository CRUD against real DuckDB."""

    def test_ensure_tables_creates_alert_tables(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        tables = alert_engine_db.get_tables()
        assert "alerts" in tables
        assert "alert_rules" in tables
        assert "tickets" in tables

    def test_upsert_and_get_rule(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        rule = AlertRule(
            id="test-rule-1",
            name="Test Rule",
            metric="pr",
            condition="below",
            threshold=75.0,
            severity=AlertSeverity.WARNING,
        )
        repo.upsert_rule(rule)
        rules = repo.list_rules()
        assert any(r.id == "test-rule-1" for r in rules)

    def test_get_enabled_rules(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        enabled_rule = AlertRule(
            id="enabled-1", name="Enabled", metric="pr", condition="below",
            threshold=75.0, enabled=True,
        )
        disabled_rule = AlertRule(
            id="disabled-1", name="Disabled", metric="pr", condition="below",
            threshold=75.0, enabled=False,
        )
        repo.upsert_rule(enabled_rule)
        repo.upsert_rule(disabled_rule)
        enabled = repo.get_enabled_rules()
        ids = [r.id for r in enabled]
        assert "enabled-1" in ids
        assert "disabled-1" not in ids

    def test_create_and_get_alert(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        alert = Alert(
            id="alert-001",
            plant_uid="uid-001",
            rule_id="rule-001",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            metric_name="pr",
            metric_value=72.0,
            threshold_value=75.0,
        )
        repo.create_alert(alert)
        fetched = repo.get_alert("alert-001")
        assert fetched is not None
        assert fetched.title == "Test Alert"
        assert fetched.metric_value == 72.0

    def test_list_alerts_with_filters(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        for i in range(3):
            alert = Alert(
                id=f"alert-{i:03d}",
                plant_uid="uid-001",
                rule_id="rule-001",
                severity=AlertSeverity.WARNING if i < 2 else AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE if i < 2 else AlertStatus.RESOLVED,
                title=f"Alert {i}",
            )
            repo.create_alert(alert)

        active = repo.list_alerts(status=AlertStatus.ACTIVE)
        assert len(active) == 2
        critical = repo.list_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical) == 1

    def test_get_active_alert_by_rule(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        alert = Alert(
            plant_uid="uid-001",
            rule_id="rule-x",
            severity=AlertSeverity.WARNING,
            title="Active for rule-x",
            status=AlertStatus.ACTIVE,
        )
        repo.create_alert(alert)
        found = repo.get_active_alert_by_rule("uid-001", "rule-x")
        assert found is not None
        assert found.rule_id == "rule-x"

    def test_upsert_alert_updates_occurrence_count(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        alert = Alert(
            id="alert-upsert",
            plant_uid="uid-001",
            rule_id="rule-001",
            severity=AlertSeverity.WARNING,
            title="Upsert Test",
            occurrence_count=1,
        )
        repo.create_alert(alert)
        alert.occurrence_count = 5
        repo.upsert_alert(alert)
        fetched = repo.get_alert("alert-upsert")
        assert fetched.occurrence_count == 5


@pytest.mark.integration
class TestAlertPipeline:
    """Test the full alert pipeline: readings → evaluate → alerts."""

    def test_alert_engine_evaluates_no_data_rule(self, alert_engine_db):
        """When no readings exist for a plant, a no_data alert should trigger."""
        # Add a plant with no readings
        alert_engine_db.execute(
            "INSERT INTO plants VALUES ('uid-empty', 'Empty Plant', 1000, 900, 50, 0, 30, 180, 'UTC')"
        )

        # Import AlertEngine with mocked analysis engines to avoid broken dependencies
        with patch("solar_platform.alerts.engine.ClippingEngine"), \
             patch("solar_platform.alerts.engine.CurtailmentEngine"), \
             patch("solar_platform.alerts.engine.FoulingEngine"), \
             patch("solar_platform.alerts.engine.ThermalLossEngine"):
            from solar_platform.alerts.engine import AlertEngine
            engine = AlertEngine(db_engine=alert_engine_db)
            triggered = engine.evaluate_plant("uid-empty")

        # The no_data rule should fire for uid-empty
        no_data_alerts = [a for a in triggered if a.metric_name == "no_data"]
        assert len(no_data_alerts) > 0
        assert no_data_alerts[0].status == AlertStatus.ACTIVE


@pytest.mark.integration
class TestTicketService:
    """Test TicketService create/transition lifecycle."""

    def test_create_ticket_sets_due_date(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        svc = TicketService(repository=repo)
        ticket = svc.create_ticket(
            plant_uid="uid-001",
            title="Test Ticket",
            description="Something went wrong",
            priority=TicketPriority.HIGH,
            created_by="test",
        )
        assert ticket.due_at is not None
        assert ticket.due_at > ticket.created_at

    def test_ticket_transition_lifecycle(self, alert_engine_db):
        repo = AlertRepository(engine=alert_engine_db)
        svc = TicketService(repository=repo)
        ticket = svc.create_ticket(
            plant_uid="uid-001",
            title="Lifecycle Test",
            description="",
        )
        # Open → In Progress
        result = svc.transition(ticket.id, status=__import__("solar_platform.alerts.models", fromlist=["TicketStatus"]).TicketStatus.IN_PROGRESS)
        assert result is not None

    def test_invalid_transition_raises(self, alert_engine_db):
        from solar_platform.alerts.models import TicketStatus

        repo = AlertRepository(engine=alert_engine_db)
        svc = TicketService(repository=repo)
        ticket = svc.create_ticket(
            plant_uid="uid-001",
            title="Bad Transition",
            description="",
        )
        # Resolve first
        svc.transition(ticket.id, TicketStatus.RESOLVED, notes="done")
        # Closed → Resolved should fail
        svc.transition(ticket.id, TicketStatus.CLOSED)
        with pytest.raises(ValueError, match="Invalid ticket transition"):
            svc.transition(ticket.id, TicketStatus.OPEN)
