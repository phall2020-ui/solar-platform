"""Tests for alert repository persistence and filters."""

from __future__ import annotations

from solar_platform.alerts.models import Alert, AlertRule, AlertSeverity, AlertStatus
from solar_platform.alerts.repository import AlertRepository


def test_alert_repository_creates_tables(test_engine):
    repo = AlertRepository(engine=test_engine)
    assert repo.engine.table_exists("alerts")
    assert repo.engine.table_exists("alert_rules")


def test_alert_repository_round_trip_and_filters(test_engine):
    repo = AlertRepository(engine=test_engine)

    alert_one = Alert(
        plant_uid="uid-001",
        rule_id="rule-low-pr",
        severity=AlertSeverity.CRITICAL,
        title="PR dropped below threshold",
        metric_name="pr",
        metric_value=61.2,
        threshold_value=75.0,
        metadata={"window": "24h"},
    )
    alert_two = Alert(
        plant_uid="uid-002",
        rule_id="rule-high-temp",
        severity=AlertSeverity.WARNING,
        title="High module temperature",
    )

    repo.create_alert(alert_one)
    repo.create_alert(alert_two)

    fetched = repo.get_alert(alert_one.id)
    assert fetched is not None
    assert fetched.metadata["window"] == "24h"
    assert fetched.status == AlertStatus.ACTIVE

    alert_one.acknowledge("ops@ampyr")
    repo.upsert_alert(alert_one)
    acknowledged = repo.get_alert(alert_one.id)
    assert acknowledged is not None
    assert acknowledged.status == AlertStatus.ACKNOWLEDGED
    assert acknowledged.acknowledged_by == "ops@ampyr"

    critical = repo.list_alerts(severity=AlertSeverity.CRITICAL)
    assert len(critical) == 1
    assert critical[0].id == alert_one.id

    plant_two = repo.list_alerts(plant_uid="uid-002")
    assert len(plant_two) == 1
    assert plant_two[0].id == alert_two.id


def test_alert_repository_enabled_rules(test_engine):
    repo = AlertRepository(engine=test_engine)

    enabled_rule = AlertRule(
        name="Low PR",
        metric="pr",
        condition="below",
        threshold=75.0,
        enabled=True,
        applies_to=["uid-001"],
    )
    disabled_rule = AlertRule(
        name="High POA",
        metric="poa_wm2",
        condition="above",
        threshold=1200.0,
        enabled=False,
    )

    repo.upsert_rule(enabled_rule)
    repo.upsert_rule(disabled_rule)

    all_rules = repo.list_rules()
    enabled_rules = repo.get_enabled_rules()

    assert len(all_rules) == 2
    assert len(enabled_rules) == 1
    assert enabled_rules[0].name == "Low PR"
    assert enabled_rules[0].applies_to == ["uid-001"]
