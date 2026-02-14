"""
Shading Analysis Module v3.0
Analyzes shading effects by comparing seasonal data (summer baseline vs winter/shaded).

Includes:
- Auto-detection of weather stations
- Visual plotting with PDF generation
- Normalized efficiency calculations (optionally temperature-corrected)
- Data quality filtering (irradiance, days, outliers, clouds)
- Classification of shading severity
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Tuple, Optional, List, Dict

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend for server environments
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    PdfPages = None  # type: ignore  # Fallback for type hints when matplotlib not installed

from .utils import logger


# --- Configuration ---


@dataclass
class ShadingSettings:
    """Configuration for shading analysis."""
    irradiance_col: str = "poaIrradiance"
    # Tries these columns in order to find power/current data
    current_col_preferences: Tuple[str, ...] = ("apparentPower", "activePower", "dcCurrent", "exportEnergy")
    timestamp_col: str = "timestamp"
    emigid_col: str = "emigId"

    # Irradiance thresholds
    irradiance_min: float = 50.0    # Minimum irradiance to include (W/m²)
    irradiance_max: float = 1200.0  # Max plausible irradiance to keep (W/m²)

    # Data density requirements
    min_points_per_hour: int = 2    # Minimum records to accept an hour bin
    min_days_per_inverter: int = 5  # Minimum distinct days per inverter

    # Core daylight window (for summarising shading)
    core_hours_start: float = 9.0   # Core window start (9am)
    core_hours_end: float = 15.0    # Core window end (3pm)

    # Hour binning (e.g. 0.25h = 15 minutes)
    hour_bin_width: float = 0.25

    # Efficiency outlier filtering (quantile clipping)
    eff_q_low: float = 0.01
    eff_q_high: float = 0.99

    # Optional temperature handling
    temperature_col: Optional[str] = None  # e.g. 'moduleTemp' or 'ambTemp'
    temp_ref: float = 25.0                 # reference temperature (°C)
    temp_coeff_pct_per_deg: float = -0.4   # %/°C, typical c-Si module
    temp_min: float = -10.0                # QC band for temperature
    temp_max: float = 80.0

    # Cloud filtering
    use_cloud_filter: bool = True

    # Timezone handling
    timezone_str: str = "Europe/London"


# --- Helper Functions ---


def _bin_hour_float(dt_series: pd.Series, cfg: ShadingSettings) -> pd.Series:
    """Convert timestamps to binned hour_float according to hour_bin_width."""
    hour_float = dt_series.dt.hour + dt_series.dt.minute / 60.0
    return (hour_float / cfg.hour_bin_width).round() * cfg.hour_bin_width


def apply_basic_qc(m: pd.DataFrame, power_col: str, cfg: ShadingSettings) -> pd.DataFrame:
    """Remove obviously bad points before profiling."""
    if m.empty:
        return m

    # Replace infs and drop NaNs
    m = m.replace([np.inf, -np.inf], np.nan)
    m = m.dropna(subset=["irr", power_col, "dt"])

    # Irradiance range filter
    m = m[m["irr"].between(cfg.irradiance_min, cfg.irradiance_max)]

    # Strictly positive power
    m = m[m[power_col] > 0]

    if m.empty:
        return m

    # Enforce minimum days per inverter
    m["date"] = m["dt"].dt.date
    valid_ids = (
        m.groupby(cfg.emigid_col)["date"]
        .nunique()
        .pipe(lambda s: s[s >= cfg.min_days_per_inverter].index)
    )
    m = m[m[cfg.emigid_col].isin(valid_ids)]
    m = m.drop(columns=["date"], errors="ignore")

    return m


def clip_efficiency_outliers(m: pd.DataFrame, cfg: ShadingSettings) -> pd.DataFrame:
    """Clip efficiency outliers per inverter using quantiles."""
    if m.empty or "efficiency" not in m.columns:
        return m

    def _clip(group: pd.DataFrame) -> pd.DataFrame:
        if group["efficiency"].isna().all():
            return group
        ql, qh = group["efficiency"].quantile([cfg.eff_q_low, cfg.eff_q_high])
        return group[group["efficiency"].between(ql, qh)]

    return m.groupby(cfg.emigid_col, group_keys=False).apply(_clip)


def drop_cloudy_instants(m: pd.DataFrame, power_col: str, cfg: ShadingSettings) -> pd.DataFrame:
    """
    Drop timestamps dominated by clouds using fleet median efficiency as a clear-sky proxy.
    Keeps instants where fleet efficiency is reasonably high.
    """
    if m.empty:
        return m

    tmp = m.copy()
    tmp["eff_tmp"] = tmp[power_col] / tmp["irr"]
    fleet = (
        tmp.groupby("dt")["eff_tmp"]
        .median()
        .rename("fleet_eff")
    )
    m = m.join(fleet, on="dt")

    if m["fleet_eff"].isna().all():
        m = m.drop(columns=["fleet_eff"], errors="ignore")
        return m

    fleet_max = m["fleet_eff"].quantile(0.99)
    clear_threshold = 0.7 * fleet_max  # keep relatively clear instants
    m = m[m["fleet_eff"] >= clear_threshold]
    m = m.drop(columns=["fleet_eff", "eff_tmp"], errors="ignore")

    return m


# --- Core Logic ---


def detect_weather_id(df: pd.DataFrame, cfg: ShadingSettings) -> str:
    """
    Scans the dataframe to find which device ID actually contains irradiance data.

    Uses a heuristic based on data volume, irradiance range, and ID patterns.
    """
    if cfg.irradiance_col not in df.columns:
        raise ValueError(f"Irradiance column '{cfg.irradiance_col}' not found in dataframe")

    valid_irr = df[df[cfg.irradiance_col] > 0].copy()
    if valid_irr.empty:
        raise ValueError(f"No valid data found in column '{cfg.irradiance_col}'")

    stats = (
        valid_irr.groupby(cfg.emigid_col)[cfg.irradiance_col]
        .agg(["count", "min", "max"])
        .reset_index()
    )

    # Only keep IDs that look like a real irradiance sensor
    stats = stats[stats["count"] > 100]
    stats = stats[stats["max"] > 600]

    if stats.empty:
        raise ValueError("Could not identify a realistic irradiance source (insufficient range or points)")

    def _score(row):
        sid = str(row[cfg.emigid_col])
        base = 0
        if "WETH" in sid or "MET" in sid:
            base += 10
        if "POA" in sid:
            base += 5
        # More points and wider range are better
        return base + row["count"] / 1000.0 + (row["max"] - row["min"]) / 1000.0

    stats["score"] = stats.apply(_score, axis=1)
    best_id = stats.sort_values("score", ascending=False)[cfg.emigid_col].iloc[0]
    logger.info(f"✓ Auto-detected Weather Station: {best_id}")
    return best_id


def determine_power_col(df: pd.DataFrame, cfg: ShadingSettings) -> str:
    """
    Finds the best available power/current column.
    """
    for col in cfg.current_col_preferences:
        if col in df.columns and df[col].sum() != 0:
            logger.info(f"✓ Using power column: {col}")
            return col

        flat_col = f"{col}_value"
        if flat_col in df.columns and df[flat_col].sum() != 0:
            logger.info(f"✓ Using power column: {flat_col}")
            return flat_col

    raise ValueError(f"Could not find a valid power column. Checked: {cfg.current_col_preferences}")


def load_and_prepare(path: str, cfg: ShadingSettings) -> Tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """
    Load CSV, split weather/inverter data, and auto-detect settings.

    Returns:
        Tuple of (inverter_df, weather_df, weather_id, power_col)
    """
    logger.info(f"Loading {path}...")
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise RuntimeError(f"Error reading {path}: {e}")

    # Standardise timestamp
    if cfg.timestamp_col not in df.columns:
        # Try finding a column that looks like 'time'
        time_cols = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower() or c.lower() == 'ts']
        if time_cols:
            cfg.timestamp_col = time_cols[0]
            logger.info(f"  Using '{cfg.timestamp_col}' as timestamp.")
        else:
            raise ValueError("Could not find timestamp column.")

    # Parse as UTC then convert to desired timezone
    df["dt"] = pd.to_datetime(df[cfg.timestamp_col], errors="coerce", utc=True)
    df = df.dropna(subset=["dt"]).copy()
    try:
        df["dt"] = df["dt"].dt.tz_convert(cfg.timezone_str)
    except Exception:
        # If tz_convert fails (already local), just keep as is
        pass

    # Add hour_float with binning
    df["hour_float"] = _bin_hour_float(df["dt"], cfg)

    # Detect irradiance column if not found
    if cfg.irradiance_col not in df.columns:
        alt_irr_cols = ['GTI', 'gti', 'POA', 'poa', 'irradiance', 'Irradiance']
        found_irr = next((alt for alt in alt_irr_cols if alt in df.columns), None)
        if found_irr:
            cfg.irradiance_col = found_irr
            logger.info(f"  Using '{found_irr}' as irradiance column.")
        else:
            raise ValueError(f"Column '{cfg.irradiance_col}' missing from CSV. Available: {list(df.columns)}")

    # Detect weather station and power column
    weather_id = detect_weather_id(df, cfg)
    power_col = determine_power_col(df, cfg)

    # Split Data
    is_weather = df[cfg.emigid_col] == weather_id
    df_weather = df[is_weather].copy()
    df_inv = df[~is_weather].copy()

    return df_inv, df_weather, weather_id, power_col


def join_with_irradiance(
    df_inv: pd.DataFrame,
    df_weather: pd.DataFrame,
    power_col: str,
    cfg: ShadingSettings
) -> pd.DataFrame:
    """
    Join inverter data with irradiance (and optionally temperature) and calculate efficiency.
    Applies QC, optional cloud filtering, and outlier clipping.
    """
    # Build weather lookup columns
    cols = ["dt", cfg.irradiance_col]
    if cfg.temperature_col and cfg.temperature_col in df_weather.columns:
        cols.append(cfg.temperature_col)

    w = df_weather[cols].rename(columns={cfg.irradiance_col: "irr"})
    if cfg.temperature_col and cfg.temperature_col in df_weather.columns:
        w = w.rename(columns={cfg.temperature_col: "temp"})

    # Filter low light
    w = w[w["irr"] >= cfg.irradiance_min]

    # Merge
    m = df_inv.merge(w, on="dt", how="inner")

    # Apply basic QC
    m = apply_basic_qc(m, power_col, cfg)
    if m.empty:
        return m

    # Optional temperature QC
    if "temp" in m.columns:
        m = m[m["temp"].between(cfg.temp_min, cfg.temp_max)]

    if m.empty:
        return m

    # Optional cloud filtering
    if cfg.use_cloud_filter:
        m = drop_cloudy_instants(m, power_col, cfg)
        if m.empty:
            return m

    # Temperature correction & efficiency
    if "temp" in m.columns:
        gamma = cfg.temp_coeff_pct_per_deg / 100.0  # %/°C -> 1/°C
        temp_factor = 1.0 + gamma * (m["temp"] - cfg.temp_ref)
        m["efficiency"] = m[power_col] / (m["irr"] * temp_factor)
    else:
        m["efficiency"] = m[power_col] / m["irr"]

    # Clip outliers
    m = clip_efficiency_outliers(m, cfg)

    # Ensure hour_float aligned with config
    m["hour_float"] = _bin_hour_float(m["dt"], cfg)

    return m


def build_profile(merged_df: pd.DataFrame, cfg: ShadingSettings) -> pd.DataFrame:
    """
    Build hourly efficiency profile from merged data.
    """
    if merged_df.empty:
        return pd.DataFrame()

    profile = (
        merged_df.groupby([cfg.emigid_col, "hour_float"])["efficiency"]
        .agg(["median", "count"])
        .reset_index()
    )

    profile = profile[profile["count"] >= cfg.min_points_per_hour]
    return profile.rename(columns={"median": "eff_median", "count": "n_points"})


def process_season(
    df_inv: pd.DataFrame,
    df_weather: pd.DataFrame,
    power_col: str,
    cfg: ShadingSettings
) -> pd.DataFrame:
    """
    Joins inverter data with weather data and calculates normalized efficiency profiles
    for a given season.
    """
    m = join_with_irradiance(df_inv, df_weather, power_col, cfg)
    if m.empty:
        logger.warning("No data after QC / merge for this season")
        return pd.DataFrame()
    return build_profile(m, cfg)


def compare_profiles(prof_summer: pd.DataFrame, prof_winter: pd.DataFrame, cfg: ShadingSettings) -> pd.DataFrame:
    """
    Compare summer (baseline) and winter (test) profiles.
    """
    if prof_summer.empty or prof_winter.empty:
        return pd.DataFrame()

    m = prof_summer.merge(
        prof_winter,
        on=[cfg.emigid_col, "hour_float"],
        suffixes=('_summer', '_winter')
    )

    if m.empty:
        return m

    # Calculate ratio (winter/summer) - values < 1 indicate shading loss
    m["ratio"] = m["eff_median_winter"] / m["eff_median_summer"].replace(0, np.nan)
    m["loss_delta"] = m["eff_median_summer"] - m["eff_median_winter"]
    m = m.dropna(subset=["ratio"])

    return m


def summarise_shading(compared_df: pd.DataFrame, cfg: ShadingSettings) -> pd.DataFrame:
    """
    Summarize shading analysis results by inverter.
    Filters for core daylight hours and classifies shading severity.
    """
    if compared_df.empty:
        return pd.DataFrame()

    core_m = compared_df[
        (compared_df["hour_float"] >= cfg.core_hours_start) &
        (compared_df["hour_float"] <= cfg.core_hours_end)
    ].copy()

    if core_m.empty:
        logger.warning(f"No data in core hours ({cfg.core_hours_start}-{cfg.core_hours_end})")
        return pd.DataFrame()

    summary = core_m.groupby(cfg.emigid_col).agg(
        ratio=("ratio", "median"),
        n_core_hours=("ratio", "size"),
        median_eff_summer=("eff_median_summer", "median"),
        median_eff_winter=("eff_median_winter", "median"),
    ).reset_index()

    summary["classification"] = np.select(
        [summary["ratio"] >= 0.95, summary["ratio"] >= 0.85, summary["ratio"] >= 0.70],
        ["No Shading", "Mild Shading", "Moderate Shading"],
        default="Severe Shading"
    )

    summary["estimated_loss_pct"] = ((1 - summary["ratio"]) * 100).round(2)

    return summary


# ---------------------------------------------------------------------------
#  Heatmap graphic & daily / monthly loss calculation
# ---------------------------------------------------------------------------

def plot_ratio_heatmap(merged_df: pd.DataFrame, cfg: ShadingSettings, pdf: PdfPages) -> None:
    """
    Add a heatmap page showing Winter/Summer ratio for each inverter vs hour of day.
    Expects merged_df to have columns: [cfg.emigid_col, 'hour_float', 'ratio'].
    """
    if merged_df.empty:
        return

    pivot = merged_df.pivot(
        index=cfg.emigid_col,
        columns="hour_float",
        values="ratio"
    )

    fig_height = max(4, len(pivot.index) * 0.3)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    im = ax.imshow(
        pivot.values,
        aspect="auto",
        origin="lower",
        vmin=0.6,
        vmax=1.05
    )

    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels([f"{h:.1f}" for h in pivot.columns], rotation=90)

    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Inverter ID")
    ax.set_title("Winter / Summer Efficiency Ratio Heatmap")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Ratio (Winter / Summer)")

    pdf.savefig(fig)
    plt.close(fig)


def compute_daily_monthly_loss(
    merged_df: pd.DataFrame,
    cfg: ShadingSettings,
    core_hours: Tuple[float, float] = (9.0, 15.0)
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Estimate daily and monthly loss per inverter from a merged ratio dataframe.

    Assumptions:
      - merged_df has at least columns:
          [cfg.emigid_col, 'hour_float', 'ratio']
      - 'ratio' is Winter/Summer efficiency ratio at each hour.

    Returns:
      daily_loss:   [emigId, date, ratio, loss_pct] (if timestamp data available)
      monthly_loss: [emigId, year_month, ratio, loss_pct] (if timestamp data available)
      
    Note: If timestamp column is not available, returns aggregated core-hour stats.
    """
    if merged_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = merged_df.copy()
    h0, h1 = core_hours

    # Filter to core hours
    df_core = df[(df["hour_float"] >= h0) & (df["hour_float"] <= h1)].copy()
    if df_core.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Check if we have timestamp data for daily/monthly breakdown
    timestamp_col = cfg.timestamp_col if hasattr(cfg, 'timestamp_col') else 'timestamp'
    
    if timestamp_col in df_core.columns:
        df_core[timestamp_col] = pd.to_datetime(df_core[timestamp_col], errors="coerce")
        df_core = df_core.dropna(subset=[timestamp_col, "ratio"])
        
        if not df_core.empty:
            # Derive date
            df_core["date"] = df_core[timestamp_col].dt.date

            # Daily median ratio per inverter
            daily = (
                df_core.groupby([cfg.emigid_col, "date"])["ratio"]
                .median()
                .reset_index()
            )
            daily["loss_pct"] = (1.0 - daily["ratio"]) * 100.0

            # Monthly median ratio per inverter
            daily["year_month"] = pd.to_datetime(daily["date"]).dt.to_period("M")
            monthly = (
                daily.groupby([cfg.emigid_col, "year_month"])["ratio"]
                .median()
                .reset_index()
            )
            monthly["loss_pct"] = (1.0 - monthly["ratio"]) * 100.0

            return daily, monthly

    # Fallback: just return core-hour aggregated stats per inverter
    summary = (
        df_core.groupby(cfg.emigid_col)["ratio"]
        .median()
        .reset_index()
    )
    summary["loss_pct"] = (1.0 - summary["ratio"]) * 100.0
    
    return summary, pd.DataFrame()


def generate_plots(merged_data: pd.DataFrame, output_pdf: str, cfg: ShadingSettings) -> bool:
    """
    Generates a multi-page PDF with visual shading analysis.
    """
    if not HAS_MATPLOTLIB:
        logger.warning("matplotlib not available, skipping plot generation")
        return False

    if merged_data.empty:
        logger.warning("No merged data available for plotting")
        return False

    logger.info(f"Generating Visual Report: {output_pdf}")

    inverters = merged_data[cfg.emigid_col].unique()

    try:
        with PdfPages(output_pdf) as pdf:
            # Summary page
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5, 0.5,
                f"Shading Analysis Report\n\n"
                f"Total Inverters: {len(inverters)}\n\n"
                f"Core Analysis Window: {cfg.core_hours_start:.0f}:00 - {cfg.core_hours_end:.0f}:00\n\n"
                f"See subsequent pages for daily profiles.",
                ha='center', va='center', fontsize=14, transform=ax.transAxes
            )
            ax.axis('off')
            pdf.savefig(fig)
            plt.close(fig)

            for inv in inverters:
                subset = merged_data[merged_data[cfg.emigid_col] == inv].sort_values("hour_float")

                if len(subset) < 4:
                    continue  # Skip if barely any data

                # Calculate core-hours median ratio for title
                core_subset = subset[
                    (subset["hour_float"] >= cfg.core_hours_start) &
                    (subset["hour_float"] <= cfg.core_hours_end)
                ]
                if core_subset.empty:
                    avg_ratio = subset["ratio"].median()
                else:
                    avg_ratio = core_subset["ratio"].median()

                if avg_ratio < 0.7:
                    status = "SEVERE SHADING"
                    title_color = 'red'
                elif avg_ratio < 0.85:
                    status = "Mild/Moderate Shading"
                    title_color = 'orange'
                else:
                    status = "Clean"
                    title_color = 'green'

                fig, ax = plt.subplots(figsize=(10, 6))

                ax.plot(
                    subset["hour_float"], subset["eff_median_summer"],
                    color='orange', marker='o', label='Summer (Baseline)', linewidth=2
                )

                ax.plot(
                    subset["hour_float"], subset["eff_median_winter"],
                    color='blue', marker='x', linestyle='--', label='Winter (Observed)'
                )

                ax.fill_between(
                    subset["hour_float"],
                    subset["eff_median_summer"],
                    subset["eff_median_winter"],
                    where=(subset["eff_median_winter"] < subset["eff_median_summer"]),
                    interpolate=True,
                    color='red',
                    alpha=0.2,
                    label='Energy Loss'
                )

                ax.set_title(
                    f"Inverter: {inv} | Status: {status} (Core Ratio: {avg_ratio:.2f})",
                    color=title_color,
                    fontweight='bold'
                )
                ax.set_xlabel("Hour of Day (24h)")
                ax.set_ylabel("Normalized Efficiency (W / W/m²)")
                ax.set_xlim(6, 18)
                ax.grid(True, linestyle=':', alpha=0.6)
                ax.legend()

                pdf.savefig(fig)
                plt.close(fig)

            # Add site-wide heatmap of ratio vs hour & inverter
            plot_ratio_heatmap(merged_data, cfg, pdf)

        logger.info(f"✓ Plots saved to {output_pdf} ({len(inverters)} inverter plots + heatmap)")
        return True

    except Exception as e:
        logger.error(f"Error generating plots: {e}")
        return False


def run_shading_analysis(
    summer_csv: str,
    winter_csv: str,
    output_base: str,
    cfg: Optional[ShadingSettings] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Complete shading analysis pipeline from CSV files.

    Returns:
        Tuple of (detailed_comparison_df, summary_df)
    """
    if cfg is None:
        cfg = ShadingSettings()

    # 1. Load & Detect
    inv_s, w_s, wid, p_col = load_and_prepare(summer_csv, cfg)
    inv_w, w_w, _, _ = load_and_prepare(winter_csv, cfg)

    logger.info(f"Analyzing using Weather Station: {wid}")
    logger.info(f"Comparing Column: {p_col} / {cfg.irradiance_col}")

    # 2. Build Profiles
    logger.info("Building Seasonal Profiles...")
    prof_s = process_season(inv_s, w_s, p_col, cfg)
    prof_w = process_season(inv_w, w_w, p_col, cfg)

    if prof_s.empty or prof_w.empty:
        raise ValueError("Could not build valid profiles from the data. Check irradiance, power, and QC thresholds.")

    # 3. Compare
    logger.info("Comparing Data...")
    merged = compare_profiles(prof_s, prof_w, cfg)

    if merged.empty:
        raise ValueError("No overlapping data between summer and winter periods after QC.")

    # 4. Summarise
    summary = summarise_shading(merged, cfg)

    # 5. Save Outputs
    excel_name = f"{output_base}.xlsx"
    pdf_name = f"{output_base}.pdf"
    csv_name = f"{output_base}_detail.csv"

    logger.info("Saving Results...")

    try:
        merged.to_csv(csv_name, index=False)
        logger.info(f"✓ Detailed data saved to {csv_name}")
    except Exception as e:
        logger.error(f"Error saving CSV: {e}")

    try:
        with pd.ExcelWriter(excel_name, engine='openpyxl') as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            merged.to_excel(writer, sheet_name="Detailed_Hourly", index=False)
        logger.info(f"✓ Excel data saved to {excel_name}")
    except ImportError:
        logger.warning("openpyxl not installed, skipping Excel export")
    except Exception as e:
        logger.error(f"Error saving Excel: {e}")

    generate_plots(merged, pdf_name, cfg)

    return merged, summary


def analyze_from_dataframes(
    summer_inv_df: pd.DataFrame,
    winter_inv_df: pd.DataFrame,
    power_col: str,
    summer_irr_df: Optional[pd.DataFrame] = None,
    winter_irr_df: Optional[pd.DataFrame] = None,
    irr_col: str = 'poaIrradiance',
    emig_id_col: str = 'emig_id',
    timestamp_col: str = 'ts',
    cfg: Optional[ShadingSettings] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run shading analysis directly from DataFrames (for database data).
    
    This is a self-contained implementation that handles database data formats
    without relying on CSV-oriented functions.
    
    If irradiance dataframes are provided, performs normalized efficiency analysis (Power/Irradiance).
    Otherwise, compares raw power profiles (less accurate for shading).
    """
    if cfg is None:
        cfg = ShadingSettings()
    cfg.emigid_col = emig_id_col
    
    # --- Helper: Robust timestamp normalization ---
    def normalize_timestamps(df: pd.DataFrame, source_name: str = "data") -> pd.DataFrame:
        """
        Robustly parse and normalize timestamps from various malformed formats.
        Handles: +00:00Z, .000000Z, mixed formats, timezone-naive, etc.
        """
        df = df.copy()
        
        # Debug: Show raw timestamps before parsing
        sample_ts = df[timestamp_col].head(3).tolist()
        logger.info(f"  {source_name} raw timestamps sample: {sample_ts}")
        
        # Convert to string for cleaning
        ts_str = df[timestamp_col].astype(str)
        
        # Fix ALL known malformed timestamp patterns:
        # 1. "+00:00Z" -> "+00:00" (redundant timezone indicators)
        ts_str = ts_str.str.replace(r'\+00:00Z$', '+00:00', regex=True)
        # 2. "-00:00Z" -> "-00:00" (negative offset variant)
        ts_str = ts_str.str.replace(r'-00:00Z$', '-00:00', regex=True)
        # 3. Any "+HH:MMZ" -> "+HH:MM" (general case)
        ts_str = ts_str.str.replace(r'([+-]\d{2}:\d{2})Z$', r'\1', regex=True)
        # 4. ".000000Z" -> "Z" (simplify microseconds with Z)
        ts_str = ts_str.str.replace(r'\.0+Z$', 'Z', regex=True)
        # 5. ".000000+00:00" -> "+00:00" (simplify microseconds with offset)
        ts_str = ts_str.str.replace(r'\.0+(\+|-)', r'\1', regex=True)
        # 6. Handle "nan" or empty strings
        ts_str = ts_str.replace(['nan', 'None', 'NaT', ''], pd.NA)
        
        df[timestamp_col] = ts_str
        
        # Debug: Show timestamps after fixing
        sample_ts_fixed = df[timestamp_col].head(3).tolist()
        logger.info(f"  {source_name} fixed timestamps sample: {sample_ts_fixed}")
        
        # Parse timestamps - handle various formats with UTC
        df["dt"] = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        
        # Count parsing failures
        n_failed = df["dt"].isna().sum()
        if n_failed > 0:
            logger.warning(f"  {source_name}: {n_failed} timestamps failed to parse")
        
        df = df.dropna(subset=["dt"])
        
        if df.empty:
            logger.warning(f"  {source_name}: All timestamps failed to parse!")
            return df
        
        # Snap to 15-minute grid (handles seconds offsets and minor drifts)
        df["dt"] = df["dt"].dt.floor('15min')
        
        # Remove timezone info for consistent comparison (all is UTC)
        df["dt"] = df["dt"].dt.tz_localize(None)
        
        # Debug: Show parsed timestamps
        sample_dt = df["dt"].head(3).tolist()
        logger.info(f"  {source_name} parsed dt sample (UTC, tz-naive): {sample_dt}")
        
        return df
    
    # --- Helper: Find the actual irradiance column ---
    def find_irr_column(df: pd.DataFrame) -> Optional[str]:
        candidates = [irr_col, f"{irr_col}_value", 'poaIrradiance', 'poaIrradiance_value', 
                      'GTI', 'gti', 'POA', 'poa', 'irradiance', 'Irradiance']
        for c in candidates:
            if c in df.columns:
                return c
        # Broader search
        for c in df.columns:
            if any(x in c.lower() for x in ['irradiance', 'poa', 'gti']):
                return c
        return None
    
    # --- Process a single season ---
    def process_single_season(inv_df: pd.DataFrame, irr_df: Optional[pd.DataFrame], season_name: str) -> pd.DataFrame:
        """Process one season and return hourly efficiency profiles."""
        
        # Normalize inverter timestamps
        inv = normalize_timestamps(inv_df, f"{season_name}_Inverter")
        logger.info(f"{season_name} Inverter: {len(inv)} rows after timestamp normalization")
        
        if inv.empty:
            logger.warning(f"{season_name}: No valid inverter data after timestamp parsing")
            return pd.DataFrame()
        
        # Check power column
        if power_col not in inv.columns:
            logger.error(f"{season_name}: Power column '{power_col}' not found. Available: {list(inv.columns)}")
            return pd.DataFrame()
        
        # Filter valid power readings
        inv = inv[inv[power_col] > 0]
        logger.info(f"{season_name} Inverter: {len(inv)} rows with positive power")
        
        if inv.empty:
            return pd.DataFrame()
        
        # Handle irradiance - try multiple sources
        irr_agg = None
        irr_source = None
        
        # Helper: Auto-detect and convert kW/m² to W/m² if needed
        def normalize_irradiance_units(values: pd.Series, col_name: str) -> pd.Series:
            """
            Auto-detect if irradiance is in kW/m² and convert to W/m².
            Some data sources incorrectly label kW/m² as W/m².
            Detection: If max value < 2.0, assume kW/m² and multiply by 1000.
            """
            if values.empty:
                return values
            max_val = values.max()
            if max_val < 2.0 and max_val > 0:
                # Likely kW/m² - convert to W/m²
                logger.warning(f"  *** Irradiance appears to be in kW/m² (max={max_val:.4f}). Converting to W/m².")
                return values * 1000
            return values
        
        # First, try separate irradiance dataframe if provided
        if irr_df is not None and not irr_df.empty:
            irr = normalize_timestamps(irr_df, f"{season_name}_Irradiance")
            logger.info(f"{season_name} Irradiance: {len(irr)} rows after timestamp normalization")
            
            # Find the actual irradiance column
            actual_irr_col = find_irr_column(irr)
            if actual_irr_col is not None:
                logger.info(f"{season_name}: Using irradiance column '{actual_irr_col}'")
                
                # DEBUG: Show irradiance value statistics BEFORE filtering
                irr_values = irr[actual_irr_col].dropna()
                logger.info(f"{season_name} Irradiance stats BEFORE conversion:")
                logger.info(f"  Count: {len(irr_values)}, Min: {irr_values.min():.4f}, Max: {irr_values.max():.4f}, Mean: {irr_values.mean():.4f}")
                
                # Normalize units (convert kW/m² to W/m² if needed)
                irr[actual_irr_col] = normalize_irradiance_units(irr[actual_irr_col], actual_irr_col)
                
                # Show stats after conversion
                irr_values = irr[actual_irr_col].dropna()
                logger.info(f"{season_name} Irradiance stats AFTER conversion:")
                logger.info(f"  Count: {len(irr_values)}, Min: {irr_values.min():.2f}, Max: {irr_values.max():.2f}, Mean: {irr_values.mean():.2f}")
                logger.info(f"  Values > 0: {(irr_values > 0).sum()}, Values >= {cfg.irradiance_min}: {(irr_values >= cfg.irradiance_min).sum()}")
                
                # Aggregate irradiance to single value per timestamp (handles multiple sensors)
                irr_agg_tmp = irr.groupby("dt")[actual_irr_col].median().reset_index()
                irr_agg_tmp = irr_agg_tmp.rename(columns={actual_irr_col: "irr"})
                
                # DEBUG: Show aggregated stats
                logger.info(f"{season_name} Irradiance after aggregation: {len(irr_agg_tmp)} timestamps")
                if not irr_agg_tmp.empty:
                    logger.info(f"  Aggregated min: {irr_agg_tmp['irr'].min():.2f}, max: {irr_agg_tmp['irr'].max():.2f}")
                
                # Filter low irradiance
                irr_agg_filtered = irr_agg_tmp[irr_agg_tmp["irr"] >= cfg.irradiance_min]
                logger.info(f"{season_name} Irradiance: {len(irr_agg_filtered)} rows after filtering >= {cfg.irradiance_min} W/m²")
                
                if not irr_agg_filtered.empty:
                    irr_agg = irr_agg_filtered
                    irr_source = "separate POA dataframe"
            else:
                logger.warning(f"{season_name}: Could not find irradiance column in separate data. Available: {list(irr.columns)}")
        
        # Fallback: Try embedded irradiance in inverter data
        if irr_agg is None or irr_agg.empty:
            embedded_irr_col = find_irr_column(inv)
            if embedded_irr_col is not None:
                logger.info(f"{season_name}: Trying embedded irradiance from inverter data column '{embedded_irr_col}'")
                
                # Check if there's valid embedded irradiance
                embedded_irr_values = inv[embedded_irr_col].dropna()
                
                # Normalize units
                inv[embedded_irr_col] = normalize_irradiance_units(inv[embedded_irr_col], embedded_irr_col)
                embedded_irr_values = inv[embedded_irr_col].dropna()
                
                valid_embedded = (embedded_irr_values >= cfg.irradiance_min).sum()
                logger.info(f"  Embedded irradiance: {len(embedded_irr_values)} values, {valid_embedded} >= {cfg.irradiance_min} W/m²")
                
                if valid_embedded > 0:
                    # Use embedded irradiance directly (already aligned with inverter timestamps)
                    inv["irr"] = inv[embedded_irr_col]
                    irr_source = "embedded in inverter data"
                    logger.info(f"{season_name}: Using embedded irradiance from inverter data")
        
        # Process based on irradiance availability
        if irr_agg is not None and not irr_agg.empty:
            # Separate irradiance - need to merge
            logger.info(f"{season_name}: Using irradiance from {irr_source}")
            
            # DEBUG: Check date overlap
            inv_dates = set(inv['dt'].dt.date.unique())
            irr_dates = set(irr_agg['dt'].dt.date.unique())
            common_dates = inv_dates & irr_dates
            logger.info(f"{season_name}: Inv dates={len(inv_dates)}, Irr dates={len(irr_dates)}, Common={len(common_dates)}")
            
            # DEBUG: Check hour distribution
            inv_hours = sorted(inv['dt'].dt.hour.unique().tolist())
            irr_hours = sorted(irr_agg['dt'].dt.hour.unique().tolist())
            logger.info(f"{season_name}: Inv hours={inv_hours[:5]}...{inv_hours[-5:] if len(inv_hours) > 5 else ''}")
            logger.info(f"{season_name}: Irr hours={irr_hours[:5]}...{irr_hours[-5:] if len(irr_hours) > 5 else ''}")
            
            if len(common_dates) == 0:
                logger.warning(f"{season_name}: NO COMMON DATES between inverter and irradiance!")
                logger.info(f"  Sample Inv dates: {sorted(list(inv_dates))[:5]}")
                logger.info(f"  Sample Irr dates: {sorted(list(irr_dates))[:5]}")
                return pd.DataFrame()
            
            # Merge inverter with irradiance on timestamp
            merged = inv.merge(irr_agg, on="dt", how="inner")
            logger.info(f"{season_name}: {len(merged)} rows after merging inv+irr")
            
            if merged.empty:
                # More debug
                logger.warning(f"{season_name}: Merge produced no results!")
                logger.info(f"  Sample Inv dt: {inv['dt'].iloc[:3].tolist()}")
                logger.info(f"  Sample Irr dt: {irr_agg['dt'].iloc[:3].tolist()}")
                return pd.DataFrame()
            
            # Calculate efficiency = Power / Irradiance
            merged["efficiency"] = merged[power_col] / merged["irr"]
            
        elif irr_source == "embedded in inverter data":
            # Embedded irradiance - already in inv dataframe
            logger.info(f"{season_name}: Using embedded irradiance from inverter data")
            
            # Filter by irradiance threshold
            merged = inv[inv["irr"] >= cfg.irradiance_min].copy()
            logger.info(f"{season_name}: {len(merged)} rows with irradiance >= {cfg.irradiance_min} W/m²")
            
            if merged.empty:
                logger.warning(f"{season_name}: No data with sufficient irradiance")
                return pd.DataFrame()
            
            # Calculate efficiency = Power / Irradiance
            merged["efficiency"] = merged[power_col] / merged["irr"]
            
        else:
            # No irradiance - use raw power as "efficiency" (less accurate)
            merged = inv.copy()
            merged["efficiency"] = merged[power_col]
            logger.info(f"{season_name}: Using raw power (no irradiance data)")
        
        # Add hour_float for binning
        merged["hour_float"] = merged["dt"].dt.hour + merged["dt"].dt.minute / 60.0
        
        # Build hourly profile: median efficiency per (inverter, hour)
        profile = (
            merged.groupby([emig_id_col, "hour_float"])["efficiency"]
            .agg(["median", "count"])
            .reset_index()
        )
        profile = profile[profile["count"] >= cfg.min_points_per_hour]
        profile = profile.rename(columns={"median": "eff_median", "count": "n_points"})
        
        logger.info(f"{season_name}: Built profile with {len(profile)} (inverter, hour) combinations")
        
        return profile
    
    # --- Process both seasons ---
    logger.info("="*60)
    logger.info("Processing SUMMER (baseline) data...")
    prof_summer = process_single_season(summer_inv_df, summer_irr_df, "Summer")
    
    logger.info("="*60)
    logger.info("Processing WINTER (comparison) data...")
    prof_winter = process_single_season(winter_inv_df, winter_irr_df, "Winter")
    
    if prof_summer.empty:
        logger.warning("Summer profile is empty - cannot proceed")
        return pd.DataFrame(), pd.DataFrame()
    
    if prof_winter.empty:
        logger.warning("Winter profile is empty - cannot proceed")
        return pd.DataFrame(), pd.DataFrame()
    
    logger.info("="*60)
    logger.info(f"Comparing profiles: Summer={len(prof_summer)} points, Winter={len(prof_winter)} points")
    
    # --- Compare profiles ---
    merged = compare_profiles(prof_summer, prof_winter, cfg)
    
    if merged.empty:
        logger.warning("No overlapping (inverter, hour) combinations between seasons")
        # Debug info
        logger.info(f"Summer inverters: {prof_summer[cfg.emigid_col].unique()[:5].tolist()}")
        logger.info(f"Winter inverters: {prof_winter[cfg.emigid_col].unique()[:5].tolist()}")
        logger.info(f"Summer hours: {sorted(prof_summer['hour_float'].unique()[:10].tolist())}")
        logger.info(f"Winter hours: {sorted(prof_winter['hour_float'].unique()[:10].tolist())}")
        return pd.DataFrame(), pd.DataFrame()
    
    logger.info(f"Merged comparison: {len(merged)} (inverter, hour) data points")
    
    # --- Summarize ---
    summary = summarise_shading(merged, cfg)
    
    return merged, summary
