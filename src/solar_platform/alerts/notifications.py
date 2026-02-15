"""Notification bridge for alert/ticket events."""

from __future__ import annotations

from solar_platform.alerts.models import Alert, Ticket


class AlertNotificationBridge:
    """Best-effort bridge into existing notification service."""

    def __init__(self) -> None:
        self._service = None
        try:
            from solar_platform.services.notifications import NotificationService, NotificationType

            self._service = NotificationService()
            self._notification_type = NotificationType.ALERT
        except Exception:
            self._service = None
            self._notification_type = "alert"

    def notify_alert(self, alert: Alert) -> None:
        if not self._service:
            return
        self._service.create_notification(
            user_id=None,
            title=f"Alert: {alert.title}",
            message=f"{alert.plant_uid} | {alert.severity.value} | {alert.metric_name}={alert.metric_value}",
            notification_type=self._notification_type,
            data={"alert_id": alert.id, "plant_uid": alert.plant_uid},
        )

    def notify_ticket(self, ticket: Ticket) -> None:
        if not self._service:
            return
        self._service.create_notification(
            user_id=None,
            title=f"Ticket: {ticket.title}",
            message=f"{ticket.plant_uid} | {ticket.priority.value} | {ticket.status.value}",
            notification_type=self._notification_type,
            data={"ticket_id": ticket.id, "plant_uid": ticket.plant_uid},
        )
