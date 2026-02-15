#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass
class ComparisonArtifacts:
    merged_csv: Path
    overall_metrics_csv: Path
    site_metrics_csv: Path
    mapping_csv: Path
    scatter_png: Path
    monthly_trend_png: Path
    site_bias_png: Path


def _normalize_site_name(value: str) -> str:
    text = str(value).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\buk\b", "", text)
    text = text.replace("shopping centre", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _to_month_key(series: pd.Series, dt_format: str | None = None) -> pd.Series:
    dt = pd.to_datetime(series, format=dt_format, errors="coerce")
    return dt.dt.strftime("%Y-%m")


def _build_site_mapping(juggle_sites: list[str], solargis_sites: list[str]) -> pd.DataFrame:
    solargis_set = set(solargis_sites)
    manual_overrides = {
        "man city fc training ground": "city football group phase 1",
    }

    records: list[dict[str, str | None]] = []
    for site in sorted(juggle_sites):
        mapped: str | None = None
        method = "unmatched"

        if site in manual_overrides:
            candidate = manual_overrides[site]
            if candidate in solargis_set:
                mapped = candidate
                method = "manual"

        if mapped is None and site in solargis_set:
            mapped = site
            method = "exact"

        if mapped is None:
            matches = get_close_matches(site, solargis_sites, n=1, cutoff=0.75)
            if matches:
                mapped = matches[0]
                method = "fuzzy"

        records.append(
            {
                "juggle_site_norm": site,
                "solargis_site_norm": mapped,
                "mapping_method": method,
            }
        )

    return pd.DataFrame(records)


def _compute_metrics(merged: pd.DataFrame, juggle_col: str, solargis_col: str) -> pd.DataFrame:
    x = merged[juggle_col].astype(float)
    y = merged[solargis_col].astype(float)
    err = x - y
    abs_err = err.abs()

    mape = np.nan
    valid = y != 0
    if valid.any():
        mape = float((abs_err[valid] / y[valid]).mean() * 100)

    rmse = float(np.sqrt((err**2).mean())) if len(err) else np.nan
    corr = float(x.corr(y)) if len(merged) > 1 else np.nan

    scaled_err = (2.0 * x) - y
    scaled_mape = np.nan
    if valid.any():
        scaled_mape = float(((scaled_err.abs()[valid]) / y[valid]).mean() * 100)

    return pd.DataFrame(
        [
            {
                "overlap_rows": int(len(merged)),
                "overlap_sites": int(merged["site_original"].nunique()),
                "overlap_months": int(merged["month"].nunique()),
                "mae": float(abs_err.mean()),
                "mape_pct": mape,
                "bias": float(err.mean()),
                "rmse": rmse,
                "correlation": corr,
                "mae_scaled_x2": float(scaled_err.abs().mean()),
                "mape_pct_scaled_x2": scaled_mape,
                "bias_scaled_x2": float(scaled_err.mean()),
            }
        ]
    )


def _site_correlation(group: pd.DataFrame) -> float:
    if len(group) < 2:
        return np.nan
    return float(group["juggle_poa_kwh_m2"].corr(group["solargis_gti_kwh_m2"]))


def _write_plots(merged: pd.DataFrame, out_dir: Path, juggle_col: str, solargis_col: str) -> tuple[Path, Path, Path]:
    scatter_png = out_dir / "scatter_juggle_vs_solargis.png"
    monthly_trend_png = out_dir / "monthly_trend_juggle_vs_solargis.png"
    site_bias_png = out_dir / "site_bias_juggle_minus_solargis.png"

    plt.style.use("seaborn-v0_8-whitegrid")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(merged[solargis_col], merged[juggle_col], alpha=0.8)
    minv = float(min(merged[solargis_col].min(), merged[juggle_col].min()))
    maxv = float(max(merged[solargis_col].max(), merged[juggle_col].max()))
    ax.plot([minv, maxv], [minv, maxv], linestyle="--", color="black", linewidth=1, label="1:1")
    ax.plot([minv, maxv], [0.5 * minv, 0.5 * maxv], linestyle=":", color="red", linewidth=1, label="0.5x")
    ax.set_xlabel("SolarGIS GTI (kWh/m²)")
    ax.set_ylabel("Juggle POA (kWh/m²)")
    ax.set_title("Juggle vs SolarGIS (site-month)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(scatter_png, dpi=150)
    plt.close(fig)

    month_df = (
        merged.groupby("month", as_index=False)[[juggle_col, solargis_col]].mean().sort_values("month")
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(month_df["month"], month_df[juggle_col], marker="o", label="Juggle")
    ax.plot(month_df["month"], month_df[solargis_col], marker="o", label="SolarGIS")
    ax.set_xlabel("Month")
    ax.set_ylabel("Average irradiance (kWh/m²)")
    ax.set_title("Monthly trend: Juggle vs SolarGIS")
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    fig.tight_layout()
    fig.savefig(monthly_trend_png, dpi=150)
    plt.close(fig)

    bias_df = (
        merged.assign(bias=lambda d: d[juggle_col] - d[solargis_col])
        .groupby("site_original", as_index=False)["bias"]
        .mean()
        .sort_values("bias")
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(bias_df["site_original"], bias_df["bias"])
    ax.axvline(0.0, color="black", linewidth=1)
    ax.set_xlabel("Mean bias (Juggle - SolarGIS) kWh/m²")
    ax.set_ylabel("Site")
    ax.set_title("Average bias by site")
    fig.tight_layout()
    fig.savefig(site_bias_png, dpi=150)
    plt.close(fig)

    return scatter_png, monthly_trend_png, site_bias_png


def create_artifacts(output_dir: Path) -> ComparisonArtifacts:
    root = Path(__file__).resolve().parents[2]
    juggle_path = root / "tools" / "inverter-data-juggle" / "poa_monthly_summary.csv"
    solargis_path = root / "tools" / "irradiation-data" / "summary_monthly_all_sites.csv"

    juggle = pd.read_csv(juggle_path)
    solargis = pd.read_csv(solargis_path)

    juggle = juggle.rename(
        columns={
            "Plant": "site_original",
            "Month": "month_raw",
            "Total POA (kWh/m²)": "juggle_poa_kwh_m2",
        }
    )
    juggle["month"] = _to_month_key(juggle["month_raw"], dt_format="%B %Y")
    juggle["site_norm"] = juggle["site_original"].map(_normalize_site_name)

    solargis = solargis.rename(columns={"name": "solargis_site", "time": "time_raw", "gti": "solargis_gti_kwh_m2"})
    solargis["month"] = _to_month_key(solargis["time_raw"], dt_format="%Y-%m-%d")
    solargis["site_norm"] = solargis["solargis_site"].map(_normalize_site_name)

    mapping = _build_site_mapping(
        sorted(juggle["site_norm"].dropna().unique().tolist()),
        sorted(solargis["site_norm"].dropna().unique().tolist()),
    )

    mapped = juggle.merge(mapping, left_on="site_norm", right_on="juggle_site_norm", how="left")
    mapped["site_norm_matched"] = mapped["solargis_site_norm"].fillna(mapped["site_norm"])

    merged = mapped.merge(
        solargis[["site_norm", "month", "solargis_site", "solargis_gti_kwh_m2"]],
        left_on=["site_norm_matched", "month"],
        right_on=["site_norm", "month"],
        how="inner",
        suffixes=("", "_sg"),
    )

    if merged.empty:
        raise RuntimeError("No overlapping site-month rows found between Juggle and SolarGIS data.")

    merged = merged[
        [
            "site_original",
            "solargis_site",
            "month",
            "juggle_poa_kwh_m2",
            "solargis_gti_kwh_m2",
            "mapping_method",
        ]
    ].copy()
    merged["difference_kwh_m2"] = merged["juggle_poa_kwh_m2"] - merged["solargis_gti_kwh_m2"]
    merged["abs_difference_kwh_m2"] = merged["difference_kwh_m2"].abs()
    merged["pct_error"] = np.where(
        merged["solargis_gti_kwh_m2"] != 0,
        (merged["abs_difference_kwh_m2"] / merged["solargis_gti_kwh_m2"]) * 100,
        np.nan,
    )

    site_metrics = (
        merged.groupby("site_original", as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "rows": int(len(g)),
                    "mae_kwh_m2": float(g["abs_difference_kwh_m2"].mean()),
                    "mape_pct": float(g["pct_error"].mean()),
                    "bias_kwh_m2": float(g["difference_kwh_m2"].mean()),
                    "correlation": _site_correlation(g),
                }
            ),
            include_groups=False,
        )
        .sort_values(["mae_kwh_m2", "site_original"], ascending=[False, True])
    )

    overall_metrics = _compute_metrics(merged, "juggle_poa_kwh_m2", "solargis_gti_kwh_m2")

    output_dir.mkdir(parents=True, exist_ok=True)

    merged_csv = output_dir / "juggle_vs_solargis_merged.csv"
    overall_metrics_csv = output_dir / "juggle_vs_solargis_metrics.csv"
    site_metrics_csv = output_dir / "juggle_vs_solargis_metrics_by_site.csv"
    mapping_csv = output_dir / "juggle_vs_solargis_site_mapping.csv"

    merged.sort_values(["site_original", "month"]).to_csv(merged_csv, index=False)
    overall_metrics.to_csv(overall_metrics_csv, index=False)
    site_metrics.to_csv(site_metrics_csv, index=False)
    mapping.to_csv(mapping_csv, index=False)

    scatter_png, monthly_trend_png, site_bias_png = _write_plots(
        merged, output_dir, "juggle_poa_kwh_m2", "solargis_gti_kwh_m2"
    )

    return ComparisonArtifacts(
        merged_csv=merged_csv,
        overall_metrics_csv=overall_metrics_csv,
        site_metrics_csv=site_metrics_csv,
        mapping_csv=mapping_csv,
        scatter_png=scatter_png,
        monthly_trend_png=monthly_trend_png,
        site_bias_png=site_bias_png,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Juggle vs SolarGIS comparison CSVs and graphs.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tools/inverter-data-juggle/reports/juggle-vs-solargis"),
        help="Output directory for CSV and PNG artifacts.",
    )
    args = parser.parse_args()

    artifacts = create_artifacts(args.output_dir)
    print("Created artifacts:")
    print(f"- {artifacts.merged_csv}")
    print(f"- {artifacts.overall_metrics_csv}")
    print(f"- {artifacts.site_metrics_csv}")
    print(f"- {artifacts.mapping_csv}")
    print(f"- {artifacts.scatter_png}")
    print(f"- {artifacts.monthly_trend_png}")
    print(f"- {artifacts.site_bias_png}")


if __name__ == "__main__":
    main()