import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite')
    
    uids = {'Hibernian Stadium': 'AMP:00002', 'Hibernian Training Ground': 'AMP:00003'}
    
    for name, uid in uids.items():
        print(f"\nChecking peak power for {name} ({uid})...")
        
        # Check max Active Power
        query = f"""
        SELECT MAX(CAST(json_extract(payload, '$.activePower.value') AS REAL)) as max_active
        FROM readings 
        WHERE plant_uid = '{uid}' 
          AND emig_id LIKE 'INVERT:%'
        """
        cursor = conn.cursor()
        cursor.execute(query)
        max_active = cursor.fetchone()[0]
        
        # Check max Apparent Power
        query_app = f"""
        SELECT MAX(CAST(json_extract(payload, '$.apparentPower.value') AS REAL)) as max_apparent
        FROM readings 
        WHERE plant_uid = '{uid}' 
          AND emig_id LIKE 'INVERT:%'
        """
        cursor.execute(query_app)
        max_apparent = cursor.fetchone()[0]
        
        print(f"  Max Active Power: {max_active} W ({max_active/1000 if max_active else 0:.2f} kW)")
        print(f"  Max Apparent Power: {max_apparent} W ({max_apparent/1000 if max_apparent else 0:.2f} kVA)")
        
    conn.close()

except Exception as e:
    print(f"Error: {e}")
