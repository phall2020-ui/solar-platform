
import sqlite3
import pandas as pd
from unified_config import config

db_path = str(config.REPORTING_DB)
print(f"Connecting to DB: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print("\n--- Tables ---")
    for t in tables:
        t_name = t[0]
        count = cursor.execute(f"SELECT COUNT(*) FROM '{t_name}'").fetchone()[0]
        print(f"{t_name}: {count} rows")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
