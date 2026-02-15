"""Alert lifecycle state machine helpers."""

from __future__ import annotations

from solar_platform.alerts.models import AlertStatus
from solar_platform.alerts.repository import AlertRepository


class AlertStateMachine:
    """Encapsulate valid state transitions for alerts."""

    def __init__(self, repository: AlertRepository | None = None):
        self._repo = repository or AlertRepository()

    def acknowledge(self, alert_id: str, user: str) -> bool:
        alert = self._repo.get_alert(alert_id)
        if not alert:
            return False
        if alert.status == AlertStatus.RESOLVED:
            return False
        alert.acknowledge(user)
        self._repo.upsert_alert(alert)
        return True

    def resolve(self, alert_id: str, user: str) -> bool:
        alert = self._repo.get_alert(alert_id)
        if not alert:
            return False
        alert.resolve(user)
        self._repo.upsert_alert(alert)
        return True

    def suppress(self, alert_id: str) -> bool:
        alert = self._repo.get_alert(alert_id)
        if not alert:
            return False
        alert.suppress()
        self._repo.upsert_alert(alert)
        return True
