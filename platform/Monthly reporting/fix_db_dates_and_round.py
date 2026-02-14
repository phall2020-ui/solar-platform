"""
Database Date and Float Formatting Utility

This script normalizes both date columns and float columns across all tables
in the solar assets database. It:
- Converts date columns to 'Mon-YY' format (e.g., 'Jan-25')
- Rounds float columns to 1 decimal place for cleaner data presentation

Usage:
    Update DB_PATH with your database path and run the script.
"""

import sqlite3
import pandas as pd

# Path to your database
DB_PATH = r"c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/solar_assets.db"

# Connect to the database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all table names
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
tables = [t[0] for t in tables]

# Patterns to detect date columns
date_patterns = ["date", "month", "period", "time"]


def format_dates_and_round_floats_in_table(table: str) -> None:
    """
    Format date columns and round float columns in a specific table.

    Args:
        table: Name of the database table to process.
    """
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    changed = False
    # Format date fields
    for col in df.columns:
        if any(pat in col.lower() for pat in date_patterns):
            try:
                new_col = pd.to_datetime(df[col], errors="coerce").dt.strftime("%b-%y")
                if not new_col.equals(df[col]):
                    df[col] = new_col
                    changed = True
            except Exception:
                pass
    # Round float columns
    for col in df.select_dtypes(include=[float]).columns:
        new_col = df[col].round(1)
        if not new_col.equals(df[col]):
            df[col] = new_col
            changed = True
    if changed:
        df.to_sql(table, conn, if_exists="replace", index=False)
        print(f"Updated date/float fields in table: {table}")
    else:
        print(f"No date/float fields updated in table: {table}")


for t in tables:
    format_dates_and_round_floats_in_table(t)

conn.close()
print("All tables processed.")
