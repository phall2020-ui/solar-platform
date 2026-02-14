"""Tests for alert model lifecycle and derived properties."""

from __future__ import annotations

from services.alerts.models import Alert, AlertSeverity, AlertStatus


def test_alert_lifecycle_transitions():
    alert = Alert(
        plant_uid="uid-001",
        rule_id="rule-low-pr",
        severity=AlertSeverity.WARNING,
        title="Performance ratio below threshold",
    )

    assert alert.status == AlertStatus.ACTIVE
    assert alert.is_active is True

    alert.acknowledge("operator@ampyr")
    assert alert.status == AlertStatus.ACKNOWLEDGED
    assert alert.acknowledged_by == "operator@ampyr"
    assert alert.acknowledged_at is not None

    alert.resolve("engineer@ampyr")
    assert alert.status == AlertStatus.RESOLVED
    assert alert.resolved_by == "engineer@ampyr"
    assert alert.resolved_at is not None
    assert alert.is_active is False


def test_alert_duration_hours_is_non_negative():
    alert = Alert(
        plant_uid="uid-001",
        rule_id="rule-comms-gap",
        severity=AlertSeverity.CRITICAL,
        title="Telemetry gap detected",
    )
    assert alert.duration_hours >= 0
