"""
Database Schema Inspector Utility

This script lists all tables and their column definitions in the solar assets
database. Useful for understanding the database structure and available data.

Usage:
    Update DB_PATH with your database path and run the script.
"""

import sqlite3

DB_PATH = r"c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/solar_assets.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# List all tables in the database
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for t in tables:
    print(t[0])

# Print columns for each table
for t in tables:
    print(f"\nColumns in table '{t[0]}':")
    cursor.execute(f"PRAGMA table_info({t[0]})")
    for col in cursor.fetchall():
        print(f"  {col[1]}")

conn.close()
