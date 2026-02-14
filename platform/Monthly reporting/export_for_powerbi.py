"""
Power BI Data Export Script
===========================

This script pre-calculates all solar performance metrics (losses, variances, yield)
using the shared logic in `analysis.py` and exports a clean CSV dataset ready for
Power BI import.

Usage:
    python export_for_powerbi.py

Output:
    powerbi_dataset.csv
"""

import json
import pandas as pd
from pathlib import Path
import sys

# Add current directory to path to ensure imports work
sys.path.append(str(Path(__file__).parent))

from config import Config
from data_access import SolarDataExtractor
from analysis import SolarDataAnalyzer

OUTPUT_FILE = "powerbi_dataset.csv"

def main():
    print("☀️  Starting Power BI Data Export...")

    # 1. Load Column Mapping
    print(f"📂 Loading column mapping from {Config.MAPPING_FILE}...")
    try:
        if Config.MAPPING_FILE.exists():
            colmap = json.loads(Config.MAPPING_FILE.read_text(encoding="utf-8"))
        else:
            print("❌ Error: colmap.json not found. Please run the Streamlit app and configure columns first.")
            return
    except Exception as e:
        print(f"❌ Error loading column mapping: {e}")
        return

    # 2. Load Data from Database
    print(f"floppy_disk Loading data from {Config.DEFAULT_DB}...")
    db = SolarDataExtractor(Config.DEFAULT_DB)
    
    # Check if table exists (assuming 'solar_data' or similar - let's check list_tables)
    tables = db.list_tables()
    if not tables:
        print("❌ No tables found in database.")
        return
    
    # Heuristic: Pick the first table that looks like data, or default to 'solar_data' if exists
    table_name = "solar_data"
    if "solar_data" not in tables:
        # If solar_data doesn't exist, try to find one
        if len(tables) > 0:
            table_name = tables[0]
            print(f"⚠️  'solar_data' table not found, using '{table_name}' instead.")
        else:
            print("❌ No tables found.")
            return

    success, df = db.query_data(f"SELECT * FROM {table_name}")
    if not success:
        print(f"❌ Error querying data: {df}")
        return

    print(f"✅ Loaded {len(df):,} rows.")

    # 3. Calculate Metrics
    print("🧮 Calculating performance metrics (Losses, Variances, Yield)...")
    try:
        analyzer = SolarDataAnalyzer(df, colmap)
        df_calculated = analyzer.compute_losses()
    except Exception as e:
        print(f"❌ Error during calculation: {e}")
        return

    # 4. Export to CSV
    print(f"💾 Exporting to {OUTPUT_FILE}...")
    try:
        # Select relevant columns - start with all, maybe filter later if needed
        # For Power BI, having everything is usually fine.
        
        # Ensure date format is friendly
        date_col = colmap.get("date")
        if date_col and date_col in df_calculated.columns:
            df_calculated[date_col] = pd.to_datetime(df_calculated[date_col], errors='coerce')
        
        df_calculated.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"✅ Successfully exported {len(df_calculated):,} rows to {OUTPUT_FILE}")
        print("\nNext Steps:")
        print("1. Open Power BI Desktop")
        print("2. Get Data -> Text/CSV")
        print(f"3. Select '{OUTPUT_FILE}'")
        print("4. You now have all calculated fields (Loss_Total_Tech_kWh, Var_Weather_kWh, etc.) ready for visualization.")
        
    except Exception as e:
        print(f"❌ Error exporting to CSV: {e}")

if __name__ == "__main__":
    main()
