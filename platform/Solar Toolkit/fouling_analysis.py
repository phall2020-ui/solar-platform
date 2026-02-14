"""
Fouling Analysis Core Logic.
Refactored from Fouling_analysis.py (extracted from the workspace item "Fouling Analysis").
This module provides the fouling (soiling) analysis workflow used by the Streamlit app.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from solar_toolkit.config import settings
from solar_toolkit.utils import logger

try:
    from sklearn.linear_model import LinearRegression
except ImportError:
    LinearRegression = None
    logger.warning("Scikit-learn not found. Regression baseline is disabled.")


# --- CONFIGURABLE CONSTANTS ---
POA_MIN = 200               # W/m²
POA_BIN_WIDTH = 100         # W/m² bin size
# Fouling classification thresholds (fractional loss)
FOULING_CLEAN = 0.98        # Minimal or no loss
FOULING_MILD = 0.95         # Mild loss
FOULING_MODERATE = 0.90     # Moderate loss


@dataclass
class FoulingConfig:
    dc_size_kw: float
    irradiance_col: str = settings.POA_IRRADIANCE_COL
    # power_col will be determined automatically
    timestamp_col: str = "ts"
    emigid_col: str = "emigId"
    poa_min: float = POA_MIN
    poa_bin_width: int = POA_BIN_WIDTH
    # Power column preferences for auto-detection
    power_col_preferences: Tuple[str] = settings.POWER_COL_PREFERENCES

def determine_power_col(df: pd.DataFrame, cfg: FoulingConfig) -> str:
    """Detect the most appropriate power column in the dataframe."""
    
    # If the data is already flattened (from CSV), we look for key_value pairs
    for pref in cfg.power_col_preferences:
        col_value = f"{pref}_value"
        if col_value in df.columns and df[col_value].sum() != 0:
            return col_value
    
    # If the data is not flattened (from DB/API), we look for top-level keys
    for pref in cfg.power_col_preferences:
        if pref in df.columns and df[pref].astype(str).str.contains('value').any():
             # Found a nested column, use the base name
             return pref
        # Check if the column exists and contains non-dict data directly
        if pref in df.columns and not isinstance(df[pref].iloc[0], dict) and df[pref].sum() != 0:
            return pref
            
    raise ValueError(f"Could not find valid power column from preferences: {cfg.power_col_preferences}")

def prepare_data(df: pd.DataFrame, cfg: FoulingConfig) -> Tuple[pd.DataFrame, str]:
    """Standardizes data format and filters noise."""
    
    power_col_name = determine_power_col(df, cfg)
    
    # Standardize timestamp and filter out low irradiance
    df[cfg.timestamp_col] = pd.to_datetime(df[cfg.timestamp_col], errors="coerce", utc=True)
    df = df.dropna(subset=[cfg.timestamp_col])

    # 1. Extract values from nested columns if necessary
    
    def _extract_value(series, col_name):
        """Extracts 'value' from nested dicts or returns the value if flat."""
        if col_name in series.name and series.apply(lambda x: isinstance(x, dict)).any():
             return series.apply(lambda x: x.get('value') if isinstance(x, dict) else x)
        return series

    # Handle Irradiance Column
    if f"{cfg.irradiance_col}_value" in df.columns:
        irradiance_series = df[f"{cfg.irradiance_col}_value"]
    else:
        irradiance_series = _extract_value(df[cfg.irradiance_col], cfg.irradiance_col)
        
    df[cfg.irradiance_col] = pd.to_numeric(irradiance_series, errors='coerce')
    
    # Handle Power Column
    power_series = _extract_value(df[power_col_name], power_col_name)
    df[power_col_name] = pd.to_numeric(power_series, errors='coerce')

    df = df.dropna(subset=[cfg.irradiance_col, power_col_name])

    # 2. Filter out low irradiance points and zero/negative power
    df = df[
        (df[cfg.irradiance_col] >= cfg.poa_min) &
        (df[power_col_name] > 0)
    ].copy()
    
    if df.empty:
        raise ValueError("Data filtering resulted in an empty dataset. Check column names, DC size, and date range.")
        
    # 3. Calculate Performance Ratio (PR)
    df["pr"] = df[power_col_name] / (df[cfg.irradiance_col] * cfg.dc_size_kw)
    
    # 4. Create POA Bins for matching
    df["poa_bin"] = (df[cfg.irradiance_col] // cfg.poa_bin_width) * cfg.poa_bin_width
    
    return df, power_col_name

def build_baseline(clean_df: pd.DataFrame) -> Dict[int, float]:
    """Builds a performance baseline using POA-matched PR medians from the clean period."""
    
    baseline_profile = (
        clean_df.groupby("poa_bin")["pr"].median().to_dict()
    )
    return baseline_profile

def apply_baseline(df: pd.DataFrame, baseline: Dict[int, float]) -> pd.DataFrame:
    """Applies the baseline PR to the full dataset."""
    df["baseline_pr"] = df["poa_bin"].map(baseline)
    # The fouling index is the ratio of actual PR to expected (baseline) PR
    df["fouling_index"] = df["pr"] / df["baseline_pr"]
    return df.dropna(subset=["fouling_index"])

def run_fouling_analysis(full_data_df: pd.DataFrame, clean_data_df: pd.DataFrame, cfg: FoulingConfig) -> Dict:
    """
    Runs the complete fouling analysis workflow.
    """
    logger.info("Preparing clean data and building baseline...")
    clean_df_prepared, _ = prepare_data(clean_data_df, cfg)
    baseline = build_baseline(clean_df_prepared)
    
    logger.info("Preparing full data and applying baseline...")
    full_df_prepared, power_col_used = prepare_data(full_data_df, cfg)
    df_result = apply_baseline(full_df_prepared, baseline)
    
    # Calculate average fouling index (only for valid points)
    median_fouling_index = df_result["fouling_index"].median()
    
    # Classify fouling
    if median_fouling_index >= FOULING_CLEAN:
        fouling_level = "Clean (Minimal Loss)"
    elif median_fouling_index >= FOULING_MILD:
        fouling_level = "Mild Fouling"
    elif median_fouling_index >= FOULING_MODERATE:
        fouling_level = "Moderate Fouling"
    else:
        fouling_level = "Severe Fouling"

    logger.info(f"Analysis used Power Column: {power_col_used}")
    
    return {
        "fouling_index": median_fouling_index,
        "fouling_level": fouling_level,
        "df_result": df_result,
        "power_col_used": power_col_used
    }

def auto_select_clean_period(df: pd.DataFrame, cfg: FoulingConfig, days: int = 3) -> Tuple[pd.DataFrame, Tuple[str, str]]:
    """
    Attempts to auto-select the 'cleanest' period for baseline calculation.
    Uses the period with the highest median PR.
    """
    df_prepared, _ = prepare_data(df, cfg)
    if df_prepared.empty:
        raise ValueError("Prepared data is empty. Cannot auto-select clean period.")

    # Group by day and find the median PR for each day
    # Assume timestamp column is "ts" for the sake of filtering
    df_prepared = df_prepared.rename(columns={'ts': 'timestamp_dt'})
    
    daily_pr = df_prepared.set_index('timestamp_dt').resample('D')['pr'].median().dropna()
    if daily_pr.empty:
        raise ValueError("Could not calculate daily PR median for auto-selection.")
        
    # Find the day with the highest PR
    clean_day = daily_pr.idxmax()
    
    # Define the period: clean_day - days/2 to clean_day + days/2
    start_dt = clean_day.normalize() - timedelta(days=days//2)
    end_dt = clean_day.normalize() + timedelta(days=(days - days//2) - 1, hours=23, minutes=59)

    clean_data_df = filter_by_date_range(df, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))
    
    return clean_data_df, (start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))

def filter_by_date_range(df: pd.DataFrame, start_date: str, end_date: str, ts_col: str = "ts") -> pd.DataFrame:
    """Filters a DataFrame by a YYYYMMDD date range."""
    
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    
    # Use timezone-aware UTC datetimes
    start_dt = datetime.strptime(start_date, "%Y%m%d").replace(tzinfo=datetime.timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y%m%d").replace(hour=23, minute=59, second=59, tzinfo=datetime.timezone.utc)
    
    return df[(df[ts_col] >= start_dt) & (df[ts_col] <= end_dt)].copy()
