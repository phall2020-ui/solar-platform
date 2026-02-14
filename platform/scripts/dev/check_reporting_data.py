from unified_config import config
import sqlite3
import pandas as pd

try:
    db_path = config.REPORTING_DB
    print(f"Checking Reporting DB: {db_path}")
    if not db_path.exists():
        print("DB DOES NOT EXIST")
    else:
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql("SELECT DISTINCT Date FROM solar_data ORDER BY Date", conn)
            print("Available Months:")
            print(df)
            
            # Check row count
            count = pd.read_sql("SELECT COUNT(*) as c FROM solar_data", conn)
            print(f"Total Rows: {count['c'].iloc[0]}")
            
        except Exception as e:
            print(f"Error reading DB: {e}")
        finally:
            conn.close()
except Exception as e:
    print(f"Config Error: {e}")
