"""Quick test script for clipping analysis on Newfold Farm."""
import sys
sys.path.insert(0, r"c:\Users\PeterHall\OneDrive - AMPYR IDEA UK Ltd\Python scripts\unified_app")

from modules.clipping_analysis import (
    detect_clipping, split_inv_irr, detect_power_column,
    detect_irradiance_column, prepare_dataframe
)
from services import legacy_toolkit
from solar_toolkit.config import settings
from solar_toolkit.data_viewer import DataViewer

# Newfold Farm settings
NEWFOLD_FARM_UID = None  # Will find it
AC_RATING_KW = 7200  # User specified 7200 kW AC
DC_RATING_KW = 9630  # 9630 kW DC

# Initialize
orch = legacy_toolkit.get_orchestrator()
viewer = DataViewer(db_path=settings.DB_PATH)

# Get available plants
available_plants = viewer.get_unique_plant_uids()
print(f"Available plants: {available_plants}")

# Find Newfold Farm
plant_list = orch.get_plants()
plant_map = {p['plant_uid']: p for p in plant_list}

for uid in available_plants:
    info = plant_map.get(uid, {})
    alias = info.get('alias', uid)
    if 'newfold' in alias.lower() or 'newfold' in uid.lower():
        NEWFOLD_FARM_UID = uid
        print(f"Found Newfold Farm: {alias} ({uid})")
        print(f"  DC Size: {info.get('dc_size_kw', 'N/A')} kW")
        break

if not NEWFOLD_FARM_UID:
    print("ERROR: Newfold Farm not found in available plants")
    print("Available plants and aliases:")
    for uid in available_plants:
        info = plant_map.get(uid, {})
        alias = info.get('alias', uid)
        print(f"  - {alias} ({uid})")
    sys.exit(1)

# Get date range
date_range = viewer.get_date_range(plant_uid=NEWFOLD_FARM_UID)
print(f"\nData available: {date_range[0][:10]} to {date_range[1][:10]}")

# Load data - focus on summer months (June-August) for clipping
start_str = "2025-06-01T00:00:00"
end_str = "2025-08-31T23:59:59"
print(f"\nAnalyzing SUMMER period: {start_str[:10]} to {end_str[:10]}")

df_raw, total_count = viewer.get_readings_data(
    plant_uid=NEWFOLD_FARM_UID,
    start_date=start_str,
    end_date=end_str,
    limit=10000000
)

print(f"Loaded {len(df_raw):,} readings (total: {total_count:,})")

if df_raw.empty:
    print("ERROR: No data found for summer period")
    # Try full range instead
    start_str = date_range[0][:10] + "T00:00:00"
    end_str = date_range[1][:10] + "T23:59:59"
    print(f"\nTrying full date range: {start_str[:10]} to {end_str[:10]}")

    df_raw, total_count = viewer.get_readings_data(
        plant_uid=NEWFOLD_FARM_UID,
        start_date=start_str,
        end_date=end_str,
        limit=10000000
    )
    print(f"Loaded {len(df_raw):,} readings")

# Split data
inv_df, irr_df = split_inv_irr(df_raw)
print(f"\nInverter records: {len(inv_df):,}")
print(f"Irradiance records: {len(irr_df):,}")

# Detect columns
power_col = detect_power_column(inv_df)
irr_col = detect_irradiance_column(irr_df) if not irr_df.empty else None
print(f"Power column: {power_col}")
print(f"Irradiance column: {irr_col}")

# Prepare data
if power_col:
    inv_df = prepare_dataframe(inv_df, power_col)
if irr_col:
    irr_df = prepare_dataframe(irr_df, irr_col)

print(f"\nAfter preparation:")
print(f"  Inverter records: {len(inv_df):,}")
print(f"  Irradiance records: {len(irr_df):,}")

# Show irradiance distribution
if not irr_df.empty and irr_col:
    print(f"\nIrradiance stats ({irr_col}):")
    print(irr_df[irr_col].describe())
    high_irr = (irr_df[irr_col] >= 600).sum()
    print(f"Records with irradiance >= 600 W/m²: {high_irr:,}")

# Run clipping detection
print("\n" + "="*60)
print("RUNNING CLIPPING DETECTION")
print("="*60)

results = detect_clipping(
    inv_df=inv_df,
    irr_df=irr_df if irr_col else None,
    power_col=power_col,
    irr_col=irr_col,
    ac_rating_kw=AC_RATING_KW,
    plateau_pct=0.95,
    flatness_pct=0.03,
    min_irradiance=200
)

# Display results
print("\nRESULTS:")
print(f"  Total Energy: {results['total_energy_kwh']:,.0f} kWh")
print(f"  Clipping Loss: {results['total_loss_kwh']:,.0f} kWh ({results['clipping_pct']:.2f}%)")
print(f"  Clipping Hours: {results['clipping_hours']:.1f} hrs")
print(f"  Days with Clipping: {len(results['clipping_days'])}")

print("\nDEBUG INFO:")
debug = results.get('debug_info', {})
for key, value in debug.items():
    if isinstance(value, float):
        print(f"  {key}: {value:,.4f}")
    else:
        print(f"  {key}: {value}")

# Show days with clipping
if not results['clipping_days'].empty:
    print("\nTOP 10 DAYS WITH CLIPPING:")
    print(results['clipping_days'].head(10).to_string())

    # Check if summer months have clipping
    clipping_days = results['clipping_days'].copy()
    clipping_days['month'] = clipping_days['date'].apply(lambda x: x.month if hasattr(x, 'month') else int(str(x)[5:7]))

    summer_clipping = clipping_days[clipping_days['month'].isin([6, 7, 8])]
    winter_clipping = clipping_days[clipping_days['month'].isin([11, 12, 1, 2])]

    print(f"\nSummer clipping days (Jun-Aug): {len(summer_clipping)}")
    print(f"Winter clipping days (Nov-Feb): {len(winter_clipping)}")

    if len(winter_clipping) > len(summer_clipping):
        print("\n⚠️  WARNING: More clipping detected in winter than summer!")
        print("    This suggests false positives - review detection thresholds")
else:
    print("\nNo clipping days detected!")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
