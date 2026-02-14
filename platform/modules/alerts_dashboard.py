"""Alert dashboard UI for Phase 4."""

from __future__ import annotations

from services.alerts import AlertEngine, AlertRepository, AlertSeverity, AlertStateMachine, AlertStatus

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


def render() -> None:
    st.markdown("## 🚨 Alerts Dashboard")
    repo = AlertRepository()
    engine = AlertEngine(repository=repo)
    state = AlertStateMachine(repository=repo)

    c1, c2, c3 = st.columns(3)
    if c1.button("Evaluate All Rules", use_container_width=True):
        new_alerts = engine.evaluate_all()
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

    severity = None if sev == "all" else AlertSeverity(sev)
    status = None if status_filter == "all" else AlertStatus(status_filter)

    alerts = repo.list_alerts(severity=severity, status=status)
    df = _to_df(alerts)

    m1, m2, m3 = st.columns(3)
    m1.metric("Active", len(repo.list_alerts(status=AlertStatus.ACTIVE)))
    m2.metric("Critical Active", len(repo.list_alerts(status=AlertStatus.ACTIVE, severity=AlertSeverity.CRITICAL)))
    m3.metric("Total Alerts", len(repo.list_alerts()))

    if df.empty:
        st.info("No alerts for current filters.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Actions")
    for alert in alerts[:20]:
        with st.expander(f"{alert.title} | {alert.plant_uid} | {alert.status.value}"):
            b1, b2, b3 = st.columns(3)
            if b1.button("Acknowledge", key=f"ack_{alert.id}", disabled=alert.status == AlertStatus.RESOLVED):
                state.acknowledge(alert.id, user="ui")
                st.rerun()
            if b2.button("Resolve", key=f"res_{alert.id}"):
                state.resolve(alert.id, user="ui")
                st.rerun()
            if b3.button("Suppress", key=f"sup_{alert.id}"):
                state.suppress(alert.id)
                st.rerun()
