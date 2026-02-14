"""
SolarGIS POA Data Import Module.
Handles importing POA (Plane of Array) irradiance data from SolarGIS CSV files
and storing it in the plant database.
Refactored from solargis_poa_import.py.
"""
import os
import json
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import pandas as pd
from solar_toolkit.data.store import PlantStore
from solar_toolkit.utils import logger
from solar_toolkit.config import settings

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

def import_solargis_data(plant_alias: str, solargis_folder: str, start_date: str, end_date: str, store: PlantStore) -> int:
    """
    Imports POA data from SolarGIS CSVs in the specified folder and stores it.
    
    Returns: The total number of readings imported.
    """
    plant_rec = store.load(plant_alias)
    if not plant_rec:
        logger.error(f"Plant alias '{plant_alias}' not found in registry.")
        return 0
    
    plant_uid = plant_rec["plant_uid"]
    
    if not os.path.isdir(solargis_folder):
        logger.error(f"SolarGIS folder not found: {solargis_folder}")
        return 0

    files = [f for f in os.listdir(solargis_folder) if f.endswith('.csv')]
    if not files:
        logger.warning(f"No CSV files found in {solargis_folder}")
        return 0

    # 1. Match File
    matched_file = fuzzy_match_filename(plant_alias, files)
    if not matched_file:
        logger.error(f"No SolarGIS CSV file found matching '{plant_alias}' in {solargis_folder}")
        return 0

    file_path = os.path.join(solargis_folder, matched_file)
    
    # 2. Load and Prepare
    try:
        # Assumes SolarGIS format where the timestamp column is named "Date & time"
        df = pd.read_csv(file_path, parse_dates=["Date & time"], index_col="Date & time")
    except Exception as e:
        logger.error(f"Error reading or parsing CSV file {file_path}: {e}")
        return 0

    # Rename columns to standard internal names
    # Try to find POA Irradiance column (GTI Global Tilted Irradiance)
    poa_col = next((col for col in df.columns if 'POA' in col and 'Irradiance' in col and 'GTI' not in col), None)
    dc_col = next((col for col in df.columns if 'DC' in col and 'Capacity' in col), None)
    
    if not poa_col:
        logger.error("Could not find POA Irradiance column (e.g., 'POA Global Irradiance').")
        return 0

    # Filter by date range (inclusive)
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d").replace(hour=23, minute=59, second=59)
    df = df[(df.index >= start_dt) & (df.index <= end_dt)]

    if df.empty:
        logger.warning("No data within the specified date range.")
        return 0

    # 3. Create POA Emig ID (e.g., POA:CITYFOOTBALLGROUP)
    poa_emig_id = f"POA:{plant_alias.replace(' ', '_').upper()}"
    
    # 4. Convert to Readings format
    readings = []
    total_dc_capacity = 0.0
    
    for ts, row in df.iterrows():
        poa_value = row[poa_col]
        
        reading = {
            "ts": ts.isoformat() + "Z",
            "emigId": poa_emig_id,
            settings.POA_IRRADIANCE_COL: {"value": poa_value, "unit": "W/m2"},
        }
        readings.append(reading)
        
        if dc_col and pd.notna(row[dc_col]) and row[dc_col] > 0:
             total_dc_capacity = row[dc_col] # Last valid DC capacity found

    # 5. Store in DB
    store.store_readings(plant_uid, poa_emig_id, readings)
    logger.info(f"Imported {len(readings)} readings for {poa_emig_id}. Max POA: {df[poa_col].max():.1f} W/m2")
    
    # 6. Update plant DC capacity in registry
    if total_dc_capacity > 0:
        # Update with new DC capacity if currently zero or None
        current_dc_size = plant_rec.get('dc_size_kw')
        if current_dc_size is None or current_dc_size == 0:
            store.save(
                plant_rec['alias'],
                plant_uid,
                plant_rec.get('inverter_ids', []),
                plant_rec.get('weather_id'),
                total_dc_capacity
            )
            logger.info(f"Updated plant DC capacity in registry: {total_dc_capacity:.1f} kW")
        
    return len(readings)