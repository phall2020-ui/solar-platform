"""
Script to summarise site array details from monthly irradiance data
and ADE spreadsheets, creating a consolidated CSV output.
"""
import pandas as pd
import os
from pathlib import Path
import re

# Base directory
base_dir = Path(r"c:\Users\PeterHall\OneDrive - AMPYR IDEA UK Ltd\Python scripts\Irradiation Data")

# Read ADE spreadsheets
print("Reading ADE spreadsheets...")
ade_crm = pd.read_excel(base_dir / "ADE CRM Data Request.xlsx")
ade_array = pd.read_excel(base_dir / "ADE Data Export Request CRM Array Data.xlsx")

# Collect unique sites from all monthly folders
print("Scanning monthly irradiance folders for sites...")

sites_data = {}
monthly_folders = [f for f in base_dir.iterdir() if f.is_dir() and f.name.startswith("202")]

# Filter out test/comparison files
exclude_patterns = ['pvgis', 'compare', 'test', 'summary']

for folder in sorted(monthly_folders):
    csv_files = list(folder.glob("*.csv"))
    for csv_file in csv_files:
        site_name = csv_file.stem  # filename without extension

        # Skip test/comparison files
        if any(pattern in site_name.lower() for pattern in exclude_patterns):
            continue

        if site_name not in sites_data:
            # Read file to get all unique array configurations
            try:
                df = pd.read_csv(csv_file)

                # Get unique array configurations (azimuth, slope, capacity combinations)
                if all(col in df.columns for col in ['azimuth', 'slope', 'array_capacity']):
                    arrays = df[['azimuth', 'slope', 'array_capacity']].drop_duplicates()
                    num_arrays = len(arrays)
                    total_capacity = arrays['array_capacity'].sum()

                    # Format array details as string for summary
                    array_details = []
                    for _, row in arrays.iterrows():
                        array_details.append(f"Az:{row['azimuth']}°/Tilt:{row['slope']}°/{row['array_capacity']}kWp")

                    sites_data[site_name] = {
                        'site_name': df['name'].iloc[0] if 'name' in df.columns else site_name,
                        'num_arrays': num_arrays,
                        'total_array_capacity_kWp': total_capacity,
                        'array_details': '; '.join(array_details),
                        'azimuths': ', '.join(map(str, sorted(arrays['azimuth'].unique()))),
                        'slopes': ', '.join(map(str, sorted(arrays['slope'].unique()))),
                        'source_file': site_name
                    }
                else:
                    sites_data[site_name] = {
                        'site_name': df['name'].iloc[0] if 'name' in df.columns else site_name,
                        'num_arrays': 1,
                        'total_array_capacity_kWp': None,
                        'array_details': 'Unknown',
                        'azimuths': None,
                        'slopes': None,
                        'source_file': site_name
                    }
            except Exception as e:
                print(f"Error reading {csv_file}: {e}")

print(f"Found {len(sites_data)} unique sites from irradiance files")

# Create a dataframe from sites data
sites_df = pd.DataFrame.from_dict(sites_data, orient='index')
sites_df = sites_df.reset_index(drop=True)

# Create a normalized name function for matching
def normalize_name(name):
    """Normalize site name for matching between datasets"""
    if pd.isna(name):
        return ""
    name = str(name).lower()
    # Replace underscores with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    # Remove extra spaces
    name = ' '.join(name.split())
    return name

# Add normalized names for matching
sites_df['normalized_name'] = sites_df['site_name'].apply(normalize_name)
ade_crm['normalized_name'] = ade_crm['asset_name'].apply(normalize_name)

# Merge to get lat/long and other details from ADE CRM
print("Matching sites with ADE CRM data for lat/long...")

# Perform the merge on normalized names
merged_df = sites_df.merge(
    ade_crm[['asset_name', 'normalized_name', 'site_latitude', 'site_longitude',
             'nameplate_dc_capacity_kwp', 'customer_name', 'fund_name',
             'date_commissioned', 'number_of_inverters']],
    on='normalized_name',
    how='left'
)

# Check for unmatched sites
unmatched = merged_df[merged_df['site_latitude'].isna()]['site_name'].tolist()
if unmatched:
    print(f"\nWarning: {len(unmatched)} sites could not be matched to ADE CRM data:")
    for site in unmatched:
        print(f"  - {site}")

# Select and rename columns for final output
output_df = merged_df[[
    'site_name',
    'customer_name',
    'fund_name',
    'site_latitude',
    'site_longitude',
    'num_arrays',
    'total_array_capacity_kWp',
    'nameplate_dc_capacity_kwp',
    'azimuths',
    'slopes',
    'array_details',
    'number_of_inverters',
    'date_commissioned'
]].copy()

output_df.columns = [
    'Site Name',
    'Customer Name',
    'Fund Name',
    'Latitude',
    'Longitude',
    'Number of Arrays',
    'Total Array Capacity (kWp) - Irradiance File',
    'Nameplate DC Capacity (kWp) - ADE',
    'Azimuths (degrees)',
    'Slopes (degrees)',
    'Array Details',
    'Number of Inverters',
    'Date Commissioned'
]

# Sort by site name
output_df = output_df.sort_values('Site Name').reset_index(drop=True)

# Save to CSV
output_file = base_dir / "site_summary.csv"
output_df.to_csv(output_file, index=False)
print(f"\nOutput saved to: {output_file}")

# Display summary
print(f"\n{'='*80}")
print("SITE SUMMARY")
print(f"{'='*80}")
print(f"Total sites: {len(output_df)}")
print(f"Sites with lat/long data: {output_df['Latitude'].notna().sum()}")
print(f"Sites missing lat/long: {output_df['Latitude'].isna().sum()}")

print(f"\n{'='*80}")
print("Output Preview:")
print(f"{'='*80}")
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
print(output_df.to_string())
