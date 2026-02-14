# Phase 4: Alert & Ticketing System — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3 weeks  
**Goal:** Build an automated alert engine with 12 default rules, a ticket lifecycle system, and Kanban-style ticket management UI in Streamlit. Alerts detect performance issues; tickets track the resolution workflow.

**Key Principle:** Alert rules are DB-configured (not hardcoded). The alert engine runs via `PortfolioService.evaluate_alerts()` (callable from Streamlit buttons now, Celery tasks later). Ticket state machine is pure Python — no Streamlit dependency.

**Prerequisite:** Phase 0 (database), Phase 1 (data layer), Phase 3 (analysis engines for PR/clipping/curtailment metrics).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 4.1: Alert Data Model](#task-41-alert-data-model)
4. [Task 4.2: Alert Rule Engine](#task-42-alert-rule-engine)
5. [Task 4.3: Default Alert Rules (12)](#task-43-default-alert-rules-12)
6. [Task 4.4: Alert Lifecycle & State Machine](#task-44-alert-lifecycle--state-machine)
7. [Task 4.5: Ticket Data Model](#task-45-ticket-data-model)
8. [Task 4.6: Ticket Lifecycle & SLA](#task-46-ticket-lifecycle--sla)
9. [Task 4.7: Alert → Ticket Auto-Creation](#task-47-alert--ticket-auto-creation)
10. [Task 4.8: Alert Dashboard UI](#task-48-alert-dashboard-ui)
11. [Task 4.9: Ticket Kanban Board UI](#task-49-ticket-kanban-board-ui)
12. [Task 4.10: Notification Integration](#task-410-notification-integration)
13. [Risks](#risks)
14. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 4.1 Alert Data Model | ✅ Done | 4 | P0 | Phase 0 |
| 4.2 Alert Rule Engine | ✅ Done | 8 | P0 | 4.1 |
| 4.3 Default Alert Rules (12) | ✅ Done | 6 | P0 | 4.2 |
| 4.4 Alert Lifecycle & State Machine | ✅ Done | 4 | P0 | 4.1 |
| 4.5 Ticket Data Model | ✅ Done | 4 | P0 | 4.1 |
| 4.6 Ticket Lifecycle & SLA | ✅ Done | 6 | P1 | 4.5 |
| 4.7 Alert → Ticket Auto-Creation | ✅ Done | 4 | P0 | 4.4, 4.5 |
| 4.8 Alert Dashboard UI | ✅ Done | 8 | P0 | 4.4 |
| 4.9 Ticket Kanban Board UI | ✅ Done | 8 | P1 | 4.6 |
| 4.10 Notification Integration | ✅ Done | 4 | P1 | 4.4 |
| **TOTAL** | | **56** | | |

---

## 2. Dependency Graph

```
┌─────────────────────┐
│ 4.1 Alert Data      │
│ Model               │
└──────┬──────────────┘
       │
  ┌────┼────────────────────┐
  │    │                    │
  ▼    ▼                    ▼
┌────────┐   ┌──────────┐ ┌──────────────┐
│ 4.2    │   │ 4.4      │ │ 4.5 Ticket   │
│ Rule   │   │ Alert    │ │ Data Model   │
│ Engine │   │ Lifecycle│ │              │
└──┬─────┘   └────┬─────┘ └──────┬───────┘
   │              │               │
   ▼              │               ▼
┌────────┐        │        ┌──────────────┐
│ 4.3    │        │        │ 4.6 Ticket   │
│ Default│        │        │ Lifecycle/SLA│
│ Rules  │        │        └──────┬───────┘
└────────┘        │               │
                  ├───────────────┤
                  ▼               │
           ┌──────────────┐      │
           │ 4.7 Alert →  │      │
           │ Ticket Auto  │      │
           └──────┬───────┘      │
                  │               │
            ┌─────┼───────┐      │
            ▼     │       ▼      ▼
     ┌────────┐   │  ┌──────────────┐
     │ 4.8    │   │  │ 4.9 Ticket   │
     │ Alert  │   │  │ Kanban UI    │
     │ Dash   │   │  └──────────────┘
     └────────┘   │
                  ▼
           ┌──────────────┐
           │ 4.10 Notify  │
           └──────────────┘
```

---

## Task 4.1: Alert Data Model

**Goal:** Define alert database schema and pydantic models.

**Estimated Hours:** 4

### Database Schema

```sql
-- DuckDB table for alerts
CREATE TABLE IF NOT EXISTS alerts (
    id              VARCHAR PRIMARY KEY,          -- UUID
    plant_uid       VARCHAR NOT NULL,
    rule_id         VARCHAR NOT NULL,
    severity        VARCHAR NOT NULL,             -- 'critical', 'warning', 'info'
    status          VARCHAR NOT NULL DEFAULT 'active',  -- 'active', 'acknowledged', 'resolved', 'suppressed'
    title           VARCHAR NOT NULL,
    description     TEXT,
    metric_name     VARCHAR,                      -- What was measured
    metric_value    DOUBLE,                       -- Measured value
    threshold_value DOUBLE,                       -- Threshold that was breached
    first_seen      TIMESTAMP NOT NULL,
    last_seen       TIMESTAMP NOT NULL,
    acknowledged_at TIMESTAMP,
    resolved_at     TIMESTAMP,
    acknowledged_by VARCHAR,
    resolved_by     VARCHAR,
    ticket_id       VARCHAR,                      -- Link to ticket if created
    occurrence_count INTEGER DEFAULT 1,
    metadata        VARCHAR,                      -- JSON string for extra data
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_plant ON alerts (plant_uid, status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity, status);
```

### Pydantic Models

#### `services/alerts/__init__.py`
```python
"""Alert and ticketing system."""
```

#### `services/alerts/models.py`
```python
"""
Alert and ticket data models.

Framework-agnostic Pydantic models.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class Alert(BaseModel):
    """Alert instance — a specific detected issue."""
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
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_by: str | None = None
    ticket_id: str | None = None
    occurrence_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    def acknowledge(self, user: str) -> None:
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = user

    def resolve(self, user: str) -> None:
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.utcnow()
        self.resolved_by = user

    def suppress(self) -> None:
        self.status = AlertStatus.SUPPRESSED

    @property
    def duration_hours(self) -> float:
        end = self.resolved_at or datetime.utcnow()
        return (end - self.first_seen).total_seconds() / 3600

    @property
    def is_active(self) -> bool:
        return self.status in (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED)


class AlertRule(BaseModel):
    """Alert rule configuration — defines when an alert fires."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    
    # Evaluation
    metric: str                   # e.g., "pr", "comms_gap", "inverter_power"
    condition: str                # "below", "above", "equals", "no_data"
    threshold: float = 0.0
    
    # Timing
    evaluation_window_minutes: int = 60
    min_consecutive_breaches: int = 1
    cooldown_minutes: int = 60    # Don't re-fire within this period
    
    # Scope
    applies_to: list[str] = Field(default_factory=list)  # Plant UIDs (empty = all)
    
    # Auto-ticketing
    auto_create_ticket: bool = False
    ticket_priority: str = "medium"
    ticket_assignee: str | None = None
```

### Acceptance Criteria

- [ ] Alert table created in DuckDB
- [ ] Alert model supports full lifecycle (active → acknowledged → resolved)
- [ ] AlertRule model configurable per plant or fleet-wide
- [ ] Index on plant_uid + status for fast queries

---

## Task 4.2: Alert Rule Engine

**Goal:** Build the evaluation engine that checks alert rules against current data.

**Estimated Hours:** 8

### `services/alerts/engine.py`
```python
"""
Alert rule evaluation engine.

Evaluates all enabled alert rules against current plant data.
Called from: Streamlit UI button (now), Celery periodic task (future).

DESIGN NOTES FOR EXTRACTION:
- This is pure business logic — no Streamlit imports
- When adding Celery: call evaluate_all() from a periodic task
- When adding FastAPI: expose as POST /api/alerts/evaluate
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from services.alerts.models import Alert, AlertRule, AlertSeverity, AlertStatus
from services.alerts.repository import AlertRepository
from services.database.repository import PlantRepository, ReadingsRepository

logger = structlog.get_logger("alerts.engine")


class AlertEngine:
    """Evaluates alert rules and creates/updates alerts."""

    def __init__(self):
        self._alert_repo = AlertRepository()
        self._plant_repo = PlantRepository()
        self._readings_repo = ReadingsRepository()

    def evaluate_all(self) -> list[Alert]:
        """Evaluate all enabled rules for all applicable plants."""
        rules = self._alert_repo.get_enabled_rules()
        plants = self._plant_repo.list_all()
        new_alerts: list[Alert] = []

        for rule in rules:
            applicable_plants = (
                [p for _, p in plants.iterrows() if p["uid"] in rule.applies_to]
                if rule.applies_to
                else [p for _, p in plants.iterrows()]
            )

            for plant in applicable_plants:
                try:
                    alert = self._evaluate_rule(rule, plant)
                    if alert:
                        self._process_alert(alert)
                        new_alerts.append(alert)
                except Exception as e:
                    logger.error(
                        "alert_evaluation_error",
                        rule=rule.name,
                        plant=plant.get("uid"),
                        error=str(e),
                    )

        # Auto-resolve alerts that are no longer active
        self._auto_resolve_stale_alerts()
        
        return new_alerts

    def evaluate_plant(self, plant_uid: str) -> list[Alert]:
        """Evaluate all rules for a specific plant."""
        rules = self._alert_repo.get_enabled_rules()
        plant = self._plant_repo.get_by_uid(plant_uid)
        if not plant:
            return []

        new_alerts = []
        for rule in rules:
            if rule.applies_to and plant_uid not in rule.applies_to:
                continue
            alert = self._evaluate_rule(rule, plant)
            if alert:
                self._process_alert(alert)
                new_alerts.append(alert)
        return new_alerts

    def _evaluate_rule(self, rule: AlertRule, plant: dict) -> Alert | None:
        """Evaluate a single rule for a single plant."""
        plant_uid = plant.get("uid", "")
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=rule.evaluation_window_minutes)

        # Check cooldown — don't re-fire too quickly
        recent = self._alert_repo.get_recent_for_rule(
            plant_uid, rule.id, since=now - timedelta(minutes=rule.cooldown_minutes)
        )
        if recent:
            return None

        # Get metric value
        value = self._get_metric_value(plant_uid, rule.metric, window_start, now)
        if value is None and rule.condition != "no_data":
            return None

        # Evaluate condition
        triggered = False
        if rule.condition == "below" and value is not None:
            triggered = value < rule.threshold
        elif rule.condition == "above" and value is not None:
            triggered = value > rule.threshold
        elif rule.condition == "equals" and value is not None:
            triggered = abs(value - rule.threshold) < 0.001
        elif rule.condition == "no_data":
            triggered = value is None

        if not triggered:
            return None

        return Alert(
            plant_uid=plant_uid,
            rule_id=rule.id,
            severity=rule.severity,
            title=f"{rule.name}: {plant.get('name', plant_uid)}",
            description=rule.description,
            metric_name=rule.metric,
            metric_value=value,
            threshold_value=rule.threshold,
        )

    def _get_metric_value(
        self, plant_uid: str, metric: str,
        start: datetime, end: datetime,
    ) -> float | None:
        """Get a metric value for alert evaluation.
        
        Supported metrics:
        - "pr": Performance Ratio (%)
        - "generation_kwh": Total generation
        - "power_kw": Current power
        - "comms_gap_minutes": Minutes since last reading
        - "irradiance_wm2": Average irradiance
        - "inverter_count_offline": Number of offline inverters
        """
        if metric == "pr":
            return self._readings_repo.get_plant_pr(plant_uid, start, end)
        elif metric == "generation_kwh":
            return self._readings_repo.get_plant_generation(plant_uid, start, end)
        elif metric == "comms_gap_minutes":
            latest = self._readings_repo.get_latest_timestamp(plant_uid)
            if latest:
                return (end - latest).total_seconds() / 60
            return None
        elif metric == "power_kw":
            return self._readings_repo.get_latest_power(plant_uid)
        else:
            logger.warning("unknown_alert_metric", metric=metric, plant_uid=plant_uid)
            return None

    def _process_alert(self, alert: Alert) -> None:
        """Process a new alert — check for deduplication, store in DB."""
        existing = self._alert_repo.find_active(
            alert.plant_uid, alert.rule_id
        )
        if existing:
            # Update occurrence count instead of creating duplicate
            existing.occurrence_count += 1
            existing.last_seen = datetime.utcnow()
            self._alert_repo.update(existing)
            logger.info("alert_updated", alert_id=existing.id, count=existing.occurrence_count)
        else:
            self._alert_repo.create(alert)
            logger.info("alert_created", alert_id=alert.id, severity=alert.severity.value)

    def _auto_resolve_stale_alerts(self) -> None:
        """Auto-resolve alerts that haven't been seen in > 24 hours."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stale = self._alert_repo.get_stale_alerts(cutoff)
        for alert in stale:
            alert.resolve(user="system")
            self._alert_repo.update(alert)
            logger.info("alert_auto_resolved", alert_id=alert.id)
```

### Acceptance Criteria

- [ ] Engine evaluates all enabled rules for all plants
- [ ] Cooldown prevents duplicate alerts within configured period
- [ ] Deduplication increments occurrence count
- [ ] Auto-resolve stale alerts after 24 hours
- [ ] Support for 6+ metric types

---

## Task 4.3: Default Alert Rules (12)

**Goal:** Seed the database with 12 default alert rules covering common solar monitoring scenarios.

**Estimated Hours:** 6

### Default Rules

| # | Rule Name | Metric | Condition | Threshold | Severity | Window |
|---|-----------|--------|-----------|-----------|----------|--------|
| 1 | Low Performance Ratio | pr | below | 60% | critical | 24h |
| 2 | Underperformance | pr | below | 75% | warning | 24h |
| 3 | Communication Loss | comms_gap_minutes | above | 120 | critical | — |
| 4 | Communication Delay | comms_gap_minutes | above | 30 | warning | — |
| 5 | Zero Generation (Daytime) | power_kw | below | 1 | critical | 60min |
| 6 | High Clipping Rate | clipping_pct | above | 10% | warning | 24h |
| 7 | Excessive Curtailment | curtailment_pct | above | 15% | warning | 24h |
| 8 | Inverter Offline | inverter_count_offline | above | 0 | critical | 30min |
| 9 | Irradiance Sensor Anomaly | irradiance_wm2 | above | 1500 | warning | 15min |
| 10 | Temperature Alarm | module_temp_c | above | 85 | warning | 15min |
| 11 | Grid Export Limit Active | export_limit_active | equals | 1 | info | 15min |
| 12 | Data Quality Low | data_quality_score | below | 0.7 | warning | 24h |

### Seed Script

```python
# scripts/seed_alert_rules.py
"""Seed default alert rules into the database."""
from services.alerts.models import AlertRule, AlertSeverity
from services.alerts.repository import AlertRepository


DEFAULT_RULES = [
    AlertRule(
        name="Low Performance Ratio",
        description="Performance ratio has dropped below 60% — investigate potential inverter failure, significant shading, or soiling.",
        severity=AlertSeverity.CRITICAL,
        metric="pr",
        condition="below",
        threshold=60.0,
        evaluation_window_minutes=1440,  # 24h
        cooldown_minutes=240,
        auto_create_ticket=True,
        ticket_priority="high",
    ),
    AlertRule(
        name="Underperformance",
        description="Performance ratio below 75% — may indicate partial shading, soiling, or mild clipping.",
        severity=AlertSeverity.WARNING,
        metric="pr",
        condition="below",
        threshold=75.0,
        evaluation_window_minutes=1440,
        cooldown_minutes=480,
    ),
    AlertRule(
        name="Communication Loss",
        description="No data received for 2+ hours — check communications module and network.",
        severity=AlertSeverity.CRITICAL,
        metric="comms_gap_minutes",
        condition="above",
        threshold=120.0,
        evaluation_window_minutes=15,
        cooldown_minutes=120,
        auto_create_ticket=True,
        ticket_priority="high",
    ),
    AlertRule(
        name="Communication Delay",
        description="No data for 30+ minutes — may be a transient communication issue.",
        severity=AlertSeverity.WARNING,
        metric="comms_gap_minutes",
        condition="above",
        threshold=30.0,
        evaluation_window_minutes=15,
        cooldown_minutes=60,
    ),
    AlertRule(
        name="Zero Generation (Daytime)",
        description="Plant producing no power during expected generation hours.",
        severity=AlertSeverity.CRITICAL,
        metric="power_kw",
        condition="below",
        threshold=1.0,
        evaluation_window_minutes=60,
        cooldown_minutes=120,
        auto_create_ticket=True,
        ticket_priority="critical",
    ),
    # ... remaining 7 rules follow same pattern
]


def seed_rules():
    """Insert default rules if they don't already exist."""
    repo = AlertRepository()
    existing = repo.get_all_rules()
    existing_names = {r.name for r in existing}
    
    for rule in DEFAULT_RULES:
        if rule.name not in existing_names:
            repo.create_rule(rule)
            print(f"  Created rule: {rule.name}")
        else:
            print(f"  Skipped (exists): {rule.name}")


if __name__ == "__main__":
    seed_rules()
```

### Acceptance Criteria

- [ ] 12 default rules seeded
- [ ] Rules configurable (edit threshold, severity, enable/disable)
- [ ] Critical rules auto-create tickets
- [ ] Rules scoped to all plants by default

---

## Task 4.4: Alert Lifecycle & State Machine

**Goal:** Define alert state transitions and enforce valid transitions.

**Estimated Hours:** 4

### State Machine

```
                    ┌──────────────────────────┐
                    │                          │
                    ▼                          │
┌─────────┐    ┌────────────┐    ┌──────────┐ │
│         │    │            │    │          │ │
│ ACTIVE  │───▶│ACKNOWLEDGED│───▶│ RESOLVED │ │
│         │    │            │    │          │ │
└────┬────┘    └─────┬──────┘    └──────────┘ │
     │               │                        │
     │               │                        │
     ▼               ▼                        │
┌──────────┐   (can go back to ACTIVE         │
│SUPPRESSED│    if condition recurs)          │
└──────────┘                                  │
     │                                        │
     └────────────────────────────────────────┘
           (un-suppress → back to ACTIVE)
```

### Valid Transitions

```python
VALID_TRANSITIONS = {
    AlertStatus.ACTIVE: [AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED, AlertStatus.SUPPRESSED],
    AlertStatus.ACKNOWLEDGED: [AlertStatus.RESOLVED, AlertStatus.ACTIVE],
    AlertStatus.RESOLVED: [AlertStatus.ACTIVE],  # Re-open if condition recurs
    AlertStatus.SUPPRESSED: [AlertStatus.ACTIVE],
}
```

### Acceptance Criteria

- [ ] Invalid transitions raise `ValueError`
- [ ] State transitions logged with user + timestamp
- [ ] Resolved alerts can re-open if condition recurs

---

## Task 4.5: Ticket Data Model

**Goal:** Define the ticket schema for tracking resolution of issues.

**Estimated Hours:** 4

### `services/alerts/ticket_models.py`
```python
"""
Ticket data models for issue tracking.

Tickets are created from alerts (auto or manual) and track
the resolution workflow: triage → assignment → investigation → resolution.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"           # Waiting for external input
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TicketPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketCategory(str, Enum):
    INVERTER = "inverter"
    COMMUNICATION = "communication"
    PERFORMANCE = "performance"
    GRID = "grid"
    ENVIRONMENTAL = "environmental"
    MAINTENANCE = "maintenance"
    OTHER = "other"


class Ticket(BaseModel):
    """Issue tracking ticket."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    
    # Classification
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    category: TicketCategory = TicketCategory.OTHER
    
    # Relationships
    plant_uid: str = ""
    alert_ids: list[str] = Field(default_factory=list)
    
    # Assignment
    assignee: str | None = None
    reporter: str = "system"
    
    # SLA
    sla_target_hours: float = 72.0    # Default 72h resolution target
    sla_breached: bool = False
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    
    # Activity log
    comments: list[TicketComment] = Field(default_factory=list)

    @property
    def age_hours(self) -> float:
        end = self.resolved_at or datetime.utcnow()
        return (end - self.created_at).total_seconds() / 3600

    @property
    def is_sla_breached(self) -> bool:
        return self.age_hours > self.sla_target_hours and self.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)


class TicketComment(BaseModel):
    """Comment on a ticket."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_system: bool = False
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS tickets (
    id              VARCHAR PRIMARY KEY,
    title           VARCHAR NOT NULL,
    description     TEXT,
    priority        VARCHAR DEFAULT 'medium',
    status          VARCHAR DEFAULT 'open',
    category        VARCHAR DEFAULT 'other',
    plant_uid       VARCHAR,
    alert_ids       VARCHAR,             -- JSON array of alert IDs
    assignee        VARCHAR,
    reporter        VARCHAR DEFAULT 'system',
    sla_target_hours DOUBLE DEFAULT 72.0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP,
    closed_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_comments (
    id              VARCHAR PRIMARY KEY,
    ticket_id       VARCHAR NOT NULL,
    author          VARCHAR NOT NULL,
    text            TEXT NOT NULL,
    is_system       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
```

### Acceptance Criteria

- [ ] Ticket model with priority, status, category, SLA
- [ ] SLA breach auto-calculated from creation time
- [ ] Comment system for tracking investigation
- [ ] Linked to alerts via alert_ids

---

## Task 4.6: Ticket Lifecycle & SLA

**Goal:** Implement ticket state transitions and SLA tracking.

**Estimated Hours:** 6

### SLA Configuration

| Priority | Target Resolution | Escalation After |
|----------|------------------|------------------|
| Critical | 4 hours | 2 hours |
| High | 24 hours | 12 hours |
| Medium | 72 hours | 48 hours |
| Low | 168 hours (1 week) | — |

### Acceptance Criteria

- [ ] SLA timer runs from ticket creation
- [ ] SLA breach flagged visually in UI
- [ ] Ticket comments auto-added on state change

---

## Task 4.7: Alert → Ticket Auto-Creation

**Goal:** Automatically create tickets from critical alerts.

**Estimated Hours:** 4

```python
# In AlertEngine._process_alert():
if alert.severity == AlertSeverity.CRITICAL and rule.auto_create_ticket:
    ticket = Ticket(
        title=alert.title,
        description=alert.description,
        priority=TicketPriority(rule.ticket_priority),
        plant_uid=alert.plant_uid,
        alert_ids=[alert.id],
        assignee=rule.ticket_assignee,
        reporter="alert_engine",
    )
    ticket_repo.create(ticket)
    alert.ticket_id = ticket.id
```

### Acceptance Criteria

- [ ] Critical alerts auto-create tickets
- [ ] Ticket linked back to alert
- [ ] No duplicate tickets for recurring alert

---

## Task 4.8: Alert Dashboard UI

**Goal:** Streamlit page showing active alerts with filtering and bulk actions.

**Estimated Hours:** 8

### Layout

```
┌──────────────────────────────────────────────────────┐
│ 🔔 Active Alerts                    [Evaluate Now 🔄]│
├──────────────────────────────────────────────────────┤
│ Summary: 🔴 2 Critical  🟡 5 Warning  ℹ️ 3 Info     │
├──────────────────────────────────────────────────────┤
│ Filter: [All ▼] [All Plants ▼] [Last 7 Days ▼]     │
├──────────────────────────────────────────────────────┤
│ ☐ 🔴 Low PR: Cranfield Solar — PR 42.1% (< 60%)    │
│     First seen: 2h ago | Occurrences: 5 | [ACK] [→🎫]│
│                                                      │
│ ☐ 🔴 Comms Loss: Dawlish Farm — 3h since last data  │
│     First seen: 3h ago | Occurrences: 1 | [ACK] [→🎫]│
│                                                      │
│ ☐ 🟡 Underperformance: Brightside — PR 67.8%       │
│     First seen: 1d ago | Occurrences: 12 | [ACK]    │
└──────────────────────────────────────────────────────┘
```

### Acceptance Criteria

- [ ] Alert list with severity icons and filters
- [ ] Acknowledge button per alert
- [ ] "Evaluate Now" button triggers manual rule evaluation
- [ ] Bulk acknowledge/resolve
- [ ] Create ticket from alert

---

## Task 4.9: Ticket Kanban Board UI

**Goal:** Streamlit-based Kanban board for ticket management.

**Estimated Hours:** 8

### Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ 🎫 Ticket Board                                                 │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│ Open (3)     │ In Progress  │ Waiting (1)  │ Resolved (5)       │
│              │ (2)          │              │                    │
│ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐      │
│ │🔴 Crit   │ │ │🟡 Med    │ │ │🟡 Med    │ │ │✅ Done   │      │
│ │Cranfield │ │ │Inverter  │ │ │Waiting   │ │ │Ashford   │      │
│ │Low PR    │ │ │repair    │ │ │for parts │ │ │cleaned   │      │
│ │2h ago    │ │ │@John     │ │ │@Sarah    │ │ │3d ago    │      │
│ └──────────┘ │ └──────────┘ │ └──────────┘ │ └──────────┘      │
│ ┌──────────┐ │ ┌──────────┐ │              │                    │
│ │🔴 Crit   │ │ │🟡 High   │ │              │                    │
│ │Comms     │ │ │Soiling   │ │              │                    │
│ │loss      │ │ │schedule  │ │              │                    │
│ └──────────┘ │ └──────────┘ │              │                    │
└──────────────┴──────────────┴──────────────┴────────────────────┘
```

### Implementation

```python
# Kanban columns using st.columns
def render_kanban():
    st.title("🎫 Ticket Board")
    
    tickets = ticket_service.get_all_tickets()
    
    col_open, col_progress, col_waiting, col_resolved = st.columns(4)
    
    with col_open:
        st.subheader(f"Open ({len([t for t in tickets if t.status == 'open'])})")
        for t in [t for t in tickets if t.status == "open"]:
            _render_ticket_card(t)
    
    with col_progress:
        st.subheader("In Progress")
        # ... etc
```

### Acceptance Criteria

- [ ] Kanban board with 4 columns (Open, In Progress, Waiting, Resolved)
- [ ] Ticket cards show priority, title, assignee, age
- [ ] Click card to view ticket detail
- [ ] Status change via dropdowns or buttons
- [ ] SLA breach highlighted visually

---

## Task 4.10: Notification Integration

**Goal:** Connect alert lifecycle events to the existing notification system.

**Estimated Hours:** 4

### Events to Notify

| Event | Channel | Template |
|-------|---------|----------|
| New critical alert | In-app + email | "🔴 {rule}: {plant} — {metric}: {value}" |
| New warning alert | In-app | "🟡 {rule}: {plant}" |
| Alert acknowledged | In-app | "✅ {user} acknowledged: {alert}" |
| Ticket created | In-app | "🎫 Ticket created: {title}" |
| SLA breach approaching | In-app + email | "⏰ SLA expiring in 2h: {ticket}" |

### Integration Point

```python
# In services/alerts/engine.py, after creating alert:
from services.notification_service import NotificationService

notifier = NotificationService()
notifier.send(
    user_id="all_admins",
    type="alert",
    title=f"New {alert.severity.value} alert",
    message=alert.title,
    data={"alert_id": alert.id, "plant_uid": alert.plant_uid},
)
```

### Acceptance Criteria

- [ ] Critical alerts trigger in-app notifications
- [ ] Ticket creation notifies assignee
- [ ] SLA breach warnings sent before expiry

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Alert storm from fleet-wide issue | High | Medium | Cooldown periods; rate limit notifications; aggregation |
| False positive alerts | Medium | High | Tunable thresholds; min_consecutive_breaches; suppress feature |
| DuckDB performance with many alerts | Low | Low | Archive resolved alerts after 90 days |
| SLA clock drifts with timezone issues | Medium | Medium | All timestamps in UTC; display in user's timezone |
| Notification spam | Medium | High | Digest mode; configurable notification preferences |

---

## Definition of Done

- [ ] Alert engine evaluates 12 default rules
- [ ] Alert lifecycle: active → acknowledged → resolved
- [ ] Auto-resolve stale alerts after 24h
- [ ] Ticket system with Kanban board
- [ ] Alert → Ticket auto-creation for critical rules
- [ ] SLA tracking with breach highlighting
- [ ] Notification integration for critical alerts
- [ ] Alert dashboard with filtering
- [ ] 15+ unit tests for engine and state machine
- [ ] Alert rules configurable via admin UI
