"""
Notification UI Components.
Provides notification center, alert management, and notification widgets.
"""

import pandas as pd
import streamlit as st

from services.auth_service import get_current_user
from services.notification_service import NotificationType, get_notification_service


def render_notification_badge():
    """Render notification badge in sidebar."""
    user = get_current_user()
    if user is None:
        return

    notification_service = get_notification_service()
    notifications = notification_service.get_notifications(
        user_id=user.user_id, unread_only=True, limit=10
    )

    unread_count = len(notifications)

    with st.sidebar:
        if unread_count > 0:
            st.markdown(f"### 🔔 Notifications ({unread_count})")
        else:
            st.markdown("### 🔔 Notifications")

        if st.button("View All Notifications", use_container_width=True):
            st.session_state.current_page = "Notifications"
            st.rerun()


def render_notification_center():
    """Render the notification center page."""
    user = get_current_user()
    if user is None:
        st.warning("Please log in to view notifications")
        return

    st.markdown("## 🔔 Notification Center")

    notification_service = get_notification_service()

    # Tabs for different views
    tab1, tab2 = st.tabs(["All Notifications", "Alerts"])

    with tab1:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            show_unread = st.checkbox("Unread only", value=False)
        with col2:
            if st.button("Mark all as read"):
                notification_service.mark_all_as_read(user.user_id)
                st.success("All notifications marked as read")
                st.rerun()
        with col3:
            limit = st.number_input("Show", min_value=10, max_value=500,
                                   value=50, step=10)

        notifications = notification_service.get_notifications(
            user_id=user.user_id,
            unread_only=show_unread,
            limit=limit
        )

        if notifications:
            for notif in notifications:
                icon_map = {
                    NotificationType.INFO: "ℹ️",
                    NotificationType.WARNING: "⚠️",
                    NotificationType.ERROR: "❌",
                    NotificationType.SUCCESS: "✅",
                    NotificationType.ALERT: "🚨",
                }
                icon = icon_map.get(notif.notification_type, "📬")

                status_badge = "" if notif.is_read else "🔵 "

                with st.expander(
                    f"{status_badge}{icon} {notif.title} - {notif.created_at}",
                    expanded=not notif.is_read
                ):
                    st.markdown(notif.message)

                    if notif.data:
                        with st.container():
                            st.json(notif.data)

                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if not notif.is_read:
                            if st.button("Mark as read",
                                       key=f"read_{notif.notification_id}"):
                                notification_service.mark_as_read(notif.notification_id)
                                st.rerun()
                    with col2:
                        if st.button("Delete", key=f"del_{notif.notification_id}"):
                            notification_service.delete_notification(notif.notification_id)
                            st.rerun()
        else:
            st.info("No notifications to display")

    with tab2:
        render_alert_management()


def render_alert_management():
    """Render alert management interface."""
    user = get_current_user()
    notification_service = get_notification_service()

    st.markdown("### Alert Rules")

    # Show existing alerts
    alerts = notification_service.get_alerts(active_only=False)

    if alerts:
        alert_data = []
        for alert in alerts:
            alert_data.append({
                "ID": alert.alert_id,
                "Name": alert.name,
                "Metric": alert.metric,
                "Condition": f"{alert.condition} {alert.threshold}",
                "Active": "✓" if alert.is_active else "✗",
            })

        df = pd.DataFrame(alert_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Edit Alert")

        selected_alert_id = st.selectbox(
            "Select Alert to Edit",
            options=[a.alert_id for a in alerts],
            format_func=lambda x: next(a.name for a in alerts if a.alert_id == x)
        )

        selected_alert = next(a for a in alerts if a.alert_id == selected_alert_id)

        with st.form("edit_alert_form"):
            name = st.text_input("Name", value=selected_alert.name)
            description = st.text_area("Description", value=selected_alert.description)
            metric = st.text_input("Metric", value=selected_alert.metric)
            condition = st.selectbox(
                "Condition",
                options=["<", ">", "<=", ">=", "==", "!="],
                index=["<", ">", "<=", ">=", "==", "!="].index(selected_alert.condition)
            )
            threshold = st.number_input("Threshold", value=float(selected_alert.threshold))
            is_active = st.checkbox("Active", value=selected_alert.is_active)

            if st.form_submit_button("Update Alert"):
                notification_service.update_alert(
                    selected_alert_id,
                    name=name,
                    description=description,
                    metric=metric,
                    condition=condition,
                    threshold=threshold,
                    is_active=is_active
                )
                st.success("Alert updated!")
                st.rerun()

    st.markdown("---")
    st.markdown("### Create New Alert")

    with st.form("create_alert_form"):
        new_name = st.text_input("Alert Name")
        new_description = st.text_area("Description")
        new_metric = st.selectbox(
            "Metric",
            options=["pr", "availability", "clipping_loss", "soiling_loss",
                    "shading_loss", "thermal_loss", "energy_production"]
        )
        new_condition = st.selectbox("Condition", options=["<", ">", "<=", ">=", "==", "!="])
        new_threshold = st.number_input("Threshold", value=0.0)

        if st.form_submit_button("Create Alert"):
            if not new_name:
                st.error("Alert name is required")
            else:
                notification_service.create_alert(
                    new_name,
                    new_description,
                    new_metric,
                    new_condition,
                    new_threshold,
                    created_by=user.user_id if user else None
                )
                st.success(f"Alert '{new_name}' created!")
                st.rerun()

    st.markdown("---")
    st.markdown("### Alert History")

    history = notification_service.get_alert_history(limit=50)

    if history:
        history_df = pd.DataFrame(history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("No alert history available")


def show_notification_toast(title: str, message: str,
                           notification_type: str = NotificationType.INFO):
    """Show a toast notification."""
    type_map = {
        NotificationType.INFO: st.info,
        NotificationType.WARNING: st.warning,
        NotificationType.ERROR: st.error,
        NotificationType.SUCCESS: st.success,
        NotificationType.ALERT: st.warning,
    }

    display_func = type_map.get(notification_type, st.info)
    display_func(f"**{title}**: {message}")


def send_system_notification(title: str, message: str,
                            notification_type: str = NotificationType.INFO,
                            user_id: int | None = None):
    """Send a system notification to a user or all users."""
    notification_service = get_notification_service()
    notification_service.create_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type
    )
