import pandas as pd

# Load CSV and maximize chunksize to avoid memory issues
chunksize = 100000
csv_file = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/data_20250601_20251121.csv'

unique_ids = set()

print("Scanning CSV for unique emigIds...")
try:
    for chunk in pd.read_csv(csv_file, chunksize=chunksize, usecols=['emigId']):
        unique_ids.update(chunk['emigId'].unique())
        
    print(f"Found {len(unique_ids)} unique IDs:")
    for uid in sorted(unique_ids):
        print(uid)
except Exception as e:
    print(f"Error: {e}")
