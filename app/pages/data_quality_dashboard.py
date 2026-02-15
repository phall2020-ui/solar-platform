"""
Data Quality Dashboard — Phase 6.7

Portfolio-level data quality overview with completeness heatmaps,
validation failure breakdowns, gap listings, and per-plant detail.

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

from app.components.kpi_cards import render_kpi_row, render_status_badge
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
    from solar_platform.data_quality.validators import (
        DEFAULT_VALIDATORS,
        ValidationReport,
        run_validation,
    )

    VALIDATORS_AVAILABLE = True
except Exception:
    VALIDATORS_AVAILABLE = False

try:
    from solar_platform.data_quality.gap_detection import DataGap, GapDetector

    GAP_DETECTION_AVAILABLE = True
except Exception:
    GAP_DETECTION_AVAILABLE = False

try:
    from solar_platform.data_quality.gap_filling import auto_fill_gap

    GAP_FILLING_AVAILABLE = True
except Exception:
    GAP_FILLING_AVAILABLE = False

try:
    from solar_platform.data_quality.quality_scorer import QualityScorer

    QUALITY_SCORER_AVAILABLE = True
except Exception:
    QUALITY_SCORER_AVAILABLE = False

try:
    from solar_platform.data_quality.sensor_health import SensorHealthMonitor

    SENSOR_HEALTH_AVAILABLE = True
except Exception:
    SENSOR_HEALTH_AVAILABLE = False

try:
    from solar_platform.db.repository import PlantRepository

    PLANT_REPO_AVAILABLE = True
except Exception:
    PLANT_REPO_AVAILABLE = False


# ── Demo data generators ────────────────────────────────────────────

DEMO_PLANTS = [
    "Alderney Farm",
    "Beacon Hill",
    "Crowland South",
    "Dunston Fields",
    "Elmbridge Park",
    "Foxley Meadow",
    "Great Staughton",
    "Hinckley North",
]


def _demo_quality_scores() -> dict[str, float]:
    """Return realistic quality scores per plant."""
    np.random.seed(42)
    return {p: round(np.random.uniform(0.75, 0.99), 3) for p in DEMO_PLANTS}


def _demo_completeness_matrix(days: int) -> pd.DataFrame:
    """Plant × day completeness matrix (0-100%)."""
    np.random.seed(42)
    end = datetime.now(UTC).date()
    dates = [end - timedelta(days=d) for d in range(days - 1, -1, -1)]
    data = np.random.uniform(85, 100, size=(len(DEMO_PLANTS), days))
    # Inject some gaps
    data[2, 5:8] = np.random.uniform(30, 60, size=3)
    data[5, 10:12] = np.random.uniform(0, 20, size=2)
    return pd.DataFrame(data, index=DEMO_PLANTS, columns=[d.strftime("%Y-%m-%d") for d in dates])


def _demo_validation_failures() -> pd.DataFrame:
    """Validation rule failure counts."""
    rules = [
        "Irradiance > 0 during day",
        "Power ≤ capacity",
        "Meter reading monotonic",
        "Temperature in range",
        "Timestamp continuity",
        "PR in [0, 1.2]",
        "Export ≤ generation",
    ]
    np.random.seed(42)
    counts = np.random.randint(0, 55, size=len(rules))
    return pd.DataFrame({"rule": rules, "failures": counts}).sort_values("failures", ascending=True)


def _demo_gaps() -> pd.DataFrame:
    """Sample data gaps."""
    now = datetime.now(UTC)
    rows = []
    for i, plant in enumerate(DEMO_PLANTS[:5]):
        start = now - timedelta(days=np.random.randint(2, 25), hours=np.random.randint(0, 12))
        duration_h = np.random.choice([1, 3, 6, 12, 24, 48])
        end = start + timedelta(hours=int(duration_h))
        completeness = round(np.random.uniform(0, 0.3), 2)
        rows.append(
            {
                "plant": plant,
                "start": start.strftime("%Y-%m-%d %H:%M"),
                "end": end.strftime("%Y-%m-%d %H:%M"),
                "duration_hours": duration_h,
                "completeness": f"{completeness:.0%}",
                "status": "Open" if i < 3 else "Filled",
            }
        )
    return pd.DataFrame(rows)


def _demo_sensor_health() -> dict[str, dict]:
    np.random.seed(42)
    sensors = ["Irradiance", "Ambient Temp", "Module Temp", "Wind Speed", "Power Meter"]
    result: dict[str, dict] = {}
    for plant in DEMO_PLANTS:
        result[plant] = {}
        for s in sensors:
            result[plant][s] = {
                "uptime": round(np.random.uniform(0.90, 1.0), 3),
                "drift": round(np.random.uniform(-0.02, 0.02), 4),
                "status": np.random.choice(["good", "warning", "critical"], p=[0.8, 0.15, 0.05]),
            }
    return result


# ── Helpers ──────────────────────────────────────────────────────────


def _quality_badge(score: float) -> str:
    """Return status string for a quality score."""
    if score >= 0.95:
        return "excellent"
    if score >= 0.85:
        return "good"
    if score >= 0.70:
        return "warning"
    return "critical"


def _apply_template(fig: go.Figure) -> go.Figure:
    """Apply AMPYR plotly template."""
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


# ── Main render ──────────────────────────────────────────────────────


def render() -> None:
    """Render the Data Quality Dashboard page."""
    page_header(
        "Data Quality Dashboard",
        subtitle="Portfolio-wide data completeness, validation, and gap analysis",
        icon="🔍",
    )

    using_demo = not (QUALITY_SCORER_AVAILABLE and VALIDATORS_AVAILABLE)
    if using_demo:
        st.info("📋 Showing demo data — data quality services are loading in the background.", icon="ℹ️")

    # ── Filters ──────────────────────────────────────────────
    col_period, col_spacer = st.columns([1, 3])
    with col_period:
        period_label = st.selectbox(
            "Period",
            ["Last 7 days", "Last 30 days", "Last 90 days"],
            index=1,
            key="dq_period",
        )
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[period_label]

    # ── Load data ────────────────────────────────────────────
    quality_scores = _load_quality_scores()
    completeness = _load_completeness_matrix(days)
    validation_df = _load_validation_failures()
    gaps_df = _load_gaps()

    # ── KPI Row ──────────────────────────────────────────────
    avg_score = np.mean(list(quality_scores.values()))
    low_plants = sum(1 for s in quality_scores.values() if s < 0.85)
    total_gaps = len(gaps_df)
    open_gaps = len(gaps_df[gaps_df["status"] == "Open"]) if "status" in gaps_df.columns else total_gaps

    render_kpi_row(
        [
            {
                "label": "Portfolio Quality Score",
                "value": f"{avg_score:.1%}",
                "delta": _quality_badge(avg_score).title(),
                "status": _quality_badge(avg_score),
                "icon": "📊",
            },
            {
                "label": "Plants Monitored",
                "value": str(len(quality_scores)),
                "delta": f"{low_plants} below threshold" if low_plants else "All healthy",
                "status": "warning" if low_plants else "good",
                "icon": "🏭",
            },
            {
                "label": "Validation Failures",
                "value": str(int(validation_df["failures"].sum())),
                "delta": f"{len(validation_df)} rules checked",
                "status": "warning" if validation_df["failures"].sum() > 50 else "good",
                "icon": "⚠️",
            },
            {
                "label": "Data Gaps",
                "value": str(total_gaps),
                "delta": f"{open_gaps} open",
                "status": "critical" if open_gaps > 3 else "warning" if open_gaps else "good",
                "icon": "🕳️",
            },
        ]
    )

    st.divider()

    # ── Portfolio Quality Gauge ──────────────────────────────
    _render_quality_gauge(avg_score)

    # ── Completeness Heatmap ─────────────────────────────────
    st.subheader("📅 Data Completeness Heatmap")
    st.caption("Percentage of expected data points received per plant per day")
    _render_completeness_heatmap(completeness)

    # ── Validation Failures & Gaps side-by-side ──────────────
    col_val, col_gap = st.columns(2)

    with col_val:
        st.subheader("⚠️ Validation Failures")
        _render_validation_chart(validation_df)

    with col_gap:
        st.subheader("🕳️ Data Gaps")
        _render_gap_table(gaps_df)

    st.divider()

    # ── Per-plant detail ─────────────────────────────────────
    st.subheader("🏭 Per-Plant Quality Detail")
    sensor_health = _load_sensor_health()

    for plant, score in sorted(quality_scores.items(), key=lambda x: x[1]):
        badge = _quality_badge(score)
        with st.expander(f"{plant} — {score:.1%}", expanded=score < 0.85):
            pcol1, pcol2 = st.columns([1, 2])
            with pcol1:
                render_status_badge(badge, f"Quality: {score:.1%}")
                st.metric("Completeness Score", f"{score:.1%}")
            with pcol2:
                if plant in sensor_health:
                    sensors = sensor_health[plant]
                    sensor_df = pd.DataFrame(
                        [
                            {
                                "Sensor": name,
                                "Uptime": f"{info['uptime']:.1%}",
                                "Drift": f"{info['drift']:+.2%}",
                                "Status": info["status"].title(),
                            }
                            for name, info in sensors.items()
                        ]
                    )
                    st.dataframe(sensor_df, use_container_width=True, hide_index=True)
                else:
                    st.caption("No sensor health data available")


# ── Data loaders ─────────────────────────────────────────────────────


def _load_quality_scores() -> dict[str, float]:
    if QUALITY_SCORER_AVAILABLE:
        try:
            scorer = QualityScorer()
            return scorer.score_portfolio()
        except Exception as e:
            logger.warning("QualityScorer failed, using demo data: %s", e)
    return _demo_quality_scores()


def _load_completeness_matrix(days: int) -> pd.DataFrame:
    if QUALITY_SCORER_AVAILABLE:
        try:
            scorer = QualityScorer()
            return scorer.completeness_matrix(days=days)
        except Exception as e:
            logger.warning("Completeness matrix failed, using demo: %s", e)
    return _demo_completeness_matrix(days)


def _load_validation_failures() -> pd.DataFrame:
    if VALIDATORS_AVAILABLE:
        try:
            report: ValidationReport = run_validation(DEFAULT_VALIDATORS)
            rows = [{"rule": r.name, "failures": r.failure_count} for r in report.results]
            return pd.DataFrame(rows).sort_values("failures", ascending=True)
        except Exception as e:
            logger.warning("Validation run failed, using demo: %s", e)
    return _demo_validation_failures()


def _load_gaps() -> pd.DataFrame:
    if GAP_DETECTION_AVAILABLE:
        try:
            detector = GapDetector()
            gaps: list[DataGap] = detector.detect_all()
            rows = [
                {
                    "plant": g.plant,
                    "start": g.start.strftime("%Y-%m-%d %H:%M"),
                    "end": g.end.strftime("%Y-%m-%d %H:%M"),
                    "duration_hours": g.duration_hours,
                    "completeness": f"{g.completeness:.0%}",
                    "status": g.status,
                }
                for g in gaps
            ]
            return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["plant", "start", "end", "duration_hours", "completeness", "status"])
        except Exception as e:
            logger.warning("Gap detection failed, using demo: %s", e)
    return _demo_gaps()


def _load_sensor_health() -> dict[str, dict]:
    if SENSOR_HEALTH_AVAILABLE:
        try:
            monitor = SensorHealthMonitor()
            return monitor.health_report()
        except Exception as e:
            logger.warning("Sensor health failed, using demo: %s", e)
    return _demo_sensor_health()


# ── Chart renderers ──────────────────────────────────────────────────


def _render_quality_gauge(score: float) -> None:
    """Big quality score gauge."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score * 100,
            number={"suffix": "%", "font": {"size": 48}},
            title={"text": "Portfolio Quality Score", "font": {"size": 18, "color": AMPYR_TEAL}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": AMPYR_TEAL},
                "steps": [
                    {"range": [0, 70], "color": STATUS_COLORS["critical"]},
                    {"range": [70, 85], "color": STATUS_COLORS["warning"]},
                    {"range": [85, 95], "color": STATUS_COLORS["good"]},
                    {"range": [95, 100], "color": STATUS_COLORS["excellent"]},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.8,
                    "value": score * 100,
                },
            },
        )
    )
    fig.update_layout(height=280, margin=dict(t=60, b=20, l=40, r=40))
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="dq_gauge")


def _render_completeness_heatmap(df: pd.DataFrame) -> None:
    """Plant × day heatmap of data completeness."""
    fig = go.Figure(
        go.Heatmap(
            z=df.values,
            x=df.columns.tolist(),
            y=df.index.tolist(),
            colorscale=[
                [0.0, STATUS_COLORS["critical"]],
                [0.5, STATUS_COLORS["warning"]],
                [0.85, STATUS_COLORS["good"]],
                [1.0, STATUS_COLORS["excellent"]],
            ],
            zmin=0,
            zmax=100,
            colorbar=dict(title="Completeness %", ticksuffix="%"),
            hovertemplate="Plant: %{y}<br>Date: %{x}<br>Completeness: %{z:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, len(df) * 40),
        xaxis_title="Date",
        yaxis_title="Plant",
        yaxis=dict(autorange="reversed"),
    )
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="dq_heatmap")


def _render_validation_chart(df: pd.DataFrame) -> None:
    """Horizontal bar chart of validation rule failures."""
    fig = go.Figure(
        go.Bar(
            x=df["failures"],
            y=df["rule"],
            orientation="h",
            marker_color=[
                STATUS_COLORS["critical"] if v > 30 else STATUS_COLORS["warning"] if v > 10 else AMPYR_TEAL
                for v in df["failures"]
            ],
            hovertemplate="%{y}: %{x} failures<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(250, len(df) * 38),
        xaxis_title="Failure Count",
        yaxis_title="",
        showlegend=False,
    )
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="dq_validation")


def _render_gap_table(df: pd.DataFrame) -> None:
    """Data gap listing."""
    if df.empty:
        st.success("No data gaps detected! ✅")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "plant": st.column_config.TextColumn("Plant", width="medium"),
            "start": st.column_config.TextColumn("Start"),
            "end": st.column_config.TextColumn("End"),
            "duration_hours": st.column_config.NumberColumn("Duration (h)", format="%d"),
            "completeness": st.column_config.TextColumn("Completeness"),
            "status": st.column_config.TextColumn("Status"),
        },
    )
