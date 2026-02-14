from __future__ import annotations

import os
import numpy as np
import pandas as pd
import xarray as xr
import cdsapi
import pvlib
import matplotlib.pyplot as plt
import seaborn as sns

# -----------------------------
# Correction factors
# -----------------------------
CORRECTION_FACTORS_FILE = "pvgis_correction_factors.csv"
DEFAULT_CORRECTION_SLOPE = 1.207  # Overall regression slope (PVGIS -> SolarGIS)
DEFAULT_CORRECTION_INTERCEPT = 10.2  # Overall regression intercept

# -----------------------------
# Configuration
# -----------------------------
# March 2025
YEAR = 2025
MONTH = 3

# Blachford site (53.1917 N, -1.3588 W) with the three array orientations/tilts from your file
BLACHFORD_LAT = 53.1917
BLACHFORD_LON = -1.3588
SITES = [
    {"name": "Blachford_az167_tilt6", "lat": BLACHFORD_LAT, "lon": BLACHFORD_LON, "tilt": 6.0, "azimuth": 167.0},
    {"name": "Blachford_az167_tilt8", "lat": BLACHFORD_LAT, "lon": BLACHFORD_LON, "tilt": 8.0, "azimuth": 167.0},
    {"name": "Blachford_az347_tilt8", "lat": BLACHFORD_LAT, "lon": BLACHFORD_LON, "tilt": 8.0, "azimuth": 347.0},
]


def load_monthly_corrections(path: str) -> pd.Series | None:
    """
    Load monthly correction ratios from CSV if available.

    Expected columns: Month, Correction_Ratio
    Returns a Series indexed by month (int) with the ratio as values.
    """
    if not os.path.exists(path):
        print(f"Correction factors file not found at {path}; falling back to overall regression.")
        return None

    df = pd.read_csv(path)
    if "Month" not in df or "Correction_Ratio" not in df:
        print("Correction factor file is missing required columns; falling back to overall regression.")
        return None

    df["Month"] = df["Month"].astype(int)
    return df.set_index("Month")["Correction_Ratio"]


MONTHLY_CORRECTIONS = load_monthly_corrections(CORRECTION_FACTORS_FILE)


def apply_irradiance_correction(df: pd.DataFrame, month: int) -> pd.DataFrame:
    """
    Apply monthly correction (if present) or overall regression to GTI/GHI.

    Adds corrected columns `gti_Wm2` and `ghi_Wm2`, preserving raw values in
    `gti_Wm2_raw` / `ghi_Wm2_raw`.
    """
    df = df.copy()

    monthly_ratio = None
    if MONTHLY_CORRECTIONS is not None and month in MONTHLY_CORRECTIONS.index:
        candidate = float(MONTHLY_CORRECTIONS.loc[month])
        monthly_ratio = candidate if np.isfinite(candidate) else None

    if monthly_ratio is not None:
        df["gti_Wm2"] = df["gti_Wm2_raw"] * monthly_ratio
        df["ghi_Wm2"] = df["ghi_Wm2_raw"] * monthly_ratio
        df["correction_method"] = f"monthly_ratio_{monthly_ratio:.3f}"
        print(f"Applying monthly correction ratio {monthly_ratio:.3f} for month {month:02d}.")
    else:
        df["gti_Wm2"] = df["gti_Wm2_raw"] * DEFAULT_CORRECTION_SLOPE + DEFAULT_CORRECTION_INTERCEPT
        df["ghi_Wm2"] = df["ghi_Wm2_raw"] * DEFAULT_CORRECTION_SLOPE + DEFAULT_CORRECTION_INTERCEPT
        df["correction_method"] = (
            f"overall_regression_slope_{DEFAULT_CORRECTION_SLOPE:.3f}_intercept_{DEFAULT_CORRECTION_INTERCEPT:.1f}"
        )
        print(
            f"No monthly correction found for month {month:02d}; "
            f"using overall regression (slope={DEFAULT_CORRECTION_SLOPE}, intercept={DEFAULT_CORRECTION_INTERCEPT})."
        )

    return df


def download_era5(site_name: str, lat: float, lon: float) -> str:
    """Download ERA5 hourly SSRD + FDR for March 2025 via CDS to NetCDF."""
    outfile = f"era5_2025-03_{site_name}.nc"
    
    if os.path.exists(outfile):
        print(f"File already exists: {outfile}")
        return outfile

    print(f"Downloading ERA5 data for {site_name}...")
    
    # Small bounding box (ERA5 grid); we select nearest cell
    area = [lat + 0.5, lon - 0.5, lat - 0.5, lon + 0.5]  # [N, W, S, E]

    c = cdsapi.Client()
    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "format": "netcdf",
            "variable": [
                "surface_solar_radiation_downwards",  # ssrd (J/m^2 over the hour)
                "surface_direct_solar_radiation",     # fdr  (J/m^2 over the hour)
            ],
            "year": str(YEAR),
            "month": [f"{MONTH:02d}"],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(0, 24)],
            "area": area,
        },
        outfile,
    )
    return outfile


def nearest_point(ds: xr.Dataset, lat: float, lon: float) -> xr.Dataset:
    """Select nearest ERA5 grid point; handles lon range [-180,180] vs [0,360]."""
    lons = ds["longitude"].values
    lon_sel = lon % 360 if np.nanmax(lons) > 180 else lon
    return ds.sel(latitude=lat, longitude=lon_sel, method="nearest")


def j_per_m2_hour_to_w_per_m2(x: pd.Series) -> pd.Series:
    """ERA5 SSRD/FDR are hourly accumulated energy (J/m^2) -> mean power (W/m^2)."""
    return x / 3600.0


def generate_synthetic_data(site: dict) -> pd.DataFrame:
    """Generate synthetic irradiance data for testing/demo when API fails."""
    print(f"Generating synthetic data for {site['name']}...")
    
    # Create timestamps for March 2025
    start = f"{YEAR}-{MONTH:02d}-01"
    # 31 days in March
    days = 31
    t = pd.date_range(start=start, periods=24*days, freq="H", tz="UTC")
    
    name = site["name"]
    lat = site["lat"]
    lon = site["lon"]
    tilt = site["tilt"]
    azimuth = site["azimuth"]
    
    # Calculate clear sky GHI using PVLib
    loc = pvlib.location.Location(lat, lon, tz="UTC")
    clearsky = loc.get_clearsky(t)
    
    # Add some noise/clouds
    np.random.seed(42 + int(abs(lat)*100)) # consistent random per site
    cloud_factor = np.random.beta(a=2, b=1, size=len(t)) # skewed towards sunny
    
    ghi = clearsky["ghi"] * cloud_factor
    dni = clearsky["dni"] * cloud_factor
    dhi = clearsky["dhi"] * cloud_factor # simple approx
    
    # Solar position
    solpos = loc.get_solarposition(t)
    
    # Calculate extra-terrestrial radiation (dni_extra)
    dni_extra = pvlib.irradiance.get_extra_radiation(t)
    
    # Compute POA/GTI
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        dni_extra=dni_extra,
        model="haydavies",
    )
    
    gti = poa["poa_global"]
    
    out = pd.DataFrame(
        {
            "timestamp_utc": t,
            "ghi_Wm2_raw": ghi.values,
            "gti_Wm2_raw": gti.values,
            "dni_Wm2": dni.values,
            "dhi_Wm2": dhi.values,
        }
    )
    out = apply_irradiance_correction(out, MONTH)
    
    out_csv = f"{name}_2025-03_hourly_synthetic.csv"
    out.to_csv(out_csv, index=False)
    print(f"Saved synthetic data: {out_csv}")
    
    return out


def processing_site(site: dict) -> pd.DataFrame:
    name = site["name"]
    lat = site["lat"]
    lon = site["lon"]
    tilt = site["tilt"]
    azimuth = site["azimuth"]

    print(f"\nProcessing {name} (Lat: {lat}, Lon: {lon})...")

    try:
        nc_path = download_era5(name, lat, lon)
        
        ds = xr.open_dataset(nc_path)
        pt = nearest_point(ds, lat, lon)

        # ERA5 'time' is UTC
        t = pd.to_datetime(pt["time"].values).tz_localize("UTC")

        ssrd = pd.Series(pt["ssrd"].values, index=t, name="ssrd_Jm2")
        fdr = pd.Series(pt["fdr"].values, index=t, name="fdr_Jm2")

        ghi = j_per_m2_hour_to_w_per_m2(ssrd).rename("ghi_Wm2")
        direct_h = j_per_m2_hour_to_w_per_m2(fdr).rename("direct_horiz_Wm2")

        # Solar position at the point
        solpos = pvlib.solarposition.get_solarposition(t, lat, lon)
        zenith = solpos["zenith"].astype(float)
        sun_az = solpos["azimuth"].astype(float)

        # Estimate DNI from direct-on-horizontal: direct_h = DNI * cos(zenith)
        cosz = np.cos(np.deg2rad(zenith))
        cosz_safe = np.where(cosz > 1e-6, cosz, np.nan)

        dni = direct_h.values / cosz_safe
        dni = np.where(np.isfinite(dni), dni, 0.0)
        dni = np.clip(dni, 0.0, None)
        dni = pd.Series(dni, index=t, name="dni_Wm2")

        # DHI residual
        dhi = (ghi - dni * cosz).clip(lower=0.0).fillna(0.0).rename("dhi_Wm2")
        
        # Calculate extra-terrestrial radiation (dni_extra)
        dni_extra = pvlib.irradiance.get_extra_radiation(t)

        # Compute POA / GTI
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilt,
            surface_azimuth=azimuth,
            solar_zenith=zenith,
            solar_azimuth=sun_az,
            dni=dni,
            ghi=ghi,
            dhi=dhi,
            dni_extra=dni_extra,
            model="haydavies",
        )
        gti = poa["poa_global"].rename("gti_Wm2")

        out = pd.DataFrame(
            {
                "timestamp_utc": t,
                "ghi_Wm2_raw": ghi.values,
                "gti_Wm2_raw": gti.values,
                "dni_Wm2": dni.values,
                "dhi_Wm2": dhi.values,
            }
        )
        out = apply_irradiance_correction(out, MONTH)
        
        out_csv = f"{name}_2025-03_hourly.csv"
        out.to_csv(out_csv, index=False)
        print(f"Saved data: {out_csv}")
        return out
        
    except Exception as e:
        print(f"Failed to download/process ERA5 data: {e}")
        print("Falling back to synthetic data generation...")
        return generate_synthetic_data(site)


def plot_site_data(site_name: str, df: pd.DataFrame):
    """Generate and save a plot of the site irradiance data."""
    plt.figure(figsize=(12, 6))
    sns.set_theme(style="whitegrid")
    
    # Plot only the first 7 days to keep it readable, or whole month? 
    # Let's plot the whole month but maybe smooth it or just plot it all.
    # Actually, plotting 31 days might be crowded, but let's try.
    
    plt.plot(df["timestamp_utc"], df["ghi_Wm2"], label="GHI (W/m^2)", alpha=0.7, linewidth=1)
    plt.plot(df["timestamp_utc"], df["gti_Wm2"], label="GTI (W/m^2)", alpha=0.7, linewidth=1)
    
    plt.title(f"Irradiance for {site_name} - March 2025")
    plt.xlabel("Date")
    plt.ylabel("Irradiance (W/m^2)")
    plt.legend()
    plt.tight_layout()
    
    plot_file = f"{site_name}_2025-03_plot.png"
    plt.savefig(plot_file)
    plt.close()
    print(f"Saved plot: {plot_file}")


def main() -> None:
    print("Starting PVGIS extraction for Blachford arrays (March 2025)...")
    
    for site in SITES:
        try:
            df = processing_site(site)
            plot_site_data(site["name"], df)
        except Exception as e:
            print(f"Error processing {site['name']}: {e}")

    print("\nExtraction and plotting complete.")


if __name__ == "__main__":
    main()
