import pandas as pd

# Load CSV
csv_file = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/data_20250601_20251121.csv'
ORPHAN_IDS = [
    'INVERT:002946', 'INVERT:002947', 'INVERT:002948', 'INVERT:002949', 'INVERT:002950',
    'INVERT:002951', 'INVERT:002952', 'INVERT:002953', 'INVERT:002954', 'INVERT:002955',
    'INVERT:002956', 'INVERT:002957', 'INVERT:002958', 'INVERT:002959', 'INVERT:002960',
    'INVERT:002961', 'INVERT:002962', 'INVERT:002963', 'INVERT:002964', 'INVERT:002965',
    'INVERT:002966', 'INVERT:002967', 'INVERT:002968'
]

print("Calculating peak power for orphan inverters...")

# We need to sum power across all inverters for each timestamp
# But first we need to verify the column names. 
# Based on previous `Get-Content`, header was: timestamp,emigId,poaIrradiance,ts... 
# Wait, `get_generation_data` in my script used `json_extract(payload, '$.activePower.value')`.
# The CSV might be different. Let's assume standard columns or check header.

# Use chunking to be safe
chunksize = 50000
max_total_power = 0
timestamps_checked = 0

# We need to pivot or group by timestamp. Since the file is large, 
# reading all relevant rows into memory might be okay if we filter by ID first.
relevant_rows = []

try:
    for chunk in pd.read_csv(csv_file, chunksize=chunksize):
        # Filter for orphan IDs
        mask = chunk['emigId'].isin(ORPHAN_IDS)
        if mask.any():
            relevant_rows.append(chunk[mask])

    if relevant_rows:
        df = pd.concat(relevant_rows)
        print(f"Loaded {len(df)} rows for orphan inverters.")
        
        # Check columns. If it's the raw format, it might need parsing.
        # Assuming 'activePower' is a column or inside payload?
        # Let's inspect columns first.
        print("Columns:", df.columns.tolist())
        
        # If 'activePower' exists, use it. Else try apparentPower.
        if 'activePower' in df.columns:
            df['power'] = pd.to_numeric(df['activePower'], errors='coerce')
        elif 'apparentPower' in df.columns:
            df['power'] = pd.to_numeric(df['apparentPower'], errors='coerce')
        
        if 'power' in df.columns:
             # Convert timestamp
             if 'timestamp' in df.columns:
                 df['ts'] = pd.to_datetime(df['timestamp'])
             elif 'ts' in df.columns:
                 df['ts'] = pd.to_datetime(df['ts'])
                 
             # Group by timestamp and sum
             max_p = df.groupby('ts')['power'].sum().max()
             print(f"Peak Combined Power: {max_p} W ({max_p/1000:.2f} kW)")
        else:
             print("Power column not found. Columns:", df.columns)

    else:
        print("No rows found for orphan inverters.")

except Exception as e:
    print(f"Error: {e}")
