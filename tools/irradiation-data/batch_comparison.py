"""
Batch comparison of PVGIS vs SolarGIS for randomly selected sites across months.
Selects 5 random sites per month (Jan-Nov 2025) and runs comparison.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import random
from datetime import datetime

# Import comparison functions from the main script
from pvgis_solargis_comparison import (
    get_site_info, parse_array_details, generate_pvgis_data,
    calculate_pvgis_weighted_average, calculate_solargis_weighted_average,
    aggregate_to_hourly, BASE_DIR
)

YEAR = 2025
MONTHS = list(range(1, 12))  # Jan to Nov
SITES_PER_MONTH = 5
RANDOM_SEED = 99  # For reproducibility with a fresh random draw


def get_available_sites_for_month(month: int) -> list[str]:
    """Get list of sites with data available for a specific month"""
    summary = pd.read_csv(BASE_DIR / 'site_summary.csv')
    valid_sites = summary[summary['Latitude'].notna()]['Site Name'].tolist()

    folder = BASE_DIR / f'{YEAR} {month:02d}'
    if not folder.exists():
        return []

    # Get files in folder
    files = [f.stem for f in folder.glob('*.csv')
             if not any(x in f.stem.lower() for x in ['pvgis', 'compare', 'test', 'summary'])]

    # Match to valid sites (handle underscore/space differences)
    available = []
    for site in valid_sites:
        site_normalized = site.replace(' ', '_').replace("'", "'")
        for f in files:
            f_normalized = f.replace(' ', '_')
            if site_normalized.lower() == f_normalized.lower():
                available.append(site)
                break

    return available


def run_single_comparison(site_name: str, year: int, month: int) -> dict:
    """Run comparison for a single site/month and return statistics"""
    try:
        site_info = get_site_info(site_name)

        # Generate PVGIS data
        pvgis_df = calculate_pvgis_weighted_average(site_info, year, month)

        # Read SolarGIS data
        solargis_df = calculate_solargis_weighted_average(site_name, year, month)

        # Aggregate SolarGIS to hourly
        solargis_hourly = aggregate_to_hourly(
            solargis_df, 'time', ['solargis_gti_Wm2', 'solargis_ghi_Wm2']
        )

        # Convert units (kWh/m2 per 15min to W/m2)
        solargis_hourly['solargis_gti_Wm2'] = solargis_hourly['solargis_gti_Wm2'] * 4000
        solargis_hourly['solargis_ghi_Wm2'] = solargis_hourly['solargis_ghi_Wm2'] * 4000

        # Merge on timestamp
        pvgis_df['timestamp_utc'] = pd.to_datetime(pvgis_df['timestamp_utc']).dt.tz_localize(None)
        solargis_hourly['time'] = pd.to_datetime(solargis_hourly['time']).dt.tz_localize(None)

        comparison = pd.merge(
            pvgis_df,
            solargis_hourly,
            left_on='timestamp_utc',
            right_on='time',
            how='inner'
        )

        # Calculate differences
        comparison['gti_diff_Wm2'] = comparison['pvgis_gti_Wm2'] - comparison['solargis_gti_Wm2']
        comparison['gti_diff_pct'] = np.where(
            comparison['solargis_gti_Wm2'] > 1,
            (comparison['gti_diff_Wm2'] / comparison['solargis_gti_Wm2']) * 100,
            0
        )

        # Filter to daytime hours
        daytime = comparison[comparison['solargis_gti_Wm2'] > 10]

        if len(daytime) == 0:
            return None

        return {
            'Site': site_name,
            'Month': month,
            'Year': year,
            'Latitude': site_info['lat'],
            'Longitude': site_info['lon'],
            'Total_Capacity_kWp': site_info['total_capacity'],
            'Num_Arrays': len(parse_array_details(site_info['array_details'])),
            'Total_Hours': len(comparison),
            'Daytime_Hours': len(daytime),
            'PVGIS_Mean_GTI_Wm2': daytime['pvgis_gti_Wm2'].mean(),
            'SolarGIS_Mean_GTI_Wm2': daytime['solargis_gti_Wm2'].mean(),
            'Mean_Diff_Wm2': daytime['gti_diff_Wm2'].mean(),
            'Mean_Diff_Pct': daytime['gti_diff_pct'].mean(),
            'RMSE_Wm2': np.sqrt((daytime['gti_diff_Wm2']**2).mean()),
            'Correlation': daytime['pvgis_gti_Wm2'].corr(daytime['solargis_gti_Wm2']),
            'PVGIS_Total_kWhm2': comparison['pvgis_gti_Wm2'].sum() / 1000,
            'SolarGIS_Total_kWhm2': comparison['solargis_gti_Wm2'].sum() / 1000,
        }

    except Exception as e:
        print(f"    Error: {e}")
        return None


def main():
    print("="*80)
    print("BATCH PVGIS vs SolarGIS COMPARISON")
    print(f"Year: {YEAR}, Months: Jan-Nov, Sites per month: {SITES_PER_MONTH}")
    print("="*80)

    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    all_results = []
    sites_used = set()  # Track unique sites used

    for month in MONTHS:
        print(f"\n--- Month {month:02d} ---")

        available_sites = get_available_sites_for_month(month)
        print(f"  Available sites: {len(available_sites)}")

        if len(available_sites) < SITES_PER_MONTH:
            print(f"  Warning: Only {len(available_sites)} sites available, using all")
            selected_sites = available_sites
        else:
            selected_sites = random.sample(available_sites, SITES_PER_MONTH)

        print(f"  Selected sites: {selected_sites}")

        for site in selected_sites:
            print(f"  Processing {site}...")
            result = run_single_comparison(site, YEAR, month)

            if result:
                all_results.append(result)
                sites_used.add(site)
                print(f"    PVGIS: {result['PVGIS_Mean_GTI_Wm2']:.1f} W/m2, "
                      f"SolarGIS: {result['SolarGIS_Mean_GTI_Wm2']:.1f} W/m2, "
                      f"Diff: {result['Mean_Diff_Pct']:.1f}%")

    # Create results dataframe
    results_df = pd.DataFrame(all_results)

    # Save detailed results
    output_file = BASE_DIR / 'batch_comparison_results.csv'
    results_df.to_csv(output_file, index=False)
    print(f"\n\nDetailed results saved to: {output_file}")

    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Total comparisons: {len(results_df)}")
    print(f"Unique sites: {len(sites_used)}")
    print(f"Months covered: {results_df['Month'].nunique()}")

    print("\n--- Overall Statistics ---")
    print(f"Mean PVGIS GTI:     {results_df['PVGIS_Mean_GTI_Wm2'].mean():.1f} W/m2")
    print(f"Mean SolarGIS GTI:  {results_df['SolarGIS_Mean_GTI_Wm2'].mean():.1f} W/m2")
    print(f"Mean Difference:    {results_df['Mean_Diff_Wm2'].mean():.1f} W/m2 ({results_df['Mean_Diff_Pct'].mean():.1f}%)")
    print(f"Mean RMSE:          {results_df['RMSE_Wm2'].mean():.1f} W/m2")
    print(f"Mean Correlation:   {results_df['Correlation'].mean():.3f}")

    print("\n--- By Month ---")
    monthly_summary = results_df.groupby('Month').agg({
        'PVGIS_Mean_GTI_Wm2': 'mean',
        'SolarGIS_Mean_GTI_Wm2': 'mean',
        'Mean_Diff_Pct': 'mean',
        'Correlation': 'mean'
    }).round(2)
    print(monthly_summary.to_string())

    # Save monthly summary
    monthly_summary.to_csv(BASE_DIR / 'batch_comparison_monthly_summary.csv')

    print("\n--- Sites Used ---")
    for site in sorted(sites_used):
        print(f"  - {site}")


if __name__ == "__main__":
    main()
