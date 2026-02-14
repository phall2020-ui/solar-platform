"""
One-time migration script to convert SQLite databases to DuckDB.
Run this once before starting the app after the code migration.

Usage:
    python migrate_to_duckdb.py
"""
import sqlite3
import duckdb
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from unified_config import config


def migrate_database(sqlite_path: Path, duckdb_path: Path) -> bool:
    """
    Migrate a SQLite database to DuckDB.
    
    Args:
        sqlite_path: Path to source SQLite database
        duckdb_path: Path to destination DuckDB database
        
    Returns:
        True if migration successful, False otherwise
    """
    if not sqlite_path.exists():
        print(f"  SQLite database not found: {sqlite_path}")
        return False
    
    if duckdb_path.exists():
        print(f"  DuckDB database exists: {duckdb_path}")
        print("  Merging into existing database...")
    
    print(f"  Migrating {sqlite_path.name} -> {duckdb_path.name}")
    
    try:
        # Connect to both databases
        sqlite_conn = sqlite3.connect(str(sqlite_path))
        duck_conn = duckdb.connect(str(duckdb_path))
        
        # Get all tables from SQLite
        tables = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        
        if not tables:
            print("  No tables found in source database.")
            sqlite_conn.close()
            duck_conn.close()
            return True
        
        print(f"  Found {len(tables)} table(s) to migrate...")
        
        for (table_name,) in tables:
            print(f"    - Migrating table: {table_name}")
            
            # Read from SQLite
            df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', sqlite_conn)
            
            # Write to DuckDB
            duck_conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            duck_conn.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')
            
            print(f"      Migrated {len(df)} rows")
        
        sqlite_conn.close()
        duck_conn.close()
        
        print(f"  ✓ Migration complete: {len(tables)} table(s) migrated")
        return True
        
    except Exception as e:
        print(f"  ✗ Migration failed: {e}")
        return False


def main():
    print("=" * 60)
    print("DuckDB Migration Script")
    print("=" * 60)
    print()
    
    migrations = [
        {
            "name": "Solar Toolkit Database",
            "sqlite_path": Path.home() / ".solar_toolkit" / "plant_registry.sqlite",
            "duckdb_path": Path.home() / ".solar_toolkit" / "plant_registry.duckdb",
        },
        {
            "name": "Reporting Database",
            "sqlite_path": config.MONTHLY_REPORTING_PATH / "solar_assets.db",
            "duckdb_path": config.REPORTING_DB,
        },
    ]
    
    for i, migration in enumerate(migrations, 1):
        print(f"[{i}/{len(migrations)}] {migration['name']}")
        print(f"  Source: {migration['sqlite_path']}")
        print(f"  Destination: {migration['duckdb_path']}")
        
        if migration['sqlite_path'].exists():
            success = migrate_database(migration['sqlite_path'], migration['duckdb_path'])
            if success:
                print()
        else:
            print(f"  No existing database to migrate - starting fresh!")
            print()
    
    print("Migration completed!")
    print()
    print("Next steps:")
    print("  1. Activate virtual environment: source .venv/bin/activate")  
    print("  2. Start the app: streamlit run app.py")
    print("  3. Verify the dashboard loads correctly")
    print()
    print("Note: Your original SQLite databases are preserved and were not modified.")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
