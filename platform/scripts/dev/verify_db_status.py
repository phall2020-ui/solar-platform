import duckdb
from pathlib import Path
import os

# Define the path we found
db_path = Path("/Users/peterhall/.solar_toolkit/plant_registry.duckdb")

print(f"Checking database at: {db_path}")

if not db_path.exists():
    print("❌ Database file not found!")
    exit(1)

print(f"✅ Database size: {db_path.stat().st_size} bytes")

try:
    con = duckdb.connect(str(db_path))
    
    # List tables
    tables = con.execute("SHOW TABLES").fetchall()
    print(f"\nFound {len(tables)} tables:")
    
    for table in tables:
        table_name = table[0]
        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f" - {table_name}: {count} rows")
        
        # Print sample for plants or solar_data
        if count > 0:
            print(f"   Sample columns: {con.execute(f'DESCRIBE {table_name}').fetchall()}")
            print(f"   First row: {con.execute(f'SELECT * FROM {table_name} LIMIT 1').fetchall()}")

except Exception as e:
    print(f"❌ Error reading database: {e}")
