"""Alert dashboard UI for Phase 4."""

from __future__ import annotations

from solar_platform.alerts import AlertEngine, AlertRepository, AlertSeverity, AlertStateMachine, AlertStatus

import pandas as pd
import streamlit as st


def _to_df(alerts):
    return pd.DataFrame(
        [
            {
                "id": a.id,
                "plant_uid": a.plant_uid,
                "rule_id": a.rule_id,
                "severity": a.severity.value,
                "status": a.status.value,
                "title": a.title,
                "metric": a.metric_name,
                "value": a.metric_value,
                "threshold": a.threshold_value,
                "first_seen": a.first_seen,
                "last_seen": a.last_seen,
                "occurrences": a.occurrence_count,
                "ticket_id": a.ticket_id,
            }
            for a in alerts
        ]
    )


@st.cache_data(ttl=300)
def _cached_alerts_df(severity_val: str | None, status_val: str | None) -> pd.DataFrame:
    """Fetch alerts and return as DataFrame (cached)."""
    repo = AlertRepository()
    severity = AlertSeverity(severity_val) if severity_val else None
    status = AlertStatus(status_val) if status_val else None
    alerts = repo.list_alerts(severity=severity, status=status)
    return _to_df(alerts)


@st.cache_data(ttl=300)
def _cached_alert_metrics() -> tuple[int, int, int]:
    """Return (active_count, critical_active_count, total_count)."""
    repo = AlertRepository()
    active = len(repo.list_alerts(status=AlertStatus.ACTIVE))
    critical = len(repo.list_alerts(status=AlertStatus.ACTIVE, severity=AlertSeverity.CRITICAL))
    total = len(repo.list_alerts())
    return active, critical, total


def _clear_alert_caches() -> None:
    """Clear all alert caches after mutations."""
    _cached_alerts_df.clear()
    _cached_alert_metrics.clear()


def render() -> None:
    st.markdown("## 🚨 Alerts Dashboard")
    repo = AlertRepository()
    engine = AlertEngine(repository=repo)
    state = AlertStateMachine(repository=repo)

    c1, c2, c3 = st.columns(3)
    if c1.button("Evaluate All Rules", use_container_width=True):
        new_alerts = engine.evaluate_all()
        _clear_alert_caches()
        st.success(f"Evaluation complete. Triggered {len(new_alerts)} alerts.")

    if c2.button("Seed Default Rules", use_container_width=True):
        count = engine.seed_default_rules()
        st.success(f"Inserted {count} missing default rules.")

    sev = c3.selectbox("Severity", options=["all", "critical", "warning", "info"], index=0)

    status_filter = st.selectbox(
        "Status",
        options=["active", "acknowledged", "resolved", "suppressed", "all"],
        index=0,
    )

    sev_val = None if sev == "all" else sev
    status_val = None if status_filter == "all" else status_filter
    df = _cached_alerts_df(sev_val, status_val)

    active_count, critical_count, total_count = _cached_alert_metrics()
    m1, m2, m3 = st.columns(3)
    m1.metric("Active", active_count)
    m2.metric("Critical Active", critical_count)
    m3.metric("Total Alerts", total_count)

    if df.empty:
        st.info("No alerts for current filters.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Actions")
    for _, row in df.head(20).iterrows():
        with st.expander(f"{row['title']} | {row['plant_uid']} | {row['status']}"):
            b1, b2, b3 = st.columns(3)
            if b1.button("Acknowledge", key=f"ack_{row['id']}", disabled=row['status'] == 'resolved'):
                state.acknowledge(row['id'], user="ui")
                _clear_alert_caches()
                st.rerun()
            if b2.button("Resolve", key=f"res_{row['id']}"):
                state.resolve(row['id'], user="ui")
                _clear_alert_caches()
                st.rerun()
            if b3.button("Suppress", key=f"sup_{row['id']}"):
                state.suppress(row['id'])
                _clear_alert_caches()
                st.rerun()
