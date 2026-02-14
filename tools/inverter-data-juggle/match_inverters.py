import sqlite3
import pandas as pd
import json

INVERTERS_FOUND = [
    'INVERT:002946', 'INVERT:002947', 'INVERT:002948', 'INVERT:002949', 'INVERT:002950',
    'INVERT:002951', 'INVERT:002952', 'INVERT:002953', 'INVERT:002954', 'INVERT:002955',
    'INVERT:002956', 'INVERT:002957', 'INVERT:002958', 'INVERT:002959', 'INVERT:002960',
    'INVERT:002961', 'INVERT:002962', 'INVERT:002963', 'INVERT:002964', 'INVERT:002965',
    'INVERT:002966', 'INVERT:002967', 'INVERT:002968'
]

try:
    conn = sqlite3.connect('c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite')
    
    # Get all plants and their inverter lists
    query = "SELECT alias, plant_uid, inverter_ids FROM plants"
    df = pd.read_sql_query(query, conn)
    
    print(f"Checking {len(INVERTERS_FOUND)} inverters against {len(df)} plants...")
    
    found_map = {}
    
    for _, row in df.iterrows():
        try:
            # Parse JSON string to list
            inv_list = json.loads(row['inverter_ids']) if row['inverter_ids'] else []
            if not isinstance(inv_list, list):
                continue
                
            match_count = 0
            for inv in INVERTERS_FOUND:
                if inv in inv_list:
                    match_count += 1
                    found_map[inv] = row['alias']
            
            if match_count > 0:
                print(f"Plant: {row['alias']} ({row['plant_uid']}) matches {match_count} inverters.")
        except Exception as e:
            continue
            
    # Check for unmatched
    unmatched = [inv for inv in INVERTERS_FOUND if inv not in found_map]
    if unmatched:
        print(f"\nUnmatched Inverters ({len(unmatched)}): {unmatched}")
    else:
        print("\nAll inverters matched.")
        
    conn.close()

except Exception as e:
    print(f"Error: {e}")
