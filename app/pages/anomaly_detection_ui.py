"""
Anomaly Detection UI — Phase 7.9

Interactive anomaly explorer with scatter timeline, method/confidence
filters, and detail drill-down for each detected anomaly.

Entry point: render()
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.kpi_cards import render_kpi_row
from app.components.layouts import page_header
from app.styles.design_tokens import (
    AMPYR_TEAL,
    AMPYR_TEAL_LIGHT,
    CHART_COLORS,
    PLOTLY_TEMPLATE,
    STATUS_COLORS,
)

logger = logging.getLogger(__name__)

# ── Service imports (guarded) ───────────────────────────────────────

try:
    from solar_platform.analytics.anomaly_detection import (
        Anomaly,
        AnomalyService,
        AnomalyType,
    )

    ANOMALY_SERVICE_AVAILABLE = True
except Exception:
    ANOMALY_SERVICE_AVAILABLE = False

try:
    from solar_platform.db.repository import PlantRepository

    PLANT_REPO_AVAILABLE = True
except Exception:
    PLANT_REPO_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────

ANOMALY_METHODS = ["All", "Statistical", "Isolation Forest", "Contextual"]

ANOMALY_TYPE_COLORS = {
    "Statistical": CHART_COLORS[2],   # red
    "Isolation Forest": CHART_COLORS[4],  # blue
    "Contextual": CHART_COLORS[6],    # purple
    "Unknown": STATUS_COLORS["offline"],
}

DEMO_PLANTS = [
    "Alderney Farm",
    "Beacon Hill",
    "Crowland South",
    "Dunston Fields",
    "Elmbridge Park",
]


# ── Demo data ────────────────────────────────────────────────────────


def _demo_plant_list() -> list[str]:
    return DEMO_PLANTS


def _demo_anomalies(plant: str, days: int, method: str, min_confidence: float) -> pd.DataFrame:
    """Generate synthetic anomaly data for demonstration."""
    np.random.seed(hash(plant) % 2**31)
    n_anomalies = np.random.randint(8, 25)
    now = datetime.now(UTC)

    rows = []
    for i in range(n_anomalies):
        ts = now - timedelta(
            days=np.random.randint(0, days),
            hours=np.random.randint(6, 18),
            minutes=np.random.randint(0, 60),
        )
        atype = np.random.choice(["Statistical", "Isolation Forest", "Contextual"])
        confidence = round(np.random.uniform(0.45, 0.99), 2)
        metric = np.random.choice(["Power (kW)", "Irradiance (W/m²)", "PR (%)", "Temperature (°C)"])
        expected = round(np.random.uniform(50, 500), 1)
        deviation = round(np.random.uniform(0.15, 0.6), 2)
        actual = round(expected * (1 + np.random.choice([-1, 1]) * deviation), 1)

        rows.append(
            {
                "plant": plant,
                "timestamp": ts,
                "type": atype,
                "confidence": confidence,
                "metric": metric,
                "expected": expected,
                "actual": actual,
                "deviation_pct": round(abs(actual - expected) / max(expected, 0.01) * 100, 1),
                "description": f"{metric} deviated {deviation:.0%} from expected at {ts.strftime('%H:%M')}",
            }
        )

    df = pd.DataFrame(rows)

    # Apply filters
    if method != "All":
        df = df[df["type"] == method]
    df = df[df["confidence"] >= min_confidence]

    return df.sort_values("timestamp", ascending=False).reset_index(drop=True)


def _demo_metric_timeseries(plant: str, days: int) -> pd.DataFrame:
    """Generate a synthetic power timeseries with anomalous points flagged."""
    np.random.seed(hash(plant) % 2**31 + 1)
    n_points = days * 24
    now = datetime.now(UTC)
    timestamps = [now - timedelta(hours=i) for i in range(n_points - 1, -1, -1)]
    hours = np.array([t.hour for t in timestamps])

    # Solar generation curve
    power = np.where(
        (hours >= 6) & (hours <= 20),
        np.sin(np.pi * (hours - 6) / 14) * np.random.uniform(80, 120, size=n_points) + np.random.normal(0, 5, n_points),
        np.random.normal(0, 1, n_points).clip(0),
    )
    power = np.clip(power, 0, None)

    # Inject anomalies
    anomaly_mask = np.zeros(n_points, dtype=bool)
    n_anom = max(3, int(n_points * 0.02))
    anom_indices = np.random.choice(range(n_points), size=n_anom, replace=False)
    for idx in anom_indices:
        power[idx] *= np.random.choice([0.1, 2.5, 3.0])
        anomaly_mask[idx] = True

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "power_kw": np.round(power, 1),
            "is_anomaly": anomaly_mask,
        }
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def _severity_status(confidence: float) -> str:
    if confidence >= 0.9:
        return "critical"
    if confidence >= 0.7:
        return "warning"
    return "good"


# ── Main render ──────────────────────────────────────────────────────


def render() -> None:
    """Render the Anomaly Detection UI page."""
    page_header(
        "Anomaly Detection",
        subtitle="Identify and investigate anomalous readings across the portfolio",
        icon="🔎",
    )

    using_demo = not ANOMALY_SERVICE_AVAILABLE
    if using_demo:
        st.info("📋 Showing demo data — anomaly detection service is loading in the background.", icon="ℹ️")

    # ── Filters ──────────────────────────────────────────────
    plant_list = _get_plant_list()

    col_plant, col_period, col_method, col_conf = st.columns([2, 1, 1, 1])

    with col_plant:
        selected_plant = st.selectbox("Plant", plant_list, key="anom_plant")

    with col_period:
        period_label = st.selectbox(
            "Period",
            ["Last 7 days", "Last 30 days", "Last 90 days"],
            index=1,
            key="anom_period",
        )

    with col_method:
        method = st.selectbox("Method", ANOMALY_METHODS, key="anom_method")

    with col_conf:
        min_confidence = st.slider(
            "Min Confidence",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            key="anom_conf",
        )

    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[period_label]

    # ── Load data ────────────────────────────────────────────
    anomalies_df = _load_anomalies(selected_plant, days, method, min_confidence)
    timeseries_df = _load_timeseries(selected_plant, days)

    # ── KPI Row ──────────────────────────────────────────────
    total = len(anomalies_df)
    high_conf = len(anomalies_df[anomalies_df["confidence"] >= 0.8]) if not anomalies_df.empty else 0
    avg_conf = anomalies_df["confidence"].mean() if not anomalies_df.empty else 0.0
    types_found = anomalies_df["type"].nunique() if not anomalies_df.empty else 0

    render_kpi_row(
        [
            {
                "label": "Total Anomalies",
                "value": str(total),
                "delta": f"in last {days}d",
                "status": "critical" if total > 15 else "warning" if total > 5 else "good",
                "icon": "🔴",
            },
            {
                "label": "High Confidence",
                "value": str(high_conf),
                "delta": f"≥ 80% confidence",
                "status": "critical" if high_conf > 5 else "warning" if high_conf > 0 else "good",
                "icon": "⚡",
            },
            {
                "label": "Avg Confidence",
                "value": f"{avg_conf:.0%}",
                "status": _severity_status(avg_conf),
                "icon": "📈",
            },
            {
                "label": "Detection Methods",
                "value": str(types_found),
                "delta": f"of {len(ANOMALY_METHODS) - 1} available",
                "status": "good",
                "icon": "🧪",
            },
        ]
    )

    st.divider()

    # ── Timeline scatter chart ───────────────────────────────
    st.subheader("📈 Anomaly Timeline")
    _render_timeline_scatter(timeseries_df, anomalies_df, selected_plant)

    # ── Anomaly table ────────────────────────────────────────
    st.subheader("📋 Anomaly List")
    _render_anomaly_table(anomalies_df)

    # ── Detail drill-down ────────────────────────────────────
    if not anomalies_df.empty:
        st.subheader("🔬 Anomaly Detail")
        _render_anomaly_detail(anomalies_df)


# ── Data loaders ─────────────────────────────────────────────────────


def _get_plant_list() -> list[str]:
    if PLANT_REPO_AVAILABLE:
        try:
            repo = PlantRepository()
            aliases = repo.list_aliases()
            if aliases:
                return aliases
        except Exception as e:
            logger.warning("PlantRepository failed: %s", e)
    return _demo_plant_list()


def _load_anomalies(plant: str, days: int, method: str, min_confidence: float) -> pd.DataFrame:
    if ANOMALY_SERVICE_AVAILABLE:
        try:
            svc = AnomalyService()
            anomalies: list[Anomaly] = svc.detect(
                plant=plant,
                days=days,
                method=method if method != "All" else None,
                min_confidence=min_confidence,
            )
            if anomalies:
                rows = [
                    {
                        "plant": a.plant,
                        "timestamp": a.timestamp,
                        "type": a.anomaly_type.value if hasattr(a.anomaly_type, "value") else str(a.anomaly_type),
                        "confidence": a.confidence,
                        "metric": a.metric,
                        "expected": a.expected,
                        "actual": a.actual,
                        "deviation_pct": a.deviation_pct,
                        "description": a.description,
                    }
                    for a in anomalies
                ]
                return pd.DataFrame(rows)
        except Exception as e:
            logger.warning("AnomalyService failed, using demo: %s", e)
    return _demo_anomalies(plant, days, method, min_confidence)


def _load_timeseries(plant: str, days: int) -> pd.DataFrame:
    if ANOMALY_SERVICE_AVAILABLE:
        try:
            svc = AnomalyService()
            return svc.timeseries(plant=plant, days=days)
        except Exception:
            pass
    return _demo_metric_timeseries(plant, days)


# ── Chart renderers ──────────────────────────────────────────────────


def _render_timeline_scatter(ts_df: pd.DataFrame, anom_df: pd.DataFrame, plant: str) -> None:
    """Power timeseries with anomaly overlay."""
    fig = go.Figure()

    # Normal points
    normal = ts_df[~ts_df["is_anomaly"]]
    fig.add_trace(
        go.Scattergl(
            x=normal["timestamp"],
            y=normal["power_kw"],
            mode="lines",
            name="Power (kW)",
            line=dict(color=AMPYR_TEAL, width=1),
            opacity=0.6,
        )
    )

    # Anomaly points from timeseries
    anom_points = ts_df[ts_df["is_anomaly"]]
    fig.add_trace(
        go.Scatter(
            x=anom_points["timestamp"],
            y=anom_points["power_kw"],
            mode="markers",
            name="Anomaly (timeseries)",
            marker=dict(
                color=STATUS_COLORS["critical"],
                size=10,
                symbol="x",
                line=dict(width=1, color="white"),
            ),
        )
    )

    # Overlay anomalies from detection with type coloring
    if not anom_df.empty and "timestamp" in anom_df.columns:
        for atype, color in ANOMALY_TYPE_COLORS.items():
            subset = anom_df[anom_df["type"] == atype]
            if subset.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=subset["timestamp"],
                    y=subset["actual"],
                    mode="markers",
                    name=atype,
                    marker=dict(
                        color=color,
                        size=subset["confidence"] * 18 + 5,
                        opacity=0.8,
                        line=dict(width=1, color="white"),
                    ),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Time: %{x}<br>"
                        "Value: %{y:.1f}<br>"
                        "<extra></extra>"
                    ),
                    text=subset["metric"],
                )
            )

    fig.update_layout(
        height=400,
        xaxis_title="Time",
        yaxis_title="Power (kW)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="closest",
    )
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="anom_timeline")


def _render_anomaly_table(df: pd.DataFrame) -> None:
    """Anomaly list with formatted columns."""
    if df.empty:
        st.success("No anomalies detected for the selected filters. ✅")
        return

    display_df = df.copy()
    if "timestamp" in display_df.columns:
        display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")

    st.dataframe(
        display_df[["plant", "timestamp", "type", "confidence", "metric", "expected", "actual", "deviation_pct"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "plant": st.column_config.TextColumn("Plant", width="medium"),
            "timestamp": st.column_config.TextColumn("Time"),
            "type": st.column_config.TextColumn("Method"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1, format="%.0%%"),
            "metric": st.column_config.TextColumn("Metric"),
            "expected": st.column_config.NumberColumn("Expected", format="%.1f"),
            "actual": st.column_config.NumberColumn("Actual", format="%.1f"),
            "deviation_pct": st.column_config.NumberColumn("Deviation %", format="%.1f%%"),
        },
    )


def _render_anomaly_detail(df: pd.DataFrame) -> None:
    """Click-to-detail for individual anomalies."""
    if df.empty:
        return

    options = [
        f"{row['timestamp'].strftime('%Y-%m-%d %H:%M') if isinstance(row['timestamp'], datetime) else row['timestamp']} — {row['metric']} ({row['type']})"
        for _, row in df.head(20).iterrows()
    ]

    selected_idx = st.selectbox(
        "Select anomaly to inspect",
        range(len(options)),
        format_func=lambda i: options[i],
        key="anom_detail_select",
    )

    row = df.iloc[selected_idx]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Metric", row["metric"])
        st.metric("Detection Method", row["type"])
    with col2:
        st.metric("Expected", f"{row['expected']:.1f}")
        st.metric("Actual", f"{row['actual']:.1f}")
    with col3:
        st.metric("Confidence", f"{row['confidence']:.0%}")
        st.metric("Deviation", f"{row['deviation_pct']:.1f}%")

    if "description" in row.index and row["description"]:
        st.caption(f"💡 {row['description']}")
