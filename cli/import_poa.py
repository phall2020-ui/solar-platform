#!/usr/bin/env python
"""
Import December 2025 POA data for all sites from SolarGIS CSVs.
"""
import os
import sys

# Add Solar Toolkit to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'Solar Toolkit'))

from solar_toolkit.plant_registry_store import PlantStore
from solar_toolkit.poa_bulk_importer import POABulkImporter
from solar_toolkit.config import settings

def main():
    # Path to downloaded POA data
    poa_folder = os.path.expanduser("~/Downloads/2025 12")
    
    if not os.path.exists(poa_folder):
        print(f"ERROR: POA folder not found: {poa_folder}")
        return 1
    
    # Initialize store and importer
    store = PlantStore(settings.DB_PATH)
    importer = POABulkImporter(store)
    
    # Scan for CSV files
    csv_files = importer.scan_folder(poa_folder)
    print(f"\nFound {len(csv_files)} CSV files in {poa_folder}")
    
    # Get all registered plants
    plants = importer.get_all_plants()
    plant_aliases = [p['alias'] for p in plants]
    print(f"Found {len(plant_aliases)} registered plants")
    
    # Fuzzy match files to plants
    matches = importer.fuzzy_match_files(csv_files, plant_aliases, threshold=0.5)
    
    # Show matches and filter valid ones
    valid_matches = {}
    unmatched = []
    
    print("\n=== File to Plant Matching ===")
    for filename, plant_alias in sorted(matches.items()):
        if plant_alias:
            valid_matches[filename] = plant_alias
            print(f"  ✓ {filename} -> {plant_alias}")
        else:
            unmatched.append(filename)
            print(f"  ✗ {filename} -> NO MATCH")
    
    print(f"\nMatched: {len(valid_matches)} files")
    print(f"Unmatched: {len(unmatched)} files")
    
    if not valid_matches:
        print("No matches found! Check plant registration.")
        return 1
    
    # Import all matched files
    print("\n=== Importing POA Data ===")
    results = importer.bulk_import_with_matches(
        solargis_folder=poa_folder,
        file_to_plant_map=valid_matches,
        start_date="2025-12-01",
        end_date="2025-12-31"
    )
    
    # Summary
    total_imported = sum(results.values())
    print(f"\n=== Import Complete ===")
    print(f"Total readings imported: {total_imported:,}")
    for filename, count in sorted(results.items()):
        print(f"  {filename}: {count:,} readings")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
