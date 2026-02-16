"""
Tariff Management UI — Phase 7.4

View, add, edit, and import tariff configurations per plant.

Entry point: render()
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import streamlit as st

from app.components.kpi_cards import render_kpi_row
from app.components.layouts import page_header
from app.styles.design_tokens import AMPYR_TEAL, PLOTLY_TEMPLATE, STATUS_COLORS

logger = logging.getLogger(__name__)

# ── Service imports (guarded) ───────────────────────────────────────

try:
    from solar_platform.financial.tariff import TariffManager

    TARIFF_AVAILABLE = True
except Exception:
    TARIFF_AVAILABLE = False

try:
    from solar_platform.db.repository import PlantRepository

    PLANT_REPO_AVAILABLE = True
except Exception:
    PLANT_REPO_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────

TARIFF_TYPES = ["Fixed PPA", "ROC", "FiT", "CfD", "Merchant", "Indexed PPA"]

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


# ── Demo data ────────────────────────────────────────────────────────


def _demo_tariff_history(plant: str) -> pd.DataFrame:
    """Synthetic tariff history for a plant."""
    np.random.seed(hash(plant) % 2**31)
    n = np.random.randint(2, 6)
    rows = []
    start = date(2020, 1, 1)
    for i in range(n):
        tariff_type = np.random.choice(TARIFF_TYPES)
        rate = round(np.random.uniform(35, 90), 2)
        escalation = round(np.random.uniform(0, 3.5), 2)
        end_date = date(start.year + np.random.randint(1, 4), start.month, 1)
        rows.append(
            {
                "tariff_type": tariff_type,
                "rate_per_mwh": rate,
                "start_date": start.isoformat(),
                "end_date": end_date.isoformat(),
                "escalation_pct": escalation,
                "status": "Expired" if end_date < date.today() else "Active",
            }
        )
        start = end_date
    return pd.DataFrame(rows)


def _demo_current_tariff(plant: str) -> dict:
    np.random.seed(hash(plant) % 2**31 + 7)
    return {
        "tariff_type": np.random.choice(TARIFF_TYPES),
        "rate_per_mwh": round(np.random.uniform(45, 80), 2),
        "start_date": "2024-04-01",
        "end_date": "2027-03-31",
        "escalation_pct": round(np.random.uniform(1.0, 3.0), 2),
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _get_plant_list() -> list[str]:
    if PLANT_REPO_AVAILABLE:
        try:
            repo = PlantRepository()
            aliases = repo.list_aliases()
            if aliases:
                return aliases
        except Exception as e:
            logger.warning("PlantRepository failed: %s", e)
    return DEMO_PLANTS


# ── Main render ──────────────────────────────────────────────────────


def render() -> None:
    """Render the Tariff Management page."""
    page_header(
        "Tariff Management",
        subtitle="View and configure tariff rates, escalation, and history per plant",
        icon="📜",
    )

    using_demo = not TARIFF_AVAILABLE
    if using_demo:
        st.info("📋 Showing demo data — tariff management service is loading in the background.", icon="ℹ️")

    # ── Plant selector ───────────────────────────────────────
    plant_list = _get_plant_list()
    selected_plant = st.selectbox("Select Plant", plant_list, key="tariff_plant")

    st.divider()

    # ── Current Tariff ───────────────────────────────────────
    current = _load_current_tariff(selected_plant)
    st.subheader("⚡ Current Tariff")
    _render_current_tariff(current)

    st.divider()

    # ── Add / Edit Tariff ────────────────────────────────────
    st.subheader("➕ Add / Edit Tariff")
    _render_tariff_form(selected_plant)

    st.divider()

    # ── Tariff History ───────────────────────────────────────
    st.subheader("📋 Tariff History")
    history_df = _load_tariff_history(selected_plant)
    _render_tariff_history(history_df)

    st.divider()

    # ── CSV Import ───────────────────────────────────────────
    st.subheader("📁 Import Tariffs from CSV")
    _render_csv_import()


# ── Data loaders ─────────────────────────────────────────────────────


def _load_current_tariff(plant: str) -> dict:
    if TARIFF_AVAILABLE:
        try:
            mgr = TariffManager()
            # Resolve alias → plant_uid
            plant_uid = plant
            if PLANT_REPO_AVAILABLE:
                try:
                    repo = PlantRepository()
                    p = repo.get_by_alias(plant)
                    if p:
                        plant_uid = p["plant_uid"]
                except Exception:
                    pass

            result = mgr.get_tariff(plant_uid)
            if result:
                return {
                    "tariff_type": result.get("tariff_type", "—"),
                    "rate_per_mwh": result.get("rate", 0.0),
                    "start_date": str(result.get("start_date", "—")),
                    "end_date": str(result.get("end_date", "—")),
                    "escalation_pct": result.get("escalation_pct", 0.0),
                }
        except Exception as e:
            logger.warning("TariffManager.get_tariff failed: %s", e)
    return _demo_current_tariff(plant)


def _load_tariff_history(plant: str) -> pd.DataFrame:
    if TARIFF_AVAILABLE:
        try:
            mgr = TariffManager()
            # Resolve alias → plant_uid
            plant_uid = plant
            if PLANT_REPO_AVAILABLE:
                try:
                    repo = PlantRepository()
                    p = repo.get_by_alias(plant)
                    if p:
                        plant_uid = p["plant_uid"]
                except Exception:
                    pass

            # Query tariff history directly from the engine
            if mgr.engine.table_exists("plant_tariffs"):
                rows = mgr.engine.execute(
                    "SELECT tariff_type, rate, start_date, end_date, escalation_pct "
                    "FROM plant_tariffs WHERE plant_uid = ? ORDER BY start_date DESC",
                    (plant_uid,),
                )
                if rows:
                    history = []
                    for row in rows:
                        end_d = row[3]
                        history.append({
                            "tariff_type": row[0],
                            "rate_per_mwh": float(row[1]),
                            "start_date": str(row[2]),
                            "end_date": str(end_d) if end_d else "—",
                            "escalation_pct": float(row[4]) if row[4] else 0.0,
                            "status": "Active" if (end_d is None or end_d >= date.today()) else "Expired",
                        })
                    return pd.DataFrame(history)
        except Exception as e:
            logger.warning("TariffManager.history failed: %s", e)
    return _demo_tariff_history(plant)


# ── UI sections ──────────────────────────────────────────────────────


def _render_current_tariff(tariff: dict) -> None:
    """Display current tariff as KPI cards."""
    render_kpi_row(
        [
            {
                "label": "Tariff Type",
                "value": tariff.get("tariff_type", "—"),
                "status": "good",
                "icon": "📄",
            },
            {
                "label": "Rate",
                "value": f"£{tariff.get('rate_per_mwh', 0):.2f}/MWh",
                "status": "good",
                "icon": "💷",
            },
            {
                "label": "Period",
                "value": f"{tariff.get('start_date', '—')} → {tariff.get('end_date', '—')}",
                "status": "good",
                "icon": "📅",
            },
            {
                "label": "Escalation",
                "value": f"{tariff.get('escalation_pct', 0):.2f}% p.a.",
                "status": "good",
                "icon": "📈",
            },
        ]
    )


def _render_tariff_form(plant: str) -> None:
    """Form to add or edit a tariff entry."""
    with st.form(key="tariff_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            tariff_type = st.selectbox("Tariff Type", TARIFF_TYPES, key="form_type")
            rate = st.number_input(
                "Rate (£/MWh)",
                min_value=0.0,
                max_value=500.0,
                value=55.0,
                step=0.5,
                key="form_rate",
            )
        with col2:
            start_date = st.date_input("Start Date", value=date.today(), key="form_start")
            end_date = st.date_input(
                "End Date",
                value=date(date.today().year + 2, date.today().month, 1),
                key="form_end",
            )

        escalation = st.number_input(
            "Annual Escalation (%)",
            min_value=0.0,
            max_value=20.0,
            value=2.0,
            step=0.1,
            key="form_escalation",
        )

        submitted = st.form_submit_button("💾 Save Tariff", use_container_width=True)

        if submitted:
            if end_date <= start_date:
                st.error("End date must be after start date.")
            else:
                tariff_data = {
                    "plant": plant,
                    "tariff_type": tariff_type,
                    "rate_per_mwh": rate,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "escalation_pct": escalation,
                }
                if TARIFF_AVAILABLE:
                    try:
                        mgr = TariffManager()
                        mgr.save(tariff_data)
                        st.success(f"✅ Tariff saved for {plant}")
                    except Exception as e:
                        st.error(f"Failed to save: {e}")
                else:
                    st.success(f"✅ Tariff would be saved for {plant} (demo mode)")
                    st.json(tariff_data)


def _render_tariff_history(df: pd.DataFrame) -> None:
    """Table of historical tariff records."""
    if df.empty:
        st.caption("No tariff history available.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "tariff_type": st.column_config.TextColumn("Type", width="medium"),
            "rate_per_mwh": st.column_config.NumberColumn("Rate (£/MWh)", format="£%.2f"),
            "start_date": st.column_config.TextColumn("Start"),
            "end_date": st.column_config.TextColumn("End"),
            "escalation_pct": st.column_config.NumberColumn("Escalation %", format="%.2f%%"),
            "status": st.column_config.TextColumn("Status"),
        },
    )


def _render_csv_import() -> None:
    """CSV file uploader for bulk tariff import."""
    st.caption(
        "Upload a CSV with columns: `plant`, `tariff_type`, `rate_per_mwh`, "
        "`start_date`, `end_date`, `escalation_pct`"
    )
    uploaded = st.file_uploader(
        "Choose CSV file",
        type=["csv"],
        key="tariff_csv_upload",
        help="CSV must contain columns: plant, tariff_type, rate_per_mwh, start_date, end_date, escalation_pct",
    )

    if uploaded is not None:
        try:
            csv_df = pd.read_csv(uploaded)
            required_cols = {"plant", "tariff_type", "rate_per_mwh", "start_date", "end_date"}
            missing = required_cols - set(csv_df.columns)
            if missing:
                st.error(f"Missing required columns: {', '.join(sorted(missing))}")
                return

            st.success(f"✅ Parsed {len(csv_df)} tariff records")
            st.dataframe(csv_df, use_container_width=True, hide_index=True)

            if st.button("📥 Import All", key="tariff_import_btn"):
                if TARIFF_AVAILABLE:
                    try:
                        mgr = TariffManager()
                        mgr.bulk_import(csv_df.to_dict("records"))
                        st.success(f"✅ Imported {len(csv_df)} tariff records")
                    except Exception as e:
                        st.error(f"Import failed: {e}")
                else:
                    st.success(f"✅ Would import {len(csv_df)} records (demo mode)")
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")
