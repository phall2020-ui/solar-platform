"""Check irradiance units in the database - new tables format."""
import sqlite3
import json
import os

# Use the store db path
db_path = os.path.join("solar_toolkit", "plant_registry.sqlite")

if not os.path.exists(db_path):
    db_path = "plant_registry.sqlite"

if not os.path.exists(db_path):
    # Search for sqlite files
    for f in os.listdir("."):
        if f.endswith(".sqlite") or f.endswith(".db"):
            print(f"Found DB file: {f}")
            db_path = f
            break

print(f"Using database: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

# Check readings table structure
if 'readings' in tables:
    cur.execute("PRAGMA table_info(readings)")
    cols = [r[1] for r in cur.fetchall()]
    print(f"\nReadings table columns: {cols}")
    
    # If payload column exists, sample some payloads
    if 'payload' in cols:
        cur.execute("SELECT payload FROM readings LIMIT 5")
        rows = cur.fetchall()
        print("\nSample payloads:")
        for r in rows:
            try:
                payload = json.loads(r[0])
                print(f"  {payload}")
            except:
                print(f"  Raw: {r[0]}")
        
        # Find POA readings
        cur.execute("SELECT emig_id, payload FROM readings WHERE emig_id LIKE '%POA%' OR emig_id LIKE '%WETH%' LIMIT 10")
        poa_rows = cur.fetchall()
        print(f"\nPOA/Weather readings ({len(poa_rows)} samples):")
        for emig_id, payload_str in poa_rows:
            try:
                payload = json.loads(payload_str)
                print(f"  {emig_id}: {payload}")
                # Check for irradiance values
                for key in ['poaIrradiance', 'gti', 'GTI', 'irradiance', 'Irradiance']:
                    if key in payload:
                        val = payload[key]
                        if isinstance(val, dict) and 'value' in val:
                            print(f"    {key} = {val['value']} {val.get('unit', '')}")
                        else:
                            print(f"    {key} = {val}")
            except:
                print(f"  {emig_id}: Raw: {payload_str[:200]}")
else:
    print("No readings table found")

conn.close()
