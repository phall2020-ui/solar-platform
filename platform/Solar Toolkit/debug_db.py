"""Debug script to analyze database data and test shading analysis flow."""

import sqlite3
import pandas as pd
import json
import sys
import os

# Connect to database - use the actual path from settings
db_path = os.path.join(os.path.expanduser("~"), ".solar_toolkit", "plant_registry.sqlite")
print(f"Database path: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)

print("="*60)
print("DATABASE ANALYSIS")
print("="*60)

# 1. List tables
tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
print(f"\n1. Tables: {tables['name'].tolist()}")

# 2. Check readings table structure
print("\n2. Readings table structure:")
cursor = conn.execute('PRAGMA table_info(readings)')
for col in cursor.fetchall():
    print(f"   {col}")

# 3. Get device types
print("\n3. Device types in database:")
devices = pd.read_sql_query("SELECT DISTINCT emig_id FROM readings LIMIT 50", conn)
print(f"   Sample device IDs: {devices['emig_id'].tolist()[:10]}")

# 3b. Check which plants have data
print("\n3b. Plants with data:")
plants_with_data = pd.read_sql_query("""
    SELECT plant_uid, COUNT(*) as count, MIN(ts) as min_ts, MAX(ts) as max_ts
    FROM readings 
    GROUP BY plant_uid
""", conn)
print(plants_with_data.to_string())

# Pick a plant with data
if not plants_with_data.empty:
    plant_uid = plants_with_data.iloc[0]['plant_uid']
else:
    plant_uid = "AMP:00032"  # Fallback
print(f"\n4. Checking plant: {plant_uid}")

# Get date range
date_range = pd.read_sql_query(f"""
    SELECT MIN(ts) as min_ts, MAX(ts) as max_ts, COUNT(*) as count
    FROM readings 
    WHERE plant_uid = '{plant_uid}'
""", conn)
print(f"   Date range: {date_range.iloc[0]['min_ts']} to {date_range.iloc[0]['max_ts']}")
print(f"   Total readings: {date_range.iloc[0]['count']}")

# 5. Get device breakdown for the plant
print("\n5. Device breakdown:")
device_counts = pd.read_sql_query(f"""
    SELECT emig_id, COUNT(*) as count 
    FROM readings 
    WHERE plant_uid = '{plant_uid}'
    GROUP BY emig_id
""", conn)
print(device_counts.to_string())

# 6. Check a sample payload for an inverter
print("\n6. Sample INVERTER payload:")
inv_sample = pd.read_sql_query(f"""
    SELECT ts, emig_id, payload 
    FROM readings 
    WHERE plant_uid = '{plant_uid}' AND emig_id LIKE 'INVERT:%'
    ORDER BY ts DESC
    LIMIT 1
""", conn)
if not inv_sample.empty:
    payload = json.loads(inv_sample.iloc[0]['payload'])
    print(f"   Timestamp: {inv_sample.iloc[0]['ts']}")
    print(f"   Device: {inv_sample.iloc[0]['emig_id']}")
    print(f"   Payload keys: {list(payload.keys())}")
    # Look for irradiance in payload
    for key in payload.keys():
        if 'irrad' in key.lower() or 'poa' in key.lower():
            print(f"   *** {key}: {payload[key]}")

# 7. Check a sample payload for POA sensor
print("\n7. Sample POA sensor payload:")
poa_sample = pd.read_sql_query(f"""
    SELECT ts, emig_id, payload 
    FROM readings 
    WHERE plant_uid = '{plant_uid}' AND emig_id LIKE 'POA:%'
    ORDER BY ts DESC
    LIMIT 1
""", conn)
if not poa_sample.empty:
    payload = json.loads(poa_sample.iloc[0]['payload'])
    print(f"   Timestamp: {poa_sample.iloc[0]['ts']}")
    print(f"   Device: {poa_sample.iloc[0]['emig_id']}")
    print(f"   Payload keys: {list(payload.keys())}")
    for key in payload.keys():
        if 'irrad' in key.lower() or 'poa' in key.lower():
            print(f"   *** {key}: {payload[key]}")
else:
    print("   No POA sensor data found")

# 8. Get irradiance values for August (summer baseline)
print("\n8. Irradiance data check for August 2025:")
aug_irr = pd.read_sql_query(f"""
    SELECT ts, payload 
    FROM readings 
    WHERE plant_uid = '{plant_uid}' 
    AND emig_id LIKE 'POA:%'
    AND ts >= '2025-08-01' AND ts < '2025-09-01'
    ORDER BY ts
""", conn)
print(f"   POA readings in August: {len(aug_irr)}")
if not aug_irr.empty:
    # Parse payloads and extract irradiance
    irr_values = []
    irr_units = []
    ts_vals = []
    for idx, row in aug_irr.iterrows():
        try:
            payload = json.loads(row['payload'])
            if 'poaIrradiance' in payload:
                irr = payload['poaIrradiance']
                if isinstance(irr, dict):
                    irr_values.append(irr.get('value', 0))
                    irr_units.append(irr.get('unit', 'unknown'))
                else:
                    irr_values.append(irr)
                    irr_units.append('unknown')
                ts_vals.append(row['ts'])
        except:
            pass
    print(f"   Total irradiance readings: {len(irr_values)}")
    print(f"   Units observed: {set(irr_units)}")
    print(f"   Non-zero values: {sum(1 for v in irr_values if v and v > 0)}")
    if irr_values:
        print(f"   Min: {min(irr_values)}, Max: {max(irr_values)}, Mean: {sum(irr_values)/len(irr_values):.4f}")
        # Check if values are in kW/m2 (max < 1.5) or W/m2 (max > 100)
        max_val = max(irr_values)
        if max_val < 2.0:
            print(f"   *** VALUES APPEAR TO BE IN kW/m² (max={max_val:.3f})")
            print(f"   *** Converting to W/m²: max would be {max_val * 1000:.1f} W/m²")
            # Count how many would pass 50 W/m² threshold after conversion
            above_threshold = sum(1 for v in irr_values if v and v * 1000 >= 50)
            print(f"   *** Values >= 50 W/m² after conversion: {above_threshold}")
        else:
            print(f"   Values appear to be in W/m²")
    # Show some non-zero samples
    nonzero = [(ts, irr) for ts, irr in zip(ts_vals, irr_values) if irr and irr > 0]
    print(f"   Sample non-zero irradiance: {nonzero[:5]}")

# 8b. Check ALL POA data across all months
print("\n8b. POA data across all time:")
all_poa = pd.read_sql_query(f"""
    SELECT ts, payload 
    FROM readings 
    WHERE plant_uid = '{plant_uid}' 
    AND emig_id LIKE 'POA:%'
    ORDER BY ts
""", conn)
print(f"   Total POA readings: {len(all_poa)}")
if not all_poa.empty:
    irr_values = []
    ts_vals = []
    for idx, row in all_poa.iterrows():
        try:
            payload = json.loads(row['payload'])
            if 'poaIrradiance' in payload:
                irr = payload['poaIrradiance']
                if isinstance(irr, dict):
                    irr_values.append(irr.get('value', 0))
                else:
                    irr_values.append(irr)
                ts_vals.append(row['ts'])
        except:
            pass
    print(f"   Total with poaIrradiance: {len(irr_values)}")
    print(f"   Non-zero values: {sum(1 for v in irr_values if v and v > 0)}")
    if irr_values:
        nonzero_vals = [v for v in irr_values if v and v > 0]
        if nonzero_vals:
            print(f"   Non-zero min: {min(nonzero_vals)}, max: {max(nonzero_vals)}")
    # Show date range
    if ts_vals:
        print(f"   Date range: {ts_vals[0]} to {ts_vals[-1]}")

# 9. Check inverter irradiance in August (embedded in inverter data)
print("\n9. Check EMBEDDED irradiance in INVERTER data (August):")
aug_inv = pd.read_sql_query(f"""
    SELECT ts, emig_id, payload 
    FROM readings 
    WHERE plant_uid = '{plant_uid}' 
    AND emig_id LIKE 'INVERT:%'
    AND ts >= '2025-08-01' AND ts < '2025-09-01'
    ORDER BY ts
    LIMIT 50
""", conn)
print(f"   Inverter readings in August: {len(aug_inv)}")
if not aug_inv.empty:
    irr_values = []
    ts_values = []
    for idx, row in aug_inv.iterrows():
        try:
            payload = json.loads(row['payload'])
            if 'poaIrradiance' in payload:
                irr = payload['poaIrradiance']
                if isinstance(irr, dict):
                    val = irr.get('value', 0)
                else:
                    val = irr
                irr_values.append(val)
                ts_values.append(row['ts'])
        except:
            pass
    print(f"   Inverters with poaIrradiance field: {len(irr_values)}")
    print(f"   Sample values: {irr_values[:10]}")
    print(f"   Sample timestamps: {ts_values[:5]}")
    print(f"   Non-zero values: {sum(1 for v in irr_values if v and v > 0)}")
    print(f"   Max value: {max(irr_values) if irr_values else 0}")

conn.close()
print("\n" + "="*60)
print("ANALYSIS COMPLETE")
print("="*60)
