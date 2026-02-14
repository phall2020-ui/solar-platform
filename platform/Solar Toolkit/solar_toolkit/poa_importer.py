"""
SolarGIS POA Data Import Module.
Handles importing POA (Plane of Array) irradiance data from SolarGIS CSV files.
"""
import os
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional, List
import pandas as pd
from .utils import logger
from .config import settings

def fuzzy_match_filename(plant_name: str, filenames: List[str], threshold: float = 0.6) -> Optional[str]:
    """Find the best matching filename for a plant name using fuzzy string matching."""
    best_match = None
    best_score = 0.0
    plant_lower = plant_name.lower().replace("_", " ").replace("-", " ")

    for filename in filenames:
        base_name = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
        score = SequenceMatcher(None, plant_lower, base_name).ratio()
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = filename
            
    return best_match

def import_solargis_data(plant_alias: str, solargis_folder: str, start_date: str, end_date: str, store=None) -> int:
    """
    Imports POA data from SolarGIS CSVs in the specified folder and stores it.
    
    Returns: The total number of readings imported.
    """
    if store is None:
        from .plant_registry_store import PlantStore
        from .config import settings
        store = PlantStore(settings.DB_PATH)
    
    # Use the bulk importer for single file import
    from .poa_bulk_importer import POABulkImporter
    
    bulk_importer = POABulkImporter(store)
    
    # Scan folder and try to match file
    csv_files = bulk_importer.scan_folder(solargis_folder)
    if not csv_files:
        logger.warning(f"No CSV files found in {solargis_folder}")
        return 0
    
    # Try to match file to plant alias
    matched_file = fuzzy_match_filename(plant_alias, csv_files)
    if not matched_file:
        logger.error(f"No SolarGIS CSV file found matching '{plant_alias}' in {solargis_folder}")
        return 0
    
    logger.info(f"Matched file '{matched_file}' to plant '{plant_alias}'")
    
    count = bulk_importer.import_file(
        plant_alias=plant_alias,
        solargis_folder=solargis_folder,
        filename=matched_file,
        start_date=start_date,
        end_date=end_date
    )
    return count
