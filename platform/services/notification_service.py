"""
Notification Service for Solar Portfolio Manager.
Provides alerts, notifications, and threshold-based monitoring.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st


class NotificationType:
    """Notification types."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    ALERT = "alert"


class Notification:
    """Notification model."""
    def __init__(self, notification_id: int, user_id: int | None, title: str,
                 message: str, notification_type: str, is_read: bool = False,
                 created_at: str = None, data: dict = None):
        self.notification_id = notification_id
        self.user_id = user_id
        self.title = title
        self.message = message
        self.notification_type = notification_type
        self.is_read = is_read
        self.created_at = created_at
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert notification to dictionary."""
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type,
            "is_read": self.is_read,
            "created_at": self.created_at,
            "data": self.data,
        }


class Alert:
    """Alert rule model."""
    def __init__(self, alert_id: int, name: str, description: str,
                 metric: str, condition: str, threshold: float,
                 is_active: bool = True, created_by: int | None = None):
        self.alert_id = alert_id
        self.name = name
        self.description = description
        self.metric = metric
        self.condition = condition  # '<', '>', '<=', '>=', '==', '!='
        self.threshold = threshold
        self.is_active = is_active
        self.created_by = created_by

    def check(self, value: float) -> bool:
        """Check if alert condition is met."""
        if not self.is_active:
            return False

        conditions = {
            '<': lambda v, t: v < t,
            '>': lambda v, t: v > t,
            '<=': lambda v, t: v <= t,
            '>=': lambda v, t: v >= t,
            '==': lambda v, t: v == t,
            '!=': lambda v, t: v != t,
        }

        check_func = conditions.get(self.condition)
        if check_func:
            return check_func(value, self.threshold)
        return False


class NotificationService:
    """Service for managing notifications and alerts."""

    def __init__(self, db_path: Path | None = None):
        """Initialize notification service."""
        if db_path is None:
            db_path = Path.home() / ".solar_toolkit" / "notifications.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the notifications database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Notifications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                metric TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_triggered TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            )
        """)

        # Alert history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                value REAL NOT NULL,
                message TEXT,
                FOREIGN KEY (alert_id) REFERENCES alerts(alert_id)
            )
        """)

        conn.commit()
        conn.close()
        self._create_default_alerts()

    def _create_default_alerts(self) -> None:
        """Create default alert rules."""
        default_alerts = [
            ("Low PR Alert", "Performance Ratio below threshold", "pr", "<", 75.0),
            ("High Availability", "Availability above target", "availability", ">", 99.0),
            ("Low Availability", "Availability below target", "availability", "<", 95.0),
            ("High Clipping Loss", "Clipping loss exceeds threshold", "clipping_loss", ">", 5.0),
            ("High Soiling Loss", "Soiling loss exceeds threshold", "soiling_loss", ">", 3.0),
        ]

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM alerts")
        if cursor.fetchone()[0] == 0:
            for name, desc, metric, condition, threshold in default_alerts:
                cursor.execute("""
                    INSERT INTO alerts (name, description, metric, condition, threshold)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, desc, metric, condition, threshold))
            conn.commit()

        conn.close()

    def create_notification(self, user_id: int | None, title: str,
                          message: str, notification_type: str = NotificationType.INFO,
                          data: dict | None = None) -> int:
        """Create a new notification."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        data_json = json.dumps(data) if data else None
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, notification_type, data)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, title, message, notification_type, data_json))

        notification_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return notification_id

    def get_notifications(self, user_id: int | None = None,
                         unread_only: bool = False,
                         limit: int = 50) -> list[Notification]:
        """Get notifications for a user."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        query = """
            SELECT notification_id, user_id, title, message, notification_type,
                   is_read, created_at, data
            FROM notifications
            WHERE 1=1
        """
        params = []

        if user_id is not None:
            query += " AND (user_id = ? OR user_id IS NULL)"
            params.append(user_id)

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)

        notifications = []
        for row in cursor.fetchall():
            data = json.loads(row[7]) if row[7] else None
            notifications.append(Notification(*row[:7], data=data))

        conn.close()
        return notifications

    def mark_as_read(self, notification_id: int) -> None:
        """Mark notification as read."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE notifications SET is_read = 1 WHERE notification_id = ?
        """, (notification_id,))

        conn.commit()
        conn.close()

    def mark_all_as_read(self, user_id: int) -> None:
        """Mark all notifications as read for a user."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE notifications SET is_read = 1
            WHERE user_id = ? OR user_id IS NULL
        """, (user_id,))

        conn.commit()
        conn.close()

    def delete_notification(self, notification_id: int) -> None:
        """Delete a notification."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("DELETE FROM notifications WHERE notification_id = ?",
                      (notification_id,))

        conn.commit()
        conn.close()

    def create_alert(self, name: str, description: str, metric: str,
                    condition: str, threshold: float, created_by: int | None = None) -> int:
        """Create a new alert rule."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (name, description, metric, condition, threshold, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, metric, condition, threshold, created_by))

        alert_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return alert_id

    def get_alerts(self, active_only: bool = True) -> list[Alert]:
        """Get all alert rules."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        query = """
            SELECT alert_id, name, description, metric, condition, threshold,
                   is_active, created_by
            FROM alerts
        """
        if active_only:
            query += " WHERE is_active = 1"

        cursor.execute(query)

        alerts = [Alert(*row) for row in cursor.fetchall()]
        conn.close()
        return alerts

    def update_alert(self, alert_id: int, **kwargs: Any) -> None:
        """Update alert rule."""
        allowed_fields = ['name', 'description', 'metric', 'condition',
                         'threshold', 'is_active']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [alert_id]

        cursor.execute(f"UPDATE alerts SET {set_clause} WHERE alert_id = ?", values)
        conn.commit()
        conn.close()

    def check_alert(self, metric: str, value: float, user_id: int | None = None) -> None:
        """Check if any alerts are triggered for a metric."""
        alerts = self.get_alerts(active_only=True)

        for alert in alerts:
            if alert.metric == metric and alert.check(value):
                # Log to alert history
                conn = sqlite3.connect(str(self.db_path))
                cursor = conn.cursor()

                message = f"{alert.name}: {metric} = {value} (threshold: {alert.condition} {alert.threshold})"
                cursor.execute("""
                    INSERT INTO alert_history (alert_id, value, message)
                    VALUES (?, ?, ?)
                """, (alert.alert_id, value, message))

                cursor.execute("""
                    UPDATE alerts SET last_triggered = CURRENT_TIMESTAMP
                    WHERE alert_id = ?
                """, (alert.alert_id,))

                conn.commit()
                conn.close()

                # Create notification
                self.create_notification(
                    user_id=user_id,
                    title=f"Alert: {alert.name}",
                    message=message,
                    notification_type=NotificationType.ALERT,
                    data={"metric": metric, "value": value, "alert_id": alert.alert_id}
                )

    def get_alert_history(self, alert_id: int | None = None,
                         limit: int = 100) -> list[dict[str, Any]]:
        """Get alert history."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        if alert_id:
            cursor.execute("""
                SELECT h.history_id, h.alert_id, a.name, h.triggered_at,
                       h.value, h.message
                FROM alert_history h
                JOIN alerts a ON h.alert_id = a.alert_id
                WHERE h.alert_id = ?
                ORDER BY h.triggered_at DESC LIMIT ?
            """, (alert_id, limit))
        else:
            cursor.execute("""
                SELECT h.history_id, h.alert_id, a.name, h.triggered_at,
                       h.value, h.message
                FROM alert_history h
                JOIN alerts a ON h.alert_id = a.alert_id
                ORDER BY h.triggered_at DESC LIMIT ?
            """, (limit,))

        history = []
        for row in cursor.fetchall():
            history.append({
                "history_id": row[0],
                "alert_id": row[1],
                "alert_name": row[2],
                "triggered_at": row[3],
                "value": row[4],
                "message": row[5],
            })

        conn.close()
        return history


# Streamlit integration
def init_notifications() -> None:
    """Initialize notification service in session state."""
    if "notification_service" not in st.session_state:
        st.session_state.notification_service = NotificationService()


def get_notification_service() -> NotificationService:
    """Get notification service instance."""
    init_notifications()
    return st.session_state.notification_service
