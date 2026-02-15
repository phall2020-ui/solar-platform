"""Default alert rule catalog for Phase 4 bootstrapping."""

from __future__ import annotations

from solar_platform.alerts.models import AlertRule, AlertSeverity


DEFAULT_ALERT_RULES: list[AlertRule] = [
    AlertRule(name="Low PR", description="Performance ratio below target.", severity=AlertSeverity.WARNING, metric="pr", condition="below", threshold=75.0, auto_create_ticket=True, ticket_priority="high"),
    AlertRule(name="Critical Low PR", description="Severe PR degradation.", severity=AlertSeverity.CRITICAL, metric="pr", condition="below", threshold=65.0, auto_create_ticket=True, ticket_priority="critical"),
    AlertRule(name="Low Availability", description="Availability below 95%.", severity=AlertSeverity.WARNING, metric="availability_pct", condition="below", threshold=95.0, auto_create_ticket=True, ticket_priority="medium"),
    AlertRule(name="Comms Gap", description="Data communication gap in minutes.", severity=AlertSeverity.CRITICAL, metric="comms_gap_minutes", condition="above", threshold=60.0, auto_create_ticket=True, ticket_priority="high"),
    AlertRule(name="Clipping Loss High", description="High clipping loss percentage.", severity=AlertSeverity.WARNING, metric="clipping_loss_pct", condition="above", threshold=3.0),
    AlertRule(name="Curtailment High", description="High curtailment rate percentage.", severity=AlertSeverity.WARNING, metric="curtailment_rate_pct", condition="above", threshold=5.0),
    AlertRule(name="Fouling Loss High", description="High fouling loss percentage.", severity=AlertSeverity.WARNING, metric="fouling_loss_pct", condition="above", threshold=2.0),
    AlertRule(name="Thermal Loss High", description="High thermal loss percentage.", severity=AlertSeverity.WARNING, metric="thermal_loss_pct", condition="above", threshold=4.0),
    AlertRule(name="High Module Temp", description="Average module temperature too high.", severity=AlertSeverity.WARNING, metric="module_temp_c", condition="above", threshold=70.0),
    AlertRule(name="No Data", description="No telemetry data in evaluation window.", severity=AlertSeverity.CRITICAL, metric="no_data", condition="no_data", threshold=1.0, auto_create_ticket=True, ticket_priority="critical"),
    AlertRule(name="Data Quality Low", description="Low data quality score.", severity=AlertSeverity.WARNING, metric="data_quality_score", condition="below", threshold=0.8),
    AlertRule(name="Power Spike", description="Unexpected high output spike.", severity=AlertSeverity.INFO, metric="power_kw", condition="above", threshold=15000.0),
]
