"""POA Import — import SolarGIS irradiance data into the platform database."""
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import duckdb
import pandas as pd
import streamlit as st

from components import drag_drop_uploader
from solar_platform.services.data_pull import JuggleDataPullService

logger = logging.getLogger(__name__)


def _get_service() -> JuggleDataPullService:
    return JuggleDataPullService()


def _fuzzy_match_to_plant(filename: str, plant_aliases: list, threshold: float = 0.5) -> str | None:
    """Find best matching plant alias for a filename."""
    base_name = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
    best_match = None
    best_score = 0.0
    for alias in plant_aliases:
        alias_lower = alias.lower().replace("_", " ").replace("-", " ")
        score = SequenceMatcher(None, base_name, alias_lower).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = alias
    return best_match


def _import_poa_csv(svc: JuggleDataPullService, plant_alias: str, plant_uid: str, csv_path: str) -> int:
    """
    Import a SolarGIS CSV file as POA readings into the platform database.

    Reads the CSV, extracts the GTI/GHI/POA column, converts to half-hourly
    readings and stores them via the data pull service.

    Returns count of readings stored.
    """
    df = pd.read_csv(csv_path)

    # Find the time column
    cols_lower = {c.lower(): c for c in df.columns}
    time_col = None
    for candidate in ["time", "date & time", "timestamp", "datetime", "date"]:
        if candidate in cols_lower:
            time_col = cols_lower[candidate]
            break

    if time_col is None:
        raise ValueError(f"No time column found. Columns: {list(df.columns)}")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    df = df.dropna(subset=[time_col])

    # Find the POA / GTI irradiance column
    poa_col = None
    for candidate in ["gti", "poa", "poa_irradiance", "ghi", "irradiance"]:
        if candidate in cols_lower:
            poa_col = cols_lower[candidate]
            break

    if poa_col is None:
        raise ValueError(f"No irradiance column (GTI/POA/GHI) found. Columns: {list(df.columns)}")

    # Aggregate by timestamp and resample to 30-minute intervals if needed
    df = df[[time_col, poa_col]].copy()
    df = df.rename(columns={time_col: "time", poa_col: "poa"})
    df["poa"] = pd.to_numeric(df["poa"], errors="coerce")
    df = df.dropna(subset=["poa"])

    # If sub-hourly data, group and average
    df = df.groupby("time", as_index=False)["poa"].mean()
    df = df.set_index("time").sort_index()

    # Create POA device ID
    poa_emig_id = f"POA:{plant_alias.replace(' ', '_').upper()}"

    # Convert to readings format
    readings = []
    for ts, row in df.iterrows():
        poa_value = row["poa"]
        if pd.isna(poa_value) or poa_value < 0:
            continue
        readings.append({
            "ts": ts.isoformat(),
            "emigId": poa_emig_id,
            "poaIrradiance": {"value": float(poa_value), "unit": "W/m2"},
        })

    if not readings:
        return 0

    # Store using the data pull service's internal method
    count = svc._store_readings(plant_uid, readings)
    logger.info("Imported %d POA readings for %s (%s)", count, plant_alias, poa_emig_id)
    return count


def render():
    """Render the POA Import page."""
    st.header("Import SolarGIS POA Data")
    st.markdown(
        """
        Import POA (Plane of Array) irradiance data from SolarGIS CSV files.
        POA data covers the entire system and will be stored separately from inverter readings
        but can be joined for analysis using aligned timestamps.
        """
    )

    svc = _get_service()
    plant_list = svc.get_registered_plants()
    plant_aliases = [p["alias"] for p in plant_list]

    if not plant_list:
        st.warning("No plants registered. Register plants via Plant Management first.")
        return

    # --- UI Start ---
    import_mode = st.radio("Import Mode", ["Upload File(s)", "From Folder Path"], horizontal=True)

    if import_mode == "Upload File(s)":
        with st.container(border=True):
            st.markdown(
                "Upload one or more SolarGIS CSV files. "
                "Files will be auto-matched to registered plants based on filename."
            )
            uploaded_poa_files = drag_drop_uploader(
                "Upload SolarGIS CSV File(s)",
                type=["csv"],
                accept_multiple_files=True,
                key="poa_file_upload",
                help="Select one or more SolarGIS CSV files",
            )

        if uploaded_poa_files:
            st.info(f"📁 {len(uploaded_poa_files)} file(s) uploaded")

            st.subheader("File to Plant Mapping")
            st.markdown(
                "Auto-matched based on filename. Override manually if needed. "
                "**All data in the file will be imported.**"
            )

            file_mappings = {}

            for i, uploaded_file in enumerate(uploaded_poa_files):
                filename = uploaded_file.name
                auto_matched = _fuzzy_match_to_plant(filename, plant_aliases)

                with st.expander(
                    f"📄 {filename}" + (f" → {auto_matched}" if auto_matched else " ⚠️ No match"),
                    expanded=(not auto_matched),
                ):
                    try:
                        df_preview = pd.read_csv(uploaded_file)
                        uploaded_file.seek(0)

                        col_info, col_map = st.columns([2, 1])
                        with col_info:
                            st.markdown("**File Preview:**")
                            st.dataframe(df_preview.head(5), use_container_width=True)
                            st.caption(
                                f"Total rows: {len(df_preview)} | "
                                f"Columns: {', '.join(df_preview.columns[:5])}..."
                            )
                            time_cols = [
                                c for c in df_preview.columns
                                if any(t in c.lower() for t in ["time", "date"])
                            ]
                            if time_cols:
                                sample_ts = df_preview[time_cols[0]].iloc[0] if len(df_preview) > 0 else "N/A"
                                st.caption(f"Timestamp column: `{time_cols[0]}` (sample: {sample_ts})")

                        with col_map:
                            st.markdown("**Link to Plant:**")
                            default_idx = (
                                plant_aliases.index(auto_matched) + 1
                                if auto_matched and auto_matched in plant_aliases
                                else 0
                            )
                            selected_plant_alias = st.selectbox(
                                "Select Plant",
                                options=["-- Skip this file --"] + plant_aliases,
                                index=default_idx,
                                key=f"poa_map_{i}",
                                label_visibility="collapsed",
                            )

                            if selected_plant_alias and selected_plant_alias != "-- Skip this file --":
                                file_mappings[filename] = {
                                    "alias": selected_plant_alias,
                                    "file_obj": uploaded_file,
                                }
                                st.success(
                                    f"✓ Will import as POA:{selected_plant_alias.replace(' ', '_').upper()}"
                                )
                            else:
                                st.warning("File will be skipped")
                    except Exception as e:
                        st.error(f"Error reading file: {e}")

            # Import button
            if file_mappings:
                st.markdown("---")
                if st.button(
                    f"🚀 Import {len(file_mappings)} POA File(s)",
                    type="primary",
                    key="import_poa_btn",
                ):
                    results = {}
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for idx, (filename, mapping) in enumerate(file_mappings.items()):
                        status_text.text(f"Importing {filename}...")
                        try:
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".csv", prefix="poa_"
                            ) as tmp:
                                mapping["file_obj"].seek(0)
                                tmp.write(mapping["file_obj"].read())
                                temp_path = tmp.name

                            # Resolve plant UID
                            plant = next(
                                (p for p in plant_list if p["alias"] == mapping["alias"]),
                                None,
                            )
                            if plant:
                                count = _import_poa_csv(
                                    svc,
                                    mapping["alias"],
                                    plant["plant_uid"],
                                    temp_path,
                                )
                                results[filename] = count
                            else:
                                st.error(f"Plant not found: {mapping['alias']}")
                                results[filename] = 0

                            os.unlink(temp_path)
                        except Exception as e:
                            st.error(f"Error importing {filename}: {e}")
                            results[filename] = 0
                        progress_bar.progress((idx + 1) / len(file_mappings))

                    status_text.empty()
                    progress_bar.empty()

                    total_imported = sum(results.values())
                    if total_imported > 0:
                        st.success(f"✅ POA Import complete! Imported {total_imported} readings.")
                        for fname, count in results.items():
                            if count > 0:
                                st.write(f"  ✓ {fname}: {count} readings")
                    else:
                        st.warning("No readings imported.")
            else:
                st.info("Select at least one file to enable import.")

    else:  # From Folder Path
        with st.container(border=True):
            st.markdown(
                """
                Import POA data from a folder on disk.
                1️⃣ Enter the folder path containing SolarGIS CSV files.
                2️⃣ System will scan and auto-match files to registered plants.
                3️⃣ Review matches and confirm import.
                """
            )

        folder_path = st.text_input(
            "Folder path",
            value=st.session_state.get("poa_folder_path", ""),
            placeholder="/path/to/solargis/csv/files",
        )
        if folder_path:
            st.session_state["poa_folder_path"] = folder_path

        if folder_path and os.path.isdir(folder_path):
            csv_files = sorted(f for f in os.listdir(folder_path) if f.lower().endswith(".csv"))
            st.success(f"Found {len(csv_files)} CSV files in folder.")

            if csv_files:
                # Auto-match
                matches = {}
                for f in csv_files:
                    matched = _fuzzy_match_to_plant(f, plant_aliases)
                    matches[f] = matched

                st.subheader("📋 File-to-Plant Matching")
                with st.form("poa_folder_import_form"):
                    final_map = {}
                    for i, (fname, auto_match) in enumerate(matches.items()):
                        c1, c2 = st.columns([3, 2])
                        with c1:
                            icon = "✅" if auto_match else "⚠️"
                            st.write(f"{icon} {fname}")
                        with c2:
                            options = ["-- Skip --"] + plant_aliases
                            default_idx = (
                                plant_aliases.index(auto_match) + 1
                                if auto_match and auto_match in plant_aliases
                                else 0
                            )
                            selected = st.selectbox(
                                "Assign",
                                options,
                                index=default_idx,
                                key=f"folder_map_{i}",
                                label_visibility="collapsed",
                            )
                            if selected and selected != "-- Skip --":
                                final_map[fname] = selected

                    submitted = st.form_submit_button("🚀 Import Matched Files", type="primary")

                if submitted and final_map:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results = {}

                    for idx, (fname, alias) in enumerate(final_map.items()):
                        status_text.text(f"Importing {fname}...")
                        csv_path = os.path.join(folder_path, fname)
                        plant = next(
                            (p for p in plant_list if p["alias"] == alias), None
                        )
                        if plant:
                            try:
                                count = _import_poa_csv(svc, alias, plant["plant_uid"], csv_path)
                                results[fname] = count
                            except Exception as e:
                                st.error(f"Error importing {fname}: {e}")
                                results[fname] = 0
                        progress_bar.progress((idx + 1) / len(final_map))

                    status_text.empty()
                    progress_bar.empty()

                    total = sum(results.values())
                    if total > 0:
                        st.success(f"✅ Imported {total} readings from {len(results)} files.")
                        for fname, count in results.items():
                            st.write(f"  ✓ {fname}: {count} readings")
                    else:
                        st.warning("No readings imported.")
        elif folder_path:
            st.error(f"Folder not found: {folder_path}")
