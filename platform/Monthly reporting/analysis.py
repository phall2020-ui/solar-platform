"""
Solar Data Analysis Module

This module provides data processing and analysis capabilities for solar portfolio
performance, including loss calculations, variance analysis, column detection,
and visualization utilities for solar energy data.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import re
import streamlit as st

from config import Config


class DataProcessor:
    """
    Data processor for cleaning and validating uploaded solar data.

    This class provides static methods for cleaning uploaded data files
    and reporting on data quality metrics like completeness and missing values.
    """

    @staticmethod
    def clean_uploaded_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean uploaded DataFrame by normalizing column names.

        Args:
            df: Raw DataFrame from uploaded file.

        Returns:
            Cleaned DataFrame with trimmed column names.
        """
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        return df

    @staticmethod
    def validate_data_quality(df: pd.DataFrame, colmap: Dict[str, str]) -> Dict[str, any]:
        """
        Validate data quality and generate a quality report.

        Args:
            df: DataFrame to validate.
            colmap: Column mapping dictionary.

        Returns:
            Dictionary containing row count, completeness metrics, and missing data details.
        """
        report = {
            "row_count": len(df),
            "completeness": 100.0,
            "missing_data": {},
            "outliers": {},
        }
        for key, col in colmap.items():
            if col and col in df.columns:
                missing = df[col].isna().sum()
                if missing > 0:
                    report["missing_data"][col] = {
                        "count": int(missing),
                        "percentage": float(missing / len(df) * 100),
                    }
        return report


class SolarDataAnalyzer:
    """
    Analyzer for calculating solar technical losses and budget variances.

    This class performs calculations of weather variance, technical losses,
    PR variance, availability losses, and yield for solar assets based on
    mapped column data.
    """

    def __init__(self, df: pd.DataFrame, colmap: Dict[str, str]) -> None:
        self.df = df.copy()
        self.colmap = colmap
        self._validate_columns()

    def _validate_columns(self):
        missing = []
        for key, col in self.colmap.items():
            if col and col not in self.df.columns:
                missing.append(f"{key} -> {col}")
        if missing:
            raise ValueError(f"Mapped columns not found in data: {', '.join(missing)}")

    def _get_col(self, key: str) -> Optional[str]:
        """
        Get the actual column name from the column mapping.

        Args:
            key: Canonical column key (e.g., "actual_gen", "pr_actual").

        Returns:
            Actual column name if it exists and is mapped, None otherwise.
        """
        c = self.colmap.get(key)
        return c if c and c in self.df.columns else None

    def _normalize_percentage(self, series: pd.Series) -> pd.Series:
        """
        Normalize percentage values to decimal scale (0-1).

        Args:
            series: Series containing percentage values.

        Returns:
            Series with values normalized to 0-1 scale (values > 1 are divided by 100).
        """
        return np.where(series > 1, series / 100, series)

    def _normalize_to_percent_scale(self, series: pd.Series) -> pd.Series:
        """
        Convert availability/PR values to 0-100 percentage scale.

        Values <= 1 are assumed to be fractions and are multiplied by 100.
        Values > 1 are assumed to already be percentages and are left as-is.

        Args:
            series: Series containing percentage or fractional values.

        Returns:
            Series with values normalized to 0-100 scale.
        """
        return np.where(series <= 1, series * 100, series)

    def compute_losses(self) -> pd.DataFrame:
        """
        Calculate all loss metrics and variances for solar performance analysis.

        This method computes:
        - Total technical loss (WAB - Actual)
        - Weather variance (WAB - Budget)
        - Total budget variance (Actual - Budget)
        - PR loss (based on PR variance)
        - Availability loss
        - PR variance (percentage points)
        - Availability variance (percentage points)
        - Yield (kWh/kWp)

        Returns:
            DataFrame with all original data plus calculated loss and variance columns.
        """
        df = self.df

        # Get column names from mapping
        col_Act = self._get_col("actual_gen")
        col_WAB = self._get_col("wab")
        col_Bud = self._get_col("budget_gen")
        col_PRa = self._get_col("pr_actual")
        col_PRb = self._get_col("pr_budget")
        col_Ava = self._get_col("availability")
        col_Cap = self._get_col("capacity")

        if col_WAB and col_Act:
            df["Loss_Total_Tech_kWh"] = df[col_WAB] - df[col_Act]

        if col_WAB and col_Bud:
            df["Var_Weather_kWh"] = df[col_WAB] - df[col_Bud]

        if col_Act and col_Bud:
            df["Var_Total_Budget_kWh"] = df[col_Act] - df[col_Bud]

        if col_WAB:
            if col_PRa and col_PRb:
                pra = self._normalize_percentage(df[col_PRa])
                prb = self._normalize_percentage(df[col_PRb])
                df["Loss_PR_kWh"] = df[col_WAB] * (prb - pra)

            if col_Ava:
                ava = self._normalize_percentage(df[col_Ava])
                df["Loss_Avail_kWh"] = df[col_WAB] * (0.99 - ava)

        if col_PRa and col_PRb:
            pra = self._normalize_percentage(df[col_PRa])
            prb = self._normalize_percentage(df[col_PRb])
            df["Var_PR_pp"] = (prb - pra) * 100

        if col_Ava:
            ava_percent = self._normalize_to_percent_scale(df[col_Ava])
            df["Var_Availability_pp"] = Config.TARGET_AVAILABILITY - ava_percent
            df["Availability_Actual_%"] = ava_percent

        if col_Act and col_Cap:
            capacity = df[col_Cap]
            if capacity.dtype == "object":
                capacity = pd.to_numeric(capacity.astype(str).str.replace(",", ""), errors="coerce")
            df["Yield_kWh_per_kWp"] = df[col_Act] / capacity

        return df


@st.cache_data(ttl=Config.CACHE_TTL, show_spinner=False)
def detect_column_candidates(df_columns: tuple) -> Dict[str, str]:
    """
    Auto-detect column mappings based on pattern matching.

    Uses regex patterns defined in Config.COLUMN_PATTERNS to automatically
    identify which columns in the DataFrame correspond to standard solar
    data fields (actual generation, WAB, budget, PR, availability, etc.).

    Args:
        df_columns: Tuple of column names from the DataFrame.

    Returns:
        Dictionary mapping canonical column keys to detected column names.
    """
    cols = list(df_columns)
    detected = {}

    def score(col: str, patterns: List[str]) -> int:
        """Score a column name against a list of regex patterns."""
        s = 0
        c_lower = col.lower().strip()
        for p in patterns:
            if re.search(p, c_lower):
                s += 1
        return s

    for key, patterns in Config.COLUMN_PATTERNS.items():
        best_col = None
        best_score = 0
        for col in cols:
            s = score(col, patterns)
            if s > best_score:
                best_score = s
                best_col = col
        detected[key] = best_col

    return detected


def weighted_average(df: pd.DataFrame, val_col: str, wt_col: str) -> float:
    """
    Calculate weighted average of a column using another column as weights.

    Args:
        df: DataFrame containing the data.
        val_col: Name of the column to average.
        wt_col: Name of the column to use as weights.

    Returns:
        Weighted average value, or NaN if calculation not possible.
    """
    mask = df[[val_col, wt_col]].notna().all(axis=1)
    d = df[mask]
    if d.empty:
        return np.nan

    total_weight = d[wt_col].sum()
    if total_weight == 0:
        return np.nan

    return (d[val_col] * d[wt_col]).sum() / total_weight


def add_time_period_column(
    df: pd.DataFrame, date_col: str, mode: str, fiscal_year_start_month: int = 4
) -> pd.DataFrame:
    """
    Add a time period column to the DataFrame based on the specified aggregation mode.

    Converts date values into period labels for grouping (daily, weekly, monthly,
    quarterly, YTD, or annual). Quarterly and annual calculations respect the
    specified fiscal year start month.

    Args:
        df: DataFrame to add period column to.
        date_col: Name of the date column.
        mode: Time period mode - "Daily", "Weekly", "Monthly", "Quarterly", "YTD", or "Annual".
        fiscal_year_start_month: Month that starts the fiscal year (1-12, default 4 for April).

    Returns:
        DataFrame with added "Period" column.
    """
    date_formats = ["%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%y"]
    dates = None
    for fmt in date_formats:
        try:
            dates = pd.to_datetime(df[date_col], format=fmt, errors="raise")
            break
        except Exception:
            continue
    if dates is None:
        dates = pd.to_datetime(df[date_col], errors="coerce")

    if mode == "Daily":
        df["Period"] = dates.dt.strftime("%Y-%m-%d")
    elif mode == "Weekly":
        df["Period"] = dates.dt.to_period("W").astype(str)
    elif mode == "Monthly":
        df["Period"] = dates.dt.to_period("M").astype(str)
    elif mode == "Quarterly":
        month = dates.dt.month
        year = dates.dt.year
        fiscal_quarter = ((month - fiscal_year_start_month) % 12) // 3 + 1
        fiscal_year = np.where(month < fiscal_year_start_month, year, year + 1)
        df["Period"] = "FY" + fiscal_year.astype(str) + "-Q" + fiscal_quarter.astype(str)
    elif mode == "YTD":
        month = dates.dt.month
        year = dates.dt.year
        fiscal_year = np.where(month < fiscal_year_start_month, year, year + 1)
        df["Period"] = "YTD FY" + fiscal_year.astype(str)
    elif mode == "Annual":
        month = dates.dt.month
        year = dates.dt.year
        fiscal_year = np.where(month < fiscal_year_start_month, year, year + 1)
        df["Period"] = "FY" + fiscal_year.astype(str)

    return df


def aggregate_flexible(
    df: pd.DataFrame,
    date_col: Optional[str],
    groupby_cols: List[str],
    time_period: Optional[str],
    metrics: List[str],
    colmap: Dict[str, str],
    fiscal_year_start: int = 4,
) -> pd.DataFrame:
    """
    Flexibly aggregate solar data by time periods and grouping columns.

    Performs aggregation with intelligent handling of different metric types:
    - Energy metrics (kWh, MWh) are summed
    - Performance ratios and availability are weighted-averaged by generation
    - Variance metrics are recalculated after aggregation

    Args:
        df: DataFrame to aggregate.
        date_col: Name of the date column for time-based grouping.
        groupby_cols: List of column names to group by (e.g., ["Site"]).
        time_period: Time aggregation level ("Daily", "Monthly", "Quarterly", "YTD", "Annual", or None).
        metrics: List of metric column names to aggregate.
        colmap: Column mapping dictionary.
        fiscal_year_start: Month that starts the fiscal year (default 4 for April).

    Returns:
        Aggregated DataFrame with calculated metrics.
    """
    if df.empty:
        return pd.DataFrame()

    df_agg = df.copy()

    # Build grouping columns
    group_cols = []
    if date_col and time_period and time_period != "None":
        df_agg = add_time_period_column(df_agg, date_col, time_period, fiscal_year_start)
        group_cols.append("Period")

    group_cols.extend(groupby_cols)

    if not group_cols:
        group_cols = ["_total"]
        df_agg["_total"] = "Total"

    agg_dict = {}

    # Get column names for weighted averaging
    weight_col = colmap.get("actual_gen")
    pr_actual_col = colmap.get("pr_actual")
    pr_budget_col = colmap.get("pr_budget")
    avail_col = colmap.get("availability")
    capacity_col = colmap.get("capacity")

    sum_metrics = []
    weighted_avg_metrics = []

    # Classify metrics for appropriate aggregation
    for m in metrics:
        if m not in df_agg.columns:
            continue

        m_lower = m.lower()

        if (
            any(x in m for x in ["kWh", "MWh", "MW", "kW"])
            or any(x in m_lower for x in ["gen", "energy", "power", "loss", "irrad"])
            or (m.startswith("Var_") and "kWh" in m)
        ):
            sum_metrics.append(m)
            agg_dict[m] = "sum"
        elif (
            any(x in m for x in ["%", "PR", "Avail", "Yield"])
            or any(x in m_lower for x in ["ratio", "factor", "efficiency", "performance"])
        ) and m not in [pr_actual_col, pr_budget_col, avail_col]:
            weighted_avg_metrics.append(m)

    if agg_dict:
        result_df = df_agg.groupby(group_cols, as_index=False).agg(agg_dict)
    else:
        result_df = df_agg[group_cols].drop_duplicates()

    if weight_col and weight_col in df_agg.columns:
        for col, target_col in [
            (pr_actual_col, "PR_Actual_Avg_%"),
            (pr_budget_col, "PR_Budget_Avg_%"),
            (avail_col, "Availability_Avg_%"),
        ]:
            if col and col in df_agg.columns:
                weighted = (
                    df_agg.groupby(group_cols)
                    .apply(lambda x: weighted_average(x, col, weight_col))
                    .reset_index(name=target_col)
                )
                result_df = result_df.merge(weighted, on=group_cols, how="left")

        for m in weighted_avg_metrics:
            weighted = (
                df_agg.groupby(group_cols).apply(lambda x: weighted_average(x, m, weight_col)).reset_index(name=m)
            )
            result_df = result_df.merge(weighted, on=group_cols, how="left")

    if "PR_Actual_Avg_%" in result_df.columns and "PR_Budget_Avg_%" in result_df.columns:
        pr_act = np.where(
            result_df["PR_Actual_Avg_%"] > 1, result_df["PR_Actual_Avg_%"] / 100, result_df["PR_Actual_Avg_%"]
        )
        pr_bud = np.where(
            result_df["PR_Budget_Avg_%"] > 1, result_df["PR_Budget_Avg_%"] / 100, result_df["PR_Budget_Avg_%"]
        )
        result_df["Var_PR_pp"] = (pr_bud - pr_act) * 100

    if "Availability_Avg_%" in result_df.columns:
        avail_pct = np.where(
            result_df["Availability_Avg_%"] <= 1, result_df["Availability_Avg_%"] * 100, result_df["Availability_Avg_%"]
        )
        result_df["Availability_Avg_%"] = avail_pct
        result_df["Var_Availability_pp"] = 99.0 - avail_pct

    if capacity_col and capacity_col in df_agg.columns:
        actual_gen_col = colmap.get("actual_gen")
        if actual_gen_col and actual_gen_col in result_df.columns:
            capacity_sum = df_agg.groupby(group_cols)[capacity_col].sum().reset_index()
            result_df = result_df.merge(capacity_sum, on=group_cols, how="left", suffixes=("", "_cap"))
            result_df["Yield_kWh_per_kWp"] = result_df[actual_gen_col] / result_df[capacity_col]
            result_df.drop(columns=[capacity_col], inplace=True, errors="ignore")

    return result_df


def plot_waterfall(df_single_row: pd.DataFrame, colmap: Dict[str, str]) -> Optional[go.Figure]:
    """
    Create a waterfall chart showing the breakdown from budget to actual generation.

    The waterfall visualizes:
    Budget → Weather Variance → WAB → PR Loss → Availability Loss → Actual

    Args:
        df_single_row: DataFrame with a single row containing all required metrics.
        colmap: Column mapping dictionary.

    Returns:
        Plotly Figure object with the waterfall chart, or None if required columns are missing.
    """
    budget_col = colmap.get("budget_gen")
    actual_col = colmap.get("actual_gen")

    required_cols = [budget_col, "Var_Weather_kWh", "Loss_PR_kWh", "Loss_Avail_kWh", actual_col]
    if not all(c in df_single_row.columns and c is not None for c in required_cols):
        st.warning("Cannot plot Waterfall: Ensure Budget Gen and all loss metrics were calculated correctly.")
        return None

    wab_value = df_single_row[budget_col].iloc[0] + df_single_row["Var_Weather_kWh"].iloc[0]

    final_data = {
        "measure": ["absolute", "relative", "total", "relative", "relative", "absolute"],
        "x": ["Budget Gen", "Weather Δ", "WAB", "PR Loss", "Avail Loss", "Actual Gen"],
        "y": [
            df_single_row[budget_col].iloc[0],
            df_single_row["Var_Weather_kWh"].iloc[0],
            wab_value,
            -df_single_row["Loss_PR_kWh"].iloc[0],
            -df_single_row["Loss_Avail_kWh"].iloc[0],
            df_single_row[actual_col].iloc[0],
        ],
    }

    valid_indices = [i for i, y in enumerate(final_data["y"]) if y is not None and not np.isnan(y)]
    final_data = {k: [v[i] for i in valid_indices] for k, v in final_data.items()}

    fig = go.Figure(
        go.Waterfall(
            name="Loss Waterfall",
            orientation="v",
            measure=final_data["measure"],
            x=final_data["x"],
            textposition="outside",
            y=final_data["y"],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
        )
    )

    fig.update_layout(
        title="Solar Loss Waterfall: Budget to Actual Energy (kWh)",
        showlegend=False,
        height=600,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig
