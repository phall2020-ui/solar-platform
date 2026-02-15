"""Alert rule evaluation engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from solar_platform.alerts.default_rules import DEFAULT_ALERT_RULES
from solar_platform.alerts.models import Alert, AlertRule, AlertStatus, TicketPriority
from solar_platform.alerts.notifications import AlertNotificationBridge
from solar_platform.alerts.repository import AlertRepository
from solar_platform.alerts.ticketing import TicketService
from solar_platform.analysis.clipping import ClippingEngine
from solar_platform.analysis.curtailment import CurtailmentEngine
from solar_platform.analysis.fouling import FoulingEngine
from solar_platform.analysis.thermal import ThermalLossEngine
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import PlantRepository, ReadingsRepository


class AlertEngine:
    """Evaluate all enabled rules and manage alert lifecycle."""

    def __init__(
        self,
        *,
        db_engine: DatabaseEngine | None = None,
        repository: AlertRepository | None = None,
        notifier: AlertNotificationBridge | None = None,
    ) -> None:
        self._repo = repository or AlertRepository(engine=db_engine)
        self._plants = PlantRepository(engine=db_engine)
        self._readings = ReadingsRepository(engine=db_engine)
        self._ticketing = TicketService(repository=self._repo)
        self._notifier = notifier or AlertNotificationBridge()
        self._clipping = ClippingEngine(engine=db_engine)
        self._curtailment = CurtailmentEngine(engine=db_engine)
        self._fouling = FoulingEngine(engine=db_engine)
        self._thermal = ThermalLossEngine(engine=db_engine)

    def seed_default_rules(self) -> int:
        """Ensure default rules are present."""
        existing = {rule.name: rule for rule in self._repo.list_rules()}
        inserted = 0
        for rule in DEFAULT_ALERT_RULES:
            if rule.name in existing:
                continue
            slug = rule.name.lower().replace(" ", "_")
            to_store = rule.model_copy(update={"id": f"default_{slug}"})
            self._repo.upsert_rule(to_store)
            inserted += 1
        return inserted

    def evaluate_all(self) -> list[Alert]:
        """Evaluate all enabled rules for all applicable plants."""
        self.seed_default_rules()
        rules = self._repo.get_enabled_rules()
        plants_df = self._plants.list_all()
        if plants_df.empty:
            return []

        uid_col = "plant_uid" if "plant_uid" in plants_df.columns else "uid"
        triggered: list[Alert] = []
        active_keys: set[tuple[str, str]] = set()

        for rule in rules:
            applicable_df = plants_df
            if rule.applies_to:
                applicable_df = plants_df[plants_df[uid_col].isin(rule.applies_to)]

            for _, plant in applicable_df.iterrows():
                plant_uid = str(plant.get(uid_col, ""))
                if not plant_uid:
                    continue

                value = self._compute_metric(plant_uid, rule)
                if self._is_breached(rule, value):
                    active_keys.add((plant_uid, rule.id))
                    alert = self._create_or_update_alert(rule, plant_uid, value)
                    triggered.append(alert)

        self._auto_resolve_stale_alerts(active_keys)
        return triggered

    def evaluate_plant(self, plant_uid: str) -> list[Alert]:
        """Evaluate all enabled rules for one plant."""
        self.seed_default_rules()
        rules = self._repo.get_enabled_rules()
        triggered: list[Alert] = []
        active_keys: set[tuple[str, str]] = set()

        for rule in rules:
            if rule.applies_to and plant_uid not in rule.applies_to:
                continue
            value = self._compute_metric(plant_uid, rule)
            if self._is_breached(rule, value):
                active_keys.add((plant_uid, rule.id))
                triggered.append(self._create_or_update_alert(rule, plant_uid, value))

        self._auto_resolve_stale_alerts(active_keys, plant_uid=plant_uid)
        return triggered

    def _compute_metric(self, plant_uid: str, rule: AlertRule) -> float | None:
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=rule.evaluation_window_minutes)

        if rule.metric == "no_data":
            df = self._readings.get_readings(plant_uid, start=window_start, end=now)
            return 1.0 if df.empty else 0.0

        if rule.metric == "clipping_loss_pct":
            return float(
                self._clipping.run(plant_uid, window_start, now).summary.get("estimated_clipping_loss_pct", 0.0)
            )

        if rule.metric == "curtailment_rate_pct":
            return float(
                self._curtailment.run(plant_uid, window_start, now).summary.get("curtailment_rate_pct", 0.0)
            )

        if rule.metric == "fouling_loss_pct":
            return float(
                self._fouling.run(plant_uid, window_start, now).summary.get("estimated_fouling_loss_pct", 0.0)
            )

        if rule.metric == "thermal_loss_pct":
            return float(
                self._thermal.run(plant_uid, window_start, now).summary.get("estimated_thermal_loss_pct", 0.0)
            )

        df = self._readings.get_readings(plant_uid, start=window_start, end=now)
        if df.empty:
            return None

        if rule.metric == "pr":
            col = self._find_numeric(df, ["performance_ratio", "pr"])
            return float(pd.to_numeric(df[col], errors="coerce").mean()) if col else None

        if rule.metric == "availability_pct":
            power_col = self._find_numeric(df, ["activepower", "power", "pac", "kw"])
            if not power_col:
                return None
            valid = pd.to_numeric(df[power_col], errors="coerce").notna().mean()
            return float(valid * 100.0)

        if rule.metric == "comms_gap_minutes":
            ts_col = self._find_time_col(df)
            if not ts_col:
                return None
            ts = pd.to_datetime(df[ts_col], errors="coerce").dropna().sort_values()
            if len(ts) < 2:
                return 0.0
            max_gap = ts.diff().dropna().max().total_seconds() / 60.0
            return float(max_gap)

        if rule.metric == "module_temp_c":
            col = self._find_numeric(df, ["moduletemperature", "module_temp", "cell_temp"])
            return float(pd.to_numeric(df[col], errors="coerce").mean()) if col else None

        if rule.metric == "power_kw":
            col = self._find_numeric(df, ["activepower", "power", "pac", "kw"])
            return float(pd.to_numeric(df[col], errors="coerce").max()) if col else None

        if rule.metric == "data_quality_score":
            numeric_df = df.select_dtypes(include=["number"])  # type: ignore[arg-type]
            if numeric_df.empty:
                return 0.0
            return float(1.0 - numeric_df.isna().mean().mean())

        return None

    @staticmethod
    def _is_breached(rule: AlertRule, value: float | None) -> bool:
        if rule.condition == "no_data":
            return bool(value == 1.0)
        if value is None:
            return False
        if rule.condition == "below":
            return value < rule.threshold
        if rule.condition == "above":
            return value > rule.threshold
        if rule.condition == "equals":
            return value == rule.threshold
        return False

    def _create_or_update_alert(self, rule: AlertRule, plant_uid: str, value: float | None) -> Alert:
        now = datetime.now(UTC)
        existing = self._repo.get_active_alert_by_rule(plant_uid, rule.id)
        if existing:
            existing.last_seen = now
            existing.occurrence_count += 1
            existing.metric_name = rule.metric
            existing.metric_value = value
            existing.threshold_value = rule.threshold
            alert = self._repo.upsert_alert(existing)
        else:
            alert = Alert(
                plant_uid=plant_uid,
                rule_id=rule.id,
                severity=rule.severity,
                title=rule.name,
                description=rule.description,
                metric_name=rule.metric,
                metric_value=value,
                threshold_value=rule.threshold,
                first_seen=now,
                last_seen=now,
                status=AlertStatus.ACTIVE,
            )
            alert = self._repo.create_alert(alert)
            self._notifier.notify_alert(alert)

        if rule.auto_create_ticket and not alert.ticket_id:
            priority = TicketPriority(rule.ticket_priority) if rule.ticket_priority in {p.value for p in TicketPriority} else TicketPriority.MEDIUM
            ticket = self._ticketing.create_ticket(
                plant_uid=plant_uid,
                title=f"{rule.name} | {plant_uid}",
                description=rule.description or f"{rule.metric} breached threshold {rule.threshold}",
                priority=priority,
                alert_id=alert.id,
                assignee=rule.ticket_assignee,
                created_by="alert_engine",
                metadata={"rule_id": rule.id},
            )
            alert.ticket_id = ticket.id
            alert = self._repo.upsert_alert(alert)
            self._notifier.notify_ticket(ticket)

        return alert

    def _auto_resolve_stale_alerts(self, active_keys: set[tuple[str, str]], plant_uid: str | None = None) -> None:
        active_alerts = self._repo.list_alerts(status=AlertStatus.ACTIVE) + self._repo.list_alerts(status=AlertStatus.ACKNOWLEDGED)
        for alert in active_alerts:
            if plant_uid and alert.plant_uid != plant_uid:
                continue
            key = (alert.plant_uid, alert.rule_id)
            if key in active_keys:
                continue
            alert.resolve("system:auto_resolve")
            self._repo.upsert_alert(alert)

    @staticmethod
    def _find_numeric(df: pd.DataFrame, keys: list[str]) -> str | None:
        for col in df.columns:
            low = col.lower()
            if any(k in low for k in keys) and pd.api.types.is_numeric_dtype(df[col]):
                return col
        return None

    @staticmethod
    def _find_time_col(df: pd.DataFrame) -> str | None:
        for col in ["timestamp", "ts", "datetime", "date", "time"]:
            if col in df.columns:
                return col
        return None
