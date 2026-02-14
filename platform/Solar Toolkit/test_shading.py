"""Test script to verify the shading analysis flow end-to-end."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solar_toolkit.data_viewer import DataViewer
from solar_toolkit.shading_analysis import analyze_from_dataframes, ShadingSettings
from solar_toolkit.config import settings
import pandas as pd

print("="*70)
print("SHADING ANALYSIS END-TO-END TEST")
print("="*70)

# Initialize data viewer
db_path = settings.DB_PATH
print(f"\n1. Database: {db_path}")
viewer = DataViewer(db_path=db_path)

# Get plant with data
plant_uid = "AMP:00001"
print(f"\n2. Testing plant: {plant_uid}")

# Define date ranges
# Summer baseline: June-August (POA data exists from June 2025)
baseline_start = "2025-06-01"
baseline_end = "2025-08-31"

# Winter comparison: October (last month with POA data)
compare_start = "2025-10-01"
compare_end = "2025-10-31"

print(f"\n3. Date ranges:")
print(f"   Baseline (summer): {baseline_start} to {baseline_end}")
print(f"   Comparison (winter): {compare_start} to {compare_end}")

# Load baseline data
print(f"\n4. Loading baseline data...")
baseline_df, baseline_count = viewer.get_readings_data(
    plant_uid=plant_uid,
    start_date=baseline_start,
    end_date=baseline_end,
    limit=100000
)
print(f"   Loaded {len(baseline_df)} rows (total available: {baseline_count})")

# Load comparison data
print(f"\n5. Loading comparison data...")
compare_df, compare_count = viewer.get_readings_data(
    plant_uid=plant_uid,
    start_date=compare_start,
    end_date=compare_end,
    limit=100000
)
print(f"   Loaded {len(compare_df)} rows (total available: {compare_count})")

# Split into inverter and irradiance
def split_inv_irr(df):
    inv = df[df['emig_id'].str.startswith("INVERT:")].copy()
    irr = df[df['emig_id'].str.contains("POA:|WETH|MET")].copy()
    return inv, irr

baseline_inv, baseline_irr = split_inv_irr(baseline_df)
compare_inv, compare_irr = split_inv_irr(compare_df)

print(f"\n6. Data split:")
print(f"   Baseline inverter: {len(baseline_inv)} rows")
print(f"   Baseline irradiance: {len(baseline_irr)} rows")
print(f"   Compare inverter: {len(compare_inv)} rows")
print(f"   Compare irradiance: {len(compare_irr)} rows")

# Check columns
print(f"\n7. Sample columns:")
if not baseline_inv.empty:
    print(f"   Inverter columns: {list(baseline_inv.columns)[:10]}...")
if not baseline_irr.empty:
    print(f"   Irradiance columns: {list(baseline_irr.columns)[:10]}...")

# Find power column
power_col = None
for candidate in ['apparentPower_value', 'activePower_value', 'exportEnergy_value']:
    if candidate in baseline_inv.columns:
        power_col = candidate
        break
print(f"\n8. Power column: {power_col}")

# Check irradiance values
if not baseline_irr.empty and 'poaIrradiance_value' in baseline_irr.columns:
    irr_vals = baseline_irr['poaIrradiance_value'].dropna()
    print(f"\n9. Baseline irradiance check:")
    print(f"   Count: {len(irr_vals)}")
    print(f"   Min: {irr_vals.min():.4f}, Max: {irr_vals.max():.4f}, Mean: {irr_vals.mean():.4f}")
    if irr_vals.max() < 2.0:
        print(f"   *** Looks like kW/m² - will be auto-converted to W/m²")

# Run the analysis
print(f"\n" + "="*70)
print("10. RUNNING SHADING ANALYSIS")
print("="*70 + "\n")

try:
    merged, summary = analyze_from_dataframes(
        summer_inv_df=baseline_inv,
        winter_inv_df=compare_inv,
        power_col=power_col,
        summer_irr_df=baseline_irr if not baseline_irr.empty else None,
        winter_irr_df=compare_irr if not compare_irr.empty else None,
        irr_col='poaIrradiance_value',
        emig_id_col='emig_id',
        timestamp_col='ts'
    )
    
    print(f"\n" + "="*70)
    print("11. RESULTS")
    print("="*70)
    
    if merged.empty:
        print("   *** Analysis returned empty results ***")
    else:
        print(f"   Merged data: {len(merged)} rows")
        print(f"   Merged columns: {list(merged.columns)}")
        print(f"\n   Sample merged data:")
        print(merged.head(10).to_string())
    
    if not summary.empty:
        print(f"\n   Summary ({len(summary)} inverters):")
        print(summary.to_string())
    else:
        print("   *** Summary is empty ***")
        
except Exception as e:
    import traceback
    print(f"   *** ERROR: {e}")
    traceback.print_exc()

print(f"\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
