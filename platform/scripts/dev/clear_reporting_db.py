
import sqlite3
from unified_config import config

db_path = str(config.REPORTING_DB)
print(f"Clearing DB: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables = ["Imported_Portfolio_Data", "Database_import_portfolio", "solar_data"]
    
    for t in tables:
        print(f"Deleting from {t}...")
        cursor.execute(f"DELETE FROM '{t}'")
        
    conn.commit()
    conn.close()
    print("✅ All data cleared successfully.")
except Exception as e:
    print(f"Error: {e}")
