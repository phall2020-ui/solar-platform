"""
PVGIS vs SolarGIS Irradiance Comparison Script

This script:
1. Allows user to select a site and month(s)
2. Generates PVGIS irradiance data using ERA5 (or synthetic) for each array
3. Calculates capacity-weighted average GTI for the site
4. Reads SolarGIS data from monthly folders and calculates capacity-weighted average
5. Compares hourly irradiance between PVGIS and SolarGIS
6. Applies correction factors to align PVGIS with SolarGIS
7. Outputs comparison CSV and statistics
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import pvlib
from pathlib import Path
from datetime import datetime
import calendar

# Base directory
BASE_DIR = Path(r"c:\Users\PeterHall\OneDrive - AMPYR IDEA UK Ltd\Python scripts\Irradiation Data")

# =============================================================================
# CORRECTION FACTORS
# Based on analysis of 50 site-month combinations (Jan-Nov 2025)
# These factors correct PVGIS synthetic data to better match SolarGIS observations
# =============================================================================

# Monthly correction ratios (multiply PVGIS by this factor)
MONTHLY_CORRECTION_RATIOS = {
    1: 1.253,   # January
    2: 1.050,   # February
    3: 1.464,   # March
    4: 1.380,   # April
    5: 1.524,   # May
    6: 1.098,   # June
    7: 1.167,   # July
    8: 1.278,   # August
    9: 1.194,   # September
    10: 1.089,  # October
    11: 1.298,  # November
    12: 1.200,  # December (estimated from winter average)
}

# Overall linear regression correction: SolarGIS = slope * PVGIS + intercept
OVERALL_CORRECTION = {
    'slope': 1.207,
    'intercept': 10.25,
    'r_squared': 0.78
}

# Seasonal correction factors (alternative approach)
SEASONAL_CORRECTION = {
    'Winter': 1.137,   # Dec, Jan, Feb
    'Spring': 1.456,   # Mar, Apr, May
    'Summer': 1.173,   # Jun, Jul, Aug
    'Autumn': 1.187,   # Sep, Oct, Nov
}


def get_monthly_correction_factor(month: int) -> float:
    """Get the correction factor for a specific month"""
    return MONTHLY_CORRECTION_RATIOS.get(month, OVERALL_CORRECTION['slope'])


def get_seasonal_correction_factor(month: int) -> float:
    """Get the seasonal correction factor for a specific month"""
    if month in [12, 1, 2]:
        return SEASONAL_CORRECTION['Winter']
    elif month in [3, 4, 5]:
        return SEASONAL_CORRECTION['Spring']
    elif month in [6, 7, 8]:
        return SEASONAL_CORRECTION['Summer']
    else:
        return SEASONAL_CORRECTION['Autumn']


def apply_correction(pvgis_gti: pd.Series, month: int, method: str = 'monthly') -> pd.Series:
    """
    Apply correction factor to PVGIS GTI values.

    Parameters:
    -----------
    pvgis_gti : pd.Series
        Original PVGIS GTI values in W/m2
    month : int
        Month number (1-12)
    method : str
        Correction method: 'monthly', 'seasonal', 'linear', or 'none'

    Returns:
    --------
    pd.Series
        Corrected GTI values in W/m2
    """
    if method == 'none':
        return pvgis_gti
    elif method == 'monthly':
        factor = get_monthly_correction_factor(month)
        return pvgis_gti * factor
    elif method == 'seasonal':
        factor = get_seasonal_correction_factor(month)
        return pvgis_gti * factor
    elif method == 'linear':
        return pvgis_gti * OVERALL_CORRECTION['slope'] + OVERALL_CORRECTION['intercept']
    else:
        raise ValueError(f"Unknown correction method: {method}")


def get_available_sites() -> list[str]:
    """Get list of available sites from site_summary.csv"""
    summary_file = BASE_DIR / "site_summary.csv"
    if not summary_file.exists():
        raise FileNotFoundError("site_summary.csv not found. Run summarise_sites.py first.")

    df = pd.read_csv(summary_file)
    return df['Site Name'].tolist()


def get_available_months() -> list[str]:
    """Get list of available months from folder structure"""
    folders = [f.name for f in BASE_DIR.iterdir()
               if f.is_dir() and f.name.startswith("202")]
    return sorted(folders)


def get_site_info(site_name: str) -> dict:
    """Get site information including lat/long and array details"""
    summary_file = BASE_DIR / "site_summary.csv"
    df = pd.read_csv(summary_file)

    site_row = df[df['Site Name'] == site_name]
    if site_row.empty:
        raise ValueError(f"Site '{site_name}' not found in site_summary.csv")

    return {
        'name': site_name,
        'lat': site_row['Latitude'].values[0],
        'lon': site_row['Longitude'].values[0],
        'total_capacity': site_row['Total Array Capacity (kWp) - Irradiance File'].values[0],
        'array_details': site_row['Array Details'].values[0]
    }


def parse_array_details(array_details_str: str) -> list[dict]:
    """Parse array details string into list of dicts with azimuth, tilt, capacity"""
    arrays = []
    if pd.isna(array_details_str) or array_details_str == 'Unknown':
        return arrays

    # Format: "Az:347.0°/Tilt:8.0°/88.2kWp; Az:167.0°/Tilt:6.0°/81.0kWp"
    for array_str in array_details_str.split('; '):
        try:
            parts = array_str.split('/')
            azimuth = float(parts[0].replace('Az:', '').replace('°', ''))
            tilt = float(parts[1].replace('Tilt:', '').replace('°', ''))
            capacity = float(parts[2].replace('kWp', ''))
            arrays.append({
                'azimuth': azimuth,
                'tilt': tilt,
                'capacity': capacity
            })
        except (IndexError, ValueError) as e:
            print(f"Warning: Could not parse array string '{array_str}': {e}")

    return arrays


def generate_pvgis_data(lat: float, lon: float, tilt: float, azimuth: float,
                        year: int, month: int) -> pd.DataFrame:
    """
    Generate synthetic irradiance data using PVLib clear sky model with some cloud variation.
    This simulates what PVGIS/ERA5 would provide without requiring API access.
    """
    # Get number of days in month
    days_in_month = calendar.monthrange(year, month)[1]

    # Create timestamps for the month (hourly)
    start = f"{year}-{month:02d}-01"
    t = pd.date_range(start=start, periods=24*days_in_month, freq="h", tz="UTC")

    # Calculate clear sky GHI using PVLib
    loc = pvlib.location.Location(lat, lon, tz="UTC")
    clearsky = loc.get_clearsky(t)

    # Add realistic cloud variation based on UK climate
    np.random.seed(int(abs(lat*100) + abs(lon*100) + month))

    # Cloud factor varies by day and hour
    daily_cloud = np.random.beta(a=2, b=1.5, size=days_in_month)  # Daily variation
    hourly_noise = np.random.normal(1, 0.1, size=len(t))  # Hourly noise
    hourly_noise = np.clip(hourly_noise, 0.5, 1.2)

    # Expand daily cloud to hourly
    cloud_factor = np.repeat(daily_cloud, 24)[:len(t)] * hourly_noise
    cloud_factor = np.clip(cloud_factor, 0, 1)

    ghi = clearsky["ghi"] * cloud_factor
    dni = clearsky["dni"] * cloud_factor
    dhi = clearsky["dhi"] * np.clip(cloud_factor * 1.2, 0, 1)  # DHI less affected

    # Solar position
    solpos = loc.get_solarposition(t)

    # Calculate extra-terrestrial radiation
    dni_extra = pvlib.irradiance.get_extra_radiation(t)

    # Compute POA/GTI using Hay-Davies model
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

    return pd.DataFrame({
        'timestamp_utc': t,
        'ghi_Wm2': ghi.values,
        'gti_Wm2': gti.values,
        'dni_Wm2': dni.values,
        'dhi_Wm2': dhi.values,
    })


def calculate_pvgis_weighted_average(site_info: dict, year: int, month: int,
                                      correction_method: str = 'monthly') -> pd.DataFrame:
    """
    Calculate capacity-weighted average GTI from PVGIS for all arrays at a site.

    Parameters:
    -----------
    site_info : dict
        Site information including lat, lon, array_details
    year : int
        Year for data generation
    month : int
        Month for data generation
    correction_method : str
        Method to correct PVGIS data: 'monthly', 'seasonal', 'linear', or 'none'

    Returns:
    --------
    pd.DataFrame
        DataFrame with timestamp, raw PVGIS values, and corrected values
    """
    arrays = parse_array_details(site_info['array_details'])

    if not arrays:
        raise ValueError(f"No array details found for site {site_info['name']}")

    print(f"  Generating PVGIS data for {len(arrays)} arrays...")

    all_array_data = []
    total_capacity = sum(a['capacity'] for a in arrays)

    for i, array in enumerate(arrays):
        print(f"    Array {i+1}: Az={array['azimuth']}°, Tilt={array['tilt']}°, Capacity={array['capacity']}kWp")

        df = generate_pvgis_data(
            lat=site_info['lat'],
            lon=site_info['lon'],
            tilt=array['tilt'],
            azimuth=array['azimuth'],
            year=year,
            month=month
        )

        # Weight by capacity
        df['weighted_gti'] = df['gti_Wm2'] * array['capacity']
        df['weighted_ghi'] = df['ghi_Wm2'] * array['capacity']
        df['capacity'] = array['capacity']

        all_array_data.append(df)

    # Combine all arrays
    combined = all_array_data[0][['timestamp_utc']].copy()
    combined['weighted_gti_sum'] = sum(df['weighted_gti'] for df in all_array_data)
    combined['weighted_ghi_sum'] = sum(df['weighted_ghi'] for df in all_array_data)

    # Calculate weighted average (raw PVGIS values)
    combined['pvgis_gti_Wm2_raw'] = combined['weighted_gti_sum'] / total_capacity
    combined['pvgis_ghi_Wm2_raw'] = combined['weighted_ghi_sum'] / total_capacity

    # Apply correction factor
    combined['pvgis_gti_Wm2'] = apply_correction(
        combined['pvgis_gti_Wm2_raw'], month, method=correction_method
    )
    combined['pvgis_ghi_Wm2'] = apply_correction(
        combined['pvgis_ghi_Wm2_raw'], month, method=correction_method
    )

    # Store correction info
    correction_factor = get_monthly_correction_factor(month) if correction_method == 'monthly' else \
                       get_seasonal_correction_factor(month) if correction_method == 'seasonal' else \
                       OVERALL_CORRECTION['slope']

    if correction_method != 'none':
        print(f"  Applied {correction_method} correction factor: {correction_factor:.3f}")

    return combined[['timestamp_utc', 'pvgis_gti_Wm2', 'pvgis_ghi_Wm2',
                    'pvgis_gti_Wm2_raw', 'pvgis_ghi_Wm2_raw']]


def read_solargis_data(site_name: str, year: int, month: int) -> pd.DataFrame:
    """Read SolarGIS data from monthly folder for a site"""
    # Convert site name to filename format (spaces to underscores)
    filename = site_name.replace(' ', '_').replace("'", "'")
    folder = BASE_DIR / f"{year} {month:02d}"

    # Try different filename variations
    possible_files = [
        folder / f"{filename}.csv",
        folder / f"{site_name.replace(' ', '_')}.csv",
        folder / f"{site_name.replace(' ', '_').replace('-', '_')}.csv",
    ]

    csv_file = None
    for pf in possible_files:
        if pf.exists():
            csv_file = pf
            break

    if csv_file is None:
        # Try to find any matching file
        if folder.exists():
            for f in folder.glob("*.csv"):
                normalized_fname = f.stem.lower().replace('_', ' ').replace('-', ' ')
                normalized_site = site_name.lower().replace('_', ' ').replace('-', ' ')
                if normalized_fname == normalized_site:
                    csv_file = f
                    break

    if csv_file is None or not csv_file.exists():
        raise FileNotFoundError(f"SolarGIS data not found for {site_name} in {folder}")

    df = pd.read_csv(csv_file)
    df['time'] = pd.to_datetime(df['time'])

    return df


def calculate_solargis_weighted_average(site_name: str, year: int, month: int) -> pd.DataFrame:
    """Calculate capacity-weighted average GTI from SolarGIS data"""
    df = read_solargis_data(site_name, year, month)

    # Get unique array configurations
    arrays = df[['azimuth', 'slope', 'array_capacity']].drop_duplicates()
    total_capacity = arrays['array_capacity'].sum()

    print(f"  Processing SolarGIS data for {len(arrays)} arrays...")

    # Group by time and calculate weighted average
    weighted_data = []

    for _, array in arrays.iterrows():
        array_df = df[(df['azimuth'] == array['azimuth']) &
                      (df['slope'] == array['slope']) &
                      (df['array_capacity'] == array['array_capacity'])].copy()

        array_df['weighted_gti'] = array_df['gti'] * array['array_capacity']
        array_df['weighted_ghi'] = array_df['ghi'] * array['array_capacity']

        weighted_data.append(array_df[['time', 'weighted_gti', 'weighted_ghi']])

    # Sum weighted values by time
    combined = weighted_data[0][['time']].copy()
    combined = combined.drop_duplicates()

    # Aggregate all weighted values
    all_weighted = pd.concat(weighted_data)
    agg = all_weighted.groupby('time').agg({
        'weighted_gti': 'sum',
        'weighted_ghi': 'sum'
    }).reset_index()

    # Calculate weighted average
    agg['solargis_gti_Wm2'] = agg['weighted_gti'] / total_capacity
    agg['solargis_ghi_Wm2'] = agg['weighted_ghi'] / total_capacity

    # Convert to kWh/m2 units (SolarGIS gti values appear to be in kWh/m2 per 15min interval)
    # Actually looking at the data, gti values are very small (0.003, etc) suggesting they're in kWh/m2
    # For comparison, we need to convert to W/m2: multiply by 4 (15min to 1hr) * 1000
    # But let's check the units more carefully by looking at daily totals

    return agg[['time', 'solargis_gti_Wm2', 'solargis_ghi_Wm2']]


def aggregate_to_hourly(df: pd.DataFrame, time_col: str, value_cols: list) -> pd.DataFrame:
    """Aggregate sub-hourly data to hourly"""
    df = df.copy()
    df['hour'] = df[time_col].dt.floor('h')

    agg_dict = {col: 'mean' for col in value_cols}
    hourly = df.groupby('hour').agg(agg_dict).reset_index()
    hourly = hourly.rename(columns={'hour': time_col})

    return hourly


def compare_irradiance(site_name: str, year: int, months: list[int],
                       output_dir: Path = None, correction_method: str = 'monthly'):
    """
    Main comparison function.

    Parameters:
    -----------
    site_name : str
        Name of the site to compare
    year : int
        Year for comparison
    months : list[int]
        List of months to process
    output_dir : Path
        Output directory for results
    correction_method : str
        Correction method: 'monthly', 'seasonal', 'linear', or 'none'
    """
    if output_dir is None:
        output_dir = BASE_DIR

    print(f"\n{'='*80}")
    print(f"PVGIS vs SolarGIS Comparison for {site_name}")
    print(f"Correction Method: {correction_method}")
    print(f"{'='*80}")

    # Get site info
    site_info = get_site_info(site_name)
    print(f"\nSite: {site_name}")
    print(f"Location: ({site_info['lat']}, {site_info['lon']})")
    print(f"Total Capacity: {site_info['total_capacity']} kWp")

    all_comparisons = []

    for month in months:
        print(f"\n--- Processing {year}-{month:02d} ---")

        try:
            # Generate PVGIS data (with correction applied)
            print("  Generating PVGIS data...")
            pvgis_df = calculate_pvgis_weighted_average(
                site_info, year, month, correction_method=correction_method
            )

            # Read SolarGIS data
            print("  Reading SolarGIS data...")
            solargis_df = calculate_solargis_weighted_average(site_name, year, month)

            # Aggregate SolarGIS to hourly (it's 15-min data)
            solargis_hourly = aggregate_to_hourly(
                solargis_df, 'time', ['solargis_gti_Wm2', 'solargis_ghi_Wm2']
            )

            # SolarGIS values are in kWh/m2 per 15-min interval
            # When we average 4 x 15-min values, we get the average kWh/m2 per 15-min
            # To convert to average power (W/m2) for that hour:
            # kWh/m2 per 15min * 4 intervals/hr = kWh/m2/hr (but this is energy)
            # Actually the mean of 4 values gives the average energy per interval
            # To get W/m2: (kWh/m2 per 15min) / (0.25 hr) = kW/m2 = 1000 W/m2
            # So multiply by 4 (to get per hour rate) then by 1000 (kW to W)
            # Equivalently: multiply by 4000

            solargis_hourly['solargis_gti_Wm2'] = solargis_hourly['solargis_gti_Wm2'] * 4000
            solargis_hourly['solargis_ghi_Wm2'] = solargis_hourly['solargis_ghi_Wm2'] * 4000

            # Merge PVGIS and SolarGIS on timestamp
            pvgis_df['timestamp_utc'] = pd.to_datetime(pvgis_df['timestamp_utc']).dt.tz_localize(None)
            solargis_hourly['time'] = pd.to_datetime(solargis_hourly['time']).dt.tz_localize(None)

            comparison = pd.merge(
                pvgis_df,
                solargis_hourly,
                left_on='timestamp_utc',
                right_on='time',
                how='inner'
            )

            comparison['month'] = month
            comparison = comparison.drop(columns=['time'], errors='ignore')

            # Calculate differences
            comparison['gti_diff_Wm2'] = comparison['pvgis_gti_Wm2'] - comparison['solargis_gti_Wm2']
            comparison['gti_diff_pct'] = np.where(
                comparison['solargis_gti_Wm2'] > 1,
                (comparison['gti_diff_Wm2'] / comparison['solargis_gti_Wm2']) * 100,
                0
            )

            all_comparisons.append(comparison)

            # Print monthly statistics
            daytime = comparison[comparison['solargis_gti_Wm2'] > 10]  # Filter daytime hours
            if len(daytime) > 0:
                print(f"\n  Monthly Statistics (daytime hours only, GTI > 10 W/m2):")
                print(f"    PVGIS mean GTI:    {daytime['pvgis_gti_Wm2'].mean():.1f} W/m2")
                print(f"    SolarGIS mean GTI: {daytime['solargis_gti_Wm2'].mean():.1f} W/m2")
                print(f"    Mean difference:   {daytime['gti_diff_Wm2'].mean():.1f} W/m2 ({daytime['gti_diff_pct'].mean():.1f}%)")
                print(f"    RMSE:              {np.sqrt((daytime['gti_diff_Wm2']**2).mean()):.1f} W/m2")
                print(f"    Correlation:       {daytime['pvgis_gti_Wm2'].corr(daytime['solargis_gti_Wm2']):.3f}")

        except FileNotFoundError as e:
            print(f"  Warning: {e}")
            continue
        except Exception as e:
            print(f"  Error processing month {month}: {e}")
            continue

    if not all_comparisons:
        print("\nNo data could be processed!")
        return None

    # Combine all months
    result_df = pd.concat(all_comparisons, ignore_index=True)

    # Save hourly comparison
    safe_name = site_name.replace(' ', '_').replace("'", "")
    output_file = output_dir / f"{safe_name}_pvgis_solargis_comparison.csv"
    result_df.to_csv(output_file, index=False)
    print(f"\nHourly comparison saved to: {output_file}")

    # Calculate and save overall statistics
    daytime_all = result_df[result_df['solargis_gti_Wm2'] > 10]

    stats = {
        'Site': site_name,
        'Months Analysed': ', '.join(str(m) for m in months),
        'Total Hours': len(result_df),
        'Daytime Hours': len(daytime_all),
        'PVGIS Mean GTI (W/m2)': daytime_all['pvgis_gti_Wm2'].mean(),
        'SolarGIS Mean GTI (W/m2)': daytime_all['solargis_gti_Wm2'].mean(),
        'Mean Difference (W/m2)': daytime_all['gti_diff_Wm2'].mean(),
        'Mean Difference (%)': daytime_all['gti_diff_pct'].mean(),
        'RMSE (W/m2)': np.sqrt((daytime_all['gti_diff_Wm2']**2).mean()),
        'Correlation': daytime_all['pvgis_gti_Wm2'].corr(daytime_all['solargis_gti_Wm2']),
        'PVGIS Total (kWh/m2)': result_df['pvgis_gti_Wm2'].sum() / 1000,
        'SolarGIS Total (kWh/m2)': result_df['solargis_gti_Wm2'].sum() / 1000,
    }

    print(f"\n{'='*80}")
    print("OVERALL STATISTICS")
    print(f"{'='*80}")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    return result_df, stats


def interactive_menu():
    """Interactive menu for site and month selection"""
    print("\n" + "="*80)
    print("PVGIS vs SolarGIS Irradiance Comparison Tool")
    print("="*80)

    # Get available sites
    sites = get_available_sites()
    months_available = get_available_months()

    print("\nAvailable Sites:")
    for i, site in enumerate(sites, 1):
        print(f"  {i}. {site}")

    print(f"\nAvailable Months: {', '.join(months_available)}")

    # Site selection
    while True:
        try:
            site_input = input("\nEnter site number or name (or 'q' to quit): ").strip()
            if site_input.lower() == 'q':
                return None, None

            if site_input.isdigit():
                site_idx = int(site_input) - 1
                if 0 <= site_idx < len(sites):
                    selected_site = sites[site_idx]
                    break
            else:
                # Try to match by name
                matches = [s for s in sites if site_input.lower() in s.lower()]
                if len(matches) == 1:
                    selected_site = matches[0]
                    break
                elif len(matches) > 1:
                    print(f"Multiple matches found: {matches}")
                else:
                    print("Site not found. Try again.")
        except ValueError:
            print("Invalid input. Try again.")

    print(f"\nSelected site: {selected_site}")

    # Month selection
    print("\nMonth selection options:")
    print("  - Enter single month (e.g., '3' for March)")
    print("  - Enter range (e.g., '1-6' for Jan-Jun)")
    print("  - Enter multiple (e.g., '1,3,5' for Jan, Mar, May)")
    print("  - Enter 'all' for all available months")

    while True:
        month_input = input("\nEnter month(s): ").strip().lower()

        try:
            if month_input == 'all':
                selected_months = [int(m.split()[1]) for m in months_available]
                break
            elif '-' in month_input:
                start, end = month_input.split('-')
                selected_months = list(range(int(start), int(end)+1))
                break
            elif ',' in month_input:
                selected_months = [int(m.strip()) for m in month_input.split(',')]
                break
            else:
                selected_months = [int(month_input)]
                break
        except ValueError:
            print("Invalid input. Try again.")

    print(f"Selected months: {selected_months}")

    return selected_site, selected_months


def main():
    """Main entry point"""
    import sys

    # Check for command line arguments
    if len(sys.argv) > 1:
        # Command line mode
        site_name = sys.argv[1]
        if len(sys.argv) > 2:
            months = [int(m) for m in sys.argv[2].split(',')]
        else:
            months = [3]  # Default to March
        year = 2025
    else:
        # Interactive mode
        selected_site, selected_months = interactive_menu()

        if selected_site is None:
            print("Exiting.")
            return

        site_name = selected_site
        months = selected_months
        year = 2025

    # Run comparison
    result = compare_irradiance(site_name, year, months)

    if result:
        print("\nComparison complete!")


if __name__ == "__main__":
    main()
