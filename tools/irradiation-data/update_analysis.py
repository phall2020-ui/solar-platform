"""
Script to update all analysis files with the latest data.
Replicates the analysis done in previous months.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

# Base directory
base_dir = Path(__file__).parent.resolve()

print("=" * 80)
print("UPDATING IRRADIANCE ANALYSIS FILES")
print("=" * 80)

# Define exclude patterns
exclude_patterns = ['pvgis', 'compare', 'test', 'summary', 'combined']

# =============================================================================
# STEP 1: Load all site data from monthly folders
# =============================================================================
print("\n[1/4] Loading all site data from monthly folders...")

all_data = []
monthly_folders = [f for f in base_dir.iterdir() 
                   if f.is_dir() and f.name.startswith("202")]

for folder in sorted(monthly_folders):
    csv_files = list(folder.glob("*.csv"))
    for csv_file in csv_files:
        site_name = csv_file.stem
        if any(pattern in site_name.lower() for pattern in exclude_patterns):
            continue
        try:
            df = pd.read_csv(csv_file)
            # Skip rows where 'time' column contains 'time' (duplicate headers)
            if 'time' in df.columns:
                df = df[df['time'] != 'time']
            all_data.append(df)
        except Exception as e:
            print(f"  Warning: Error reading {csv_file}: {e}")

print(f"  Loaded data from {len(monthly_folders)} monthly folders")

# Combine all data
combined_df = pd.concat(all_data, ignore_index=True)
combined_df['time'] = pd.to_datetime(combined_df['time'], format='mixed', utc=True)
combined_df = combined_df.sort_values('time').reset_index(drop=True)
print(f"  Total records: {len(combined_df):,}")
print(f"  Date range: {combined_df['time'].min()} to {combined_df['time'].max()}")

# =============================================================================
# STEP 2: Generate Monthly Summary for All Sites
# =============================================================================
print("\n[2/4] Generating monthly summary for all sites...")

df = combined_df.copy()
df['month'] = df['time'].dt.to_period('M')

# First, sum readings within each month for each array
monthly_per_array = df.groupby(['name', 'azimuth', 'slope', 'array_capacity', 'month']).agg({
    'gti': 'sum',
    'gti_low': 'sum',
    'gti_high': 'sum',
    'ghi': 'sum'
}).reset_index()

# Calculate capacity-weighted irradiance for each site and month
monthly_per_array['gti_weighted'] = monthly_per_array['gti'] * monthly_per_array['array_capacity']
monthly_per_array['gti_low_weighted'] = monthly_per_array['gti_low'] * monthly_per_array['array_capacity']
monthly_per_array['gti_high_weighted'] = monthly_per_array['gti_high'] * monthly_per_array['array_capacity']
monthly_per_array['ghi_weighted'] = monthly_per_array['ghi'] * monthly_per_array['array_capacity']

# Group by site and month, combining arrays
monthly_summary = monthly_per_array.groupby(['name', 'month']).agg({
    'array_capacity': 'sum',
    'gti_weighted': 'sum',
    'gti_low_weighted': 'sum',
    'gti_high_weighted': 'sum',
    'ghi_weighted': 'sum'
}).reset_index()

# Calculate weighted average irradiance
monthly_summary['gti'] = monthly_summary['gti_weighted'] / monthly_summary['array_capacity']
monthly_summary['gti_low'] = monthly_summary['gti_low_weighted'] / monthly_summary['array_capacity']
monthly_summary['gti_high'] = monthly_summary['gti_high_weighted'] / monthly_summary['array_capacity']
monthly_summary['ghi'] = monthly_summary['ghi_weighted'] / monthly_summary['array_capacity']

# Convert period back to timestamp for consistency
monthly_summary['time'] = monthly_summary['month'].dt.to_timestamp()
monthly_summary = monthly_summary[['name', 'time', 'array_capacity', 'gti', 'gti_low', 'gti_high', 'ghi']]
monthly_summary.rename(columns={'array_capacity': 'total_capacity_kwp'}, inplace=True)

# Save monthly summary
monthly_output = base_dir / "summary_monthly_all_sites.csv"
monthly_summary.to_csv(monthly_output, index=False)
print(f"  Saved: {monthly_output}")
print(f"  Total records: {len(monthly_summary)}")

# =============================================================================
# STEP 3: Generate Annual Summary for All Sites
# =============================================================================
print("\n[3/4] Generating annual summary for all sites...")

# Annual summary - sum up monthly GTI values for each site
# Use MAX capacity to account for sites where arrays were added during the year
annual_summary = monthly_summary.groupby('name').agg({
    'total_capacity_kwp': 'max',  # Use max to get full capacity when all arrays present
    'gti': 'sum',
    'gti_low': 'sum',
    'gti_high': 'sum',
    'ghi': 'sum'
}).reset_index()

# Save annual summary
annual_output = base_dir / "summary_annual_all_sites.csv"
annual_summary.to_csv(annual_output, index=False)
print(f"  Saved: {annual_output}")
print(f"  Total sites: {len(annual_summary)}")

# =============================================================================
# STEP 4: Generate Monthly Summary for Full-Year Sites (sites with 12+ months data)
# =============================================================================
print("\n[4/4] Generating summaries for full-year sites...")

# Define the full-year sites (sites that have data for all months in 2025)
full_year_sites = [
    'Blachford',
    'Cromwell_Tools',
    'Hibernian_Stadium',
    'Hibernian_Training_Ground',
    'Merry_Hill',
    'Metro_Centre',
    'Sheldons_Bakery'
]

# Define location mapping for full-year sites
location_map = {
    'Blachford': 'Midlands',
    'Cromwell_Tools': 'Midlands',
    'Hibernian_Stadium': 'Scotland',
    'Hibernian_Training_Ground': 'Scotland',
    'Merry_Hill': 'Midlands',
    'Metro_Centre': 'North East',
    'Sheldons_Bakery': 'North West'
}

# Filter for full-year sites
full_year_monthly = monthly_summary[monthly_summary['name'].str.replace(' ', '_').isin(full_year_sites)].copy()

# Also try matching without underscore conversion
if len(full_year_monthly) == 0:
    # Try matching the names directly from the data
    available_names = monthly_summary['name'].unique()
    full_year_site_matches = []
    for site in full_year_sites:
        # Try with underscores replaced by spaces
        site_space = site.replace('_', ' ')
        if site in available_names:
            full_year_site_matches.append(site)
        elif site_space in available_names:
            full_year_site_matches.append(site_space)
    
    full_year_monthly = monthly_summary[monthly_summary['name'].isin(full_year_site_matches)].copy()

# Add location column
full_year_monthly['location'] = full_year_monthly['name'].apply(
    lambda x: location_map.get(x.replace(' ', '_'), 'Unknown')
)

# Format and save monthly full-year sites
full_year_monthly_output = full_year_monthly[['name', 'location', 'time', 'total_capacity_kwp', 'gti', 'gti_low', 'gti_high', 'ghi']].copy()
full_year_monthly_output['time'] = full_year_monthly_output['time'].dt.strftime('%d/%m/%Y')
full_year_monthly_output.to_csv(base_dir / "summary_monthly_full_year_sites.csv", index=False)
print(f"  Saved: summary_monthly_full_year_sites.csv")
print(f"  Total records: {len(full_year_monthly_output)}")

# Generate annual summary for full-year sites
full_year_annual = annual_summary[annual_summary['name'].str.replace(' ', '_').isin(full_year_sites)].copy()
if len(full_year_annual) == 0:
    full_year_annual = annual_summary[annual_summary['name'].isin(full_year_site_matches)].copy()

# Format names with underscores for consistency with existing file
full_year_annual['name'] = full_year_annual['name'].str.replace(' ', '_')
full_year_annual.to_csv(base_dir / "summary_annual_full_year_sites.csv", index=False)
print(f"  Saved: summary_annual_full_year_sites.csv")
print(f"  Total sites: {len(full_year_annual)}")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 80)
print("ANALYSIS UPDATE COMPLETE")
print("=" * 80)
print("\nFiles updated:")
print(f"  1. summary_monthly_all_sites.csv ({len(monthly_summary)} records)")
print(f"  2. summary_annual_all_sites.csv ({len(annual_summary)} sites)")
print(f"  3. summary_monthly_full_year_sites.csv ({len(full_year_monthly_output)} records)")
print(f"  4. summary_annual_full_year_sites.csv ({len(full_year_annual)} sites)")

# Show January 2026 counts
jan_2026 = monthly_summary[monthly_summary['time'].dt.year == 2026]
print(f"\nJanuary 2026 data: {len(jan_2026)} site records")
