
import sys
import os
import sqlite3
from unified_config import config

# Check Plant Registry
db_path = r"C:\Users\PeterHall\.solar_toolkit\plant_registry.sqlite"
print(f"Checking Candidate DB Path: {db_path}")
print(f"Checking if file exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"All tables in DB: {tables}")
        
        if ('readings',) in tables:
            print("Table 'readings' exists!")
            cursor.execute("SELECT count(*) FROM readings")
            print(f"Total readings: {cursor.fetchone()[0]}")
            
            # Check for AMP:00001
            cursor.execute("SELECT count(*), min(ts), max(ts) FROM readings WHERE plant_uid='AMP:00001'")
            res = cursor.fetchone()
            print(f"Data for AMP:00001: Count={res[0]}, Min={res[1]}, Max={res[2]}")
            
        else:
            print("Table 'readings' DOES NOT exist in this DB.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print("solar_data.db not found at expected path.")
