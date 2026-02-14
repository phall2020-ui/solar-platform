import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite')
    
    # query plants
    query = """
    SELECT alias, plant_uid, dc_size_kw, inverter_ids
    FROM plants 
    WHERE alias LIKE '%Hibernian%'
    """
    
    df = pd.read_sql_query(query, conn)
    print(df)
    
    # If we find plants, lets check if we have readings for them
    if not df.empty:
        for _, row in df.iterrows():
            uid = row['plant_uid']
            print(f"\nChecking readings for {row['alias']} ({uid})...")
            
            # Check for ANY readings
            count_query = f"SELECT count(*) FROM readings WHERE plant_uid = '{uid}'"
            cursor = conn.cursor()
            cursor.execute(count_query)
            count = cursor.fetchone()[0]
            print(f"  Total readings: {count}")
            
            # Check for Generation readings (INVERT:)
            inv_query = f"SELECT count(*) FROM readings WHERE plant_uid = '{uid}' AND emig_id LIKE 'INVERT:%'"
            cursor.execute(inv_query)
            inv_count = cursor.fetchone()[0]
            print(f"  Inverter readings: {inv_count}")
            
    conn.close()

except Exception as e:
    print(f"Error: {e}")
