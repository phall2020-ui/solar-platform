"""
Shading Analysis Core Logic.
Refactored from Shading_analysis.py.
"""
from __future__ import annotations
import argparse
import sys
import tkinter as tk
from tkinter import filedialog
from dataclasses import dataclass
from typing import Tuple, Optional, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from solar_toolkit.config import settings
from solar_toolkit.utils import logger

# --- Configuration ---
@dataclass
class ShadingSettings:
    irradiance_col: str = settings.POA_IRRADIANCE_COL
    # Tries 'apparentPower', then 'activePower', etc.
    current_col_preferences: Tuple[str] = settings.POWER_COL_PREFERENCES
    timestamp_col: str = "ts" # Using 'ts' which is the standard API/DB name
    emigid_col: str = "emigId"
    irradiance_min: float = 50.0   # Lowered slightly to capture early morning shading
    min_points_per_hour: int = 2   # Minimum records to accept an hour bin
    
# --- Core Logic ---

def detect_weather_id(df: pd.DataFrame, cfg: ShadingSettings) -> str:
    """
    Scans the dataframe to find which ID contains POA irradiance data.
    Assumes irradiance data will be non-null and high when sunny.
    """
    irradiance_col = f"{cfg.irradiance_col}_value" if f"{cfg.irradiance_col}_value" in df.columns else cfg.irradiance_col
    
    # Find all unique device IDs
    emig_ids = df[cfg.emigid_col].unique()
    
    best_id = None
    max_poa = -1
    
    for emig_id in emig_ids:
        device_df = df[df[cfg.emigid_col] == emig_id].copy()
        
        # Check if the column exists or can be extracted
        if irradiance_col in device_df.columns:
            poa_data = pd.to_numeric(device_df[irradiance_col], errors='coerce')
        elif cfg.irradiance_col in device_df.columns:
            # Extract from nested dict if present (DB format)
            poa_data = device_df[cfg.irradiance_col].apply(lambda x: x.get('value') if isinstance(x, dict) else x)
            poa_data = pd.to_numeric(poa_data, errors='coerce')
        else:
            continue
            
        # Ignore zeros and nulls for calculating max
        poa_data = poa_data.dropna()
        poa_data = poa_data[poa_data > 0]
        
        if not poa_data.empty and poa_data.max() > max_poa:
            max_poa = poa_data.max()
            best_id = emig_id

    if best_id:
        logger.info(f"Auto-detected weather station ID: {best_id} (Max POA: {max_poa:.1f} W/m²)")
        return best_id
    
    raise ValueError("Could not automatically detect weather station ID with valid POA data.")

def determine_power_col(df: pd.DataFrame, cfg: ShadingSettings) -> str:
    """Detect the most appropriate power column in the dataframe."""
    
    # Prioritize flattened columns (from CSV)
    for col in cfg.current_col_preferences:
        col_value = f"{col}_value"
        if col_value in df.columns and df[col_value].sum() != 0:
            return col_value
    
    # Fallback to nested columns (from DB)
    for col in cfg.current_col_preferences:
        if col in df.columns and df[col].astype(str).str.contains('value').any():
             # Found a nested column, use the base name
             return col
        # Check if the column exists and contains non-dict data directly
        if col in df.columns and not isinstance(df[col].iloc[0], dict) and df[col].sum() != 0:
            return col
            
    raise ValueError(f"Could not find valid power column from preferences: {cfg.current_col_preferences}")

def prepare_device_data(df: pd.DataFrame, power_col: str, cfg: ShadingSettings) -> pd.DataFrame:
    """Standardizes, cleans, and adds time features to data for a single device."""
    
    # Ensure correct data types
    df[cfg.timestamp_col] = pd.to_datetime(df[cfg.timestamp_col], errors="coerce", utc=True)
    df = df.dropna(subset=[cfg.timestamp_col, power_col])
    
    # Extract value from nested dicts if needed
    if power_col in cfg.current_col_preferences:
        power_data = df[power_col].apply(lambda x: x.get('value') if isinstance(x, dict) else x)
        df[power_col] = pd.to_numeric(power_data, errors='coerce')
    else:
         df[power_col] = pd.to_numeric(df[power_col], errors='coerce')
    
    # Filter out impossible or zero values (night time)
    df = df[df[power_col] > 0].copy()
    
    # Add time features
    df["date"] = df[cfg.timestamp_col].dt.date
    # Calculate float hour for grouping and plotting (e.g., 10:30 -> 10.5)
    df["hour_float"] = df[cfg.timestamp_col].dt.hour + df[cfg.timestamp_col].dt.minute / 60.0
    
    return df.dropna(subset=[power_col])

def load_and_prepare(file_path: str, cfg: ShadingSettings) -> Tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """Loads CSV, separates weather and inverter data, and determines column names."""
    
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Data file not found: {file_path}")
        
    logger.info(f"Loading data from {os.path.basename(file_path)}...")
    df_raw = pd.read_csv(file_path)
    
    power_col = determine_power_col(df_raw, cfg)
    weather_id = detect_weather_id(df_raw, cfg)
    
    # Separate weather (POA) and inverter data
    df_weather = df_raw[df_raw[cfg.emigid_col] == weather_id].copy()
    df_inverters = df_raw[df_raw[cfg.emigid_col] != weather_id].copy()
    
    if df_inverters.empty:
        raise ValueError("No inverter data found after separating weather station data.")

    # Prepare data for processing
    df_weather = prepare_device_data(df_weather, power_col, cfg)
    df_inverters = prepare_device_data(df_inverters, power_col, cfg)
    
    return df_inverters, df_weather, weather_id, power_col

def process_season(inv_df: pd.DataFrame, weth_df: pd.DataFrame, power_col: str, cfg: ShadingSettings) -> pd.DataFrame:
    """
    Computes the normalized performance profile (efficiency) for each inverter 
    across the day, matched by POA irradiance.
    """
    # 1. Prepare Weather (POA) Data for merging
    irradiance_col = f"{cfg.irradiance_col}_value" if f"{cfg.irradiance_col}_value" in weth_df.columns else cfg.irradiance_col
    
    # Extract POA value safely
    if irradiance_col in cfg.current_col_preferences:
        poa_series = weth_df[irradiance_col].apply(lambda x: x.get('value') if isinstance(x, dict) else x)
        weth_df[irradiance_col] = pd.to_numeric(poa_series, errors='coerce')
    else:
         weth_df[irradiance_col] = pd.to_numeric(weth_df[irradiance_col], errors='coerce')

    weth_df = weth_df.dropna(subset=[irradiance_col])
    weth_df = weth_df[weth_df[irradiance_col] >= cfg.irradiance_min].copy()
    weth_df = weth_df[[cfg.timestamp_col, irradiance_col]].rename(columns={irradiance_col: "irradiance"})
    
    # 2. Join Inverter and Weather Data
    inv_df = inv_df.merge(weth_df, on=cfg.timestamp_col, how='inner')
    
    # Filter out low irradiance points on the combined set
    inv_df = inv_df[inv_df["irradiance"] >= cfg.irradiance_min].copy()

    # 3. Compute Normalized Efficiency
    # Efficiency is simply P_out / I_POA (unit-agnostic, proportional to PR * P_DC)
    inv_df["efficiency"] = inv_df[power_col] / inv_df["irradiance"]
    
    # 4. Aggregate by Inverter and Hour_Float (Binning)
    
    # Use 15-minute binning for more granularity (0.25 hours)
    inv_df["hour_float_bin"] = (inv_df["hour_float"] * 4).round() / 4
    
    agg_df = inv_df.groupby([cfg.emigid_col, "hour_float_bin"]).agg(
        eff_median=('efficiency', 'median'),
        count=('efficiency', 'count')
    ).reset_index()
    
    # Filter out bins with insufficient data
    agg_df = agg_df[agg_df["count"] >= cfg.min_points_per_hour].copy()
    
    # Rename for clarity
    agg_df = agg_df.rename(columns={"eff_median": "eff", "hour_float_bin": "hour_float"})
    
    return agg_df

def generate_plots(merged_df: pd.DataFrame, output_pdf_path: str, cfg: ShadingSettings) -> None:
    """Generates comparative plots for the shading analysis."""
    
    inverter_ids = merged_df[cfg.emigid_col].unique()
    
    with PdfPages(output_pdf_path) as pdf:
        
        # Plot 1: Efficiency Comparison (Summer vs Winter)
        for inv_id in inverter_ids:
            fig, ax = plt.subplots(figsize=(12, 6))
            inv_data = merged_df[merged_df[cfg.emigid_col] == inv_id]
            
            ax.plot(inv_data["hour_float"], inv_data["eff_summer"], label="Summer (Baseline)", marker='o', linestyle='-', markersize=4)
            ax.plot(inv_data["hour_float"], inv_data["eff_winter"], label="Winter (Shaded)", marker='x', linestyle='--', markersize=4)
            
            ax.set_title(f"Inverter {inv_id} - Efficiency Comparison")
            ax.set_xlabel("Time of Day (Hour)")
            ax.set_ylabel("Normalized Efficiency (P_out / I_POA)")
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend()
            ax.set_xlim(5, 19)
            
            pdf.savefig(fig)
            plt.close(fig)

        # Plot 2: Shading Ratio (Winter/Summer)
        for inv_id in inverter_ids:
            fig, ax = plt.subplots(figsize=(12, 6))
            inv_data = merged_df[merged_df[cfg.emigid_col] == inv_id]
            
            ax.plot(inv_data["hour_float"], inv_data["ratio"], label="Winter/Summer Ratio", marker='.', linestyle='-', markersize=4, color='red')
            
            ax.axhline(1.0, color='green', linestyle='-', linewidth=1, label="No Loss (Ratio = 1.0)")
            ax.axhline(0.9, color='orange', linestyle='--', linewidth=1, label="10% Loss")
            ax.axhline(0.8, color='red', linestyle='--', linewidth=1, label="20% Loss")
            
            ax.set_title(f"Inverter {inv_id} - Shading Loss Ratio (Winter Eff / Summer Eff)")
            ax.set_xlabel("Time of Day (Hour)")
            ax.set_ylabel("Efficiency Ratio (Lower = More Shading)")
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend()
            ax.set_xlim(5, 19)
            ax.set_ylim(0.5, 1.1)
            
            pdf.savefig(fig)
            plt.close(fig)

    logger.info(f"Generated {len(inverter_ids) * 2} plots and saved to {output_pdf_path}")