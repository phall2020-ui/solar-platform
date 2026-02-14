import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite')
    
    orphan_id = 'INVERT:002946'
    print(f"Checking for {orphan_id} in readings table...")
    
    query = f"""
    SELECT DISTINCT plant_uid, emig_id 
    FROM readings 
    WHERE emig_id = '{orphan_id}'
    """
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        print("Found in readings:")
        print(df)
        
        # Check alias for the UID
        uid = df.iloc[0]['plant_uid']
        alias_query = f"SELECT alias, dc_size_kw FROM plants WHERE plant_uid = '{uid}'"
        alias_df = pd.read_sql_query(alias_query, conn)
        print("\nPlant Details:")
        print(alias_df)
    else:
        print("Not found in readings table.")
        
    conn.close()

except Exception as e:
    print(f"Error: {e}")
