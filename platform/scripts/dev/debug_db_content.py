
import sqlite3
import pandas as pd
from unified_config import config

db_path = str(config.TOOLKIT_DB)
print(f"Connecting to DB: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    
    # Get any plant
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT plant_uid FROM readings LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        p_uid = row[0]
        print(f"Sampling data for plant: {p_uid}")
        
        # Get 5 samples
        query = "SELECT ts, plant_uid FROM readings WHERE plant_uid = ? ORDER BY ts DESC LIMIT 5"
        df = pd.read_sql_query(query, conn, params=(p_uid,))
        print("\n--- Sample Readings ---")
        print(df)
        
        if not df.empty:
            val = df['ts'].iloc[0]
            print(f"Sample TS value: '{val}' (Type: {type(val)})")
            
        # Check a specific date range query to mimic the failed one
        # Try finding ANY data for 2025
        print("\n--- Testing 2025 Query ---")
        q2 = "SELECT count(*) FROM readings WHERE plant_uid = ? AND ts LIKE '2025%'"
        c2 = conn.execute(q2, (p_uid,))
        print(f"Count for 2025: {c2.fetchone()[0]}")
        
    else:
        print("No readings found.")
        
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
