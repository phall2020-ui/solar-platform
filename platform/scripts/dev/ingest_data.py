import pandas as pd
from services import reporting_bridge as reporting
import sys
from pathlib import Path

# File path
file_path = r"C:\Users\PeterHall\OneDrive - AMPYR IDEA UK Ltd\Database import portfolio.xlsx"
table_name = "Imported_Portfolio_Data"

print(f"Reading file: {file_path}")

try:
    # Read Excel
    df = pd.read_excel(file_path)
    print(f"Loaded {len(df)} rows and {len(df.columns)} columns.")
    
    # Save to DB
    print(f"Saving to table '{table_name}'...")
    success = reporting.save_table_data(table_name, df, if_exists='replace')
    
    if success:
        print("✅ Success! Data imported to database.")
    else:
        print("❌ Failed to save data.")

except Exception as e:
    print(f"Error: {e}")
