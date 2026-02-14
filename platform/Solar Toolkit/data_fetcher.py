"""
Juggle Energy API Data Fetching Module.
Handles device discovery and reading retrieval from the Juggle Energy API.
"""
import os
import json
import requests
import pandas as pd
from typing import List, Dict, Sequence, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from solar_toolkit.config import settings
from solar_toolkit.utils import logger, date_range_to_ts

# Juggle API configuration
BASE_URL = settings.JUGGLE_BASE_URL
MAX_DAYS_PER_REQUEST = 104  # Maximum number of days the API can return for half-hourly data

@dataclass
class FetchConfig:
    api_key: str
    plant_uid: str
    start_date: str  # YYYYMMDD
    end_date: str    # YYYYMMDD
    min_interval_s: int = settings.DEFAULT_MIN_INTERVAL_S
    # The API key is sensitive and should not be logged
    
def _get_api_headers(api_key: str) -> Dict[str, str]:
    """Returns the standard headers for API calls."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def get_plant_devices(cfg: FetchConfig) -> List[str]:
    """
    Retrieves the list of inverters associated with a plant.
    """
    logger.debug(f"Querying devices for plant {cfg.plant_uid}...")
    url = f"{BASE_URL}/plants/{cfg.plant_uid}/devices"
    headers = _get_api_headers(cfg.api_key)
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Filter for inverters (typically type == 'inverter')
        inverter_ids = [
            d["emigId"] for d in data.get("results", [])
            if d.get("deviceType", "").lower() == "inverter"
        ]
        
        # Also include a weather station ID if configured (might not be in 'devices' list)
        # This function only handles explicit device listing, weather ID is usually handled
        # separately or fetched by a user-supplied ID from the store.
        
        return inverter_ids
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API Error fetching devices for {cfg.plant_uid}: {e}")
        return []

def _fetch_readings_chunk(cfg: FetchConfig, emig_id: str, start_ts: str, end_ts: str) -> List[Dict]:
    """
    Fetches a single chunk of readings for a device.
    """
    url = f"{BASE_URL}/devices/{emig_id}/readings"
    headers = _get_api_headers(cfg.api_key)
    
    params = {
        "start": start_ts,
        "end": end_ts,
        "minIntervalS": cfg.min_interval_s,
    }
    
    logger.debug(f"Fetching {emig_id}: {start_ts} to {end_ts}")
    
    response = requests.get(url, headers=headers, params=params, timeout=60)
    response.raise_for_status()
    
    data = response.json()
    return data.get("results", [])

def fetch_all_readings(cfg: FetchConfig, emig_id: str) -> List[Dict]:
    """
    Handles date range segmentation and fetches all readings for a device.
    """
    all_readings: List[Dict] = []
    
    # Convert YYYYMMDD to datetime objects
    start_dt = datetime.strptime(cfg.start_date, "%Y%m%d")
    end_dt = datetime.strptime(cfg.end_date, "%Y%m%d")
    
    current_dt = start_dt
    
    while current_dt <= end_dt:
        chunk_start_dt = current_dt
        chunk_end_dt = min(
            end_dt,
            current_dt + timedelta(days=MAX_DAYS_PER_REQUEST - 1)
        )
        
        # Convert to ISO timestamps (start of start day, end of end day)
        start_ts = chunk_start_dt.isoformat() + "Z"
        # Set end time to 23:59:59.999Z for full day inclusion
        end_ts = (chunk_end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).isoformat() + "Z"

        try:
            readings = _fetch_readings_chunk(cfg, emig_id, start_ts, end_ts)
            for r in readings:
                 r["emigId"] = emig_id # Add emigId to each reading payload
            all_readings.extend(readings)
            
            logger.debug(f"Fetched {len(readings)} records for chunk {chunk_start_dt.strftime('%Y%m%d')} to {chunk_end_dt.strftime('%Y%m%d')}.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data chunk for {emig_id} from {chunk_start_dt.date()} to {chunk_end_dt.date()}: {e}")
            # Decide whether to raise or continue; raising is safer for analysis
            raise

        # Move to the start of the next day
        current_dt = chunk_end_dt + timedelta(days=1)
        
    return all_readings

def write_combined_csv(readings: Sequence[Dict], output_path: str) -> None:
    """
    Writes a combined list of readings (from multiple devices) to a single CSV file.
    It flattens nested data (e.g., {"apparentPower": {"value": 100, "unit": "kW"}})
    into separate value and unit columns (e.g., apparentPower_value, apparentPower_unit).
    """
    if not readings:
        logger.warning("No readings to write to CSV.")
        return

    flat_data = []
    for r in readings:
        flat_r: Dict[str, str | float] = {"ts": r.get("ts"), "emigId": r.get("emigId")}
        
        for key, value in r.items():
            if key in ["ts", "emigId"]:
                continue
                
            if isinstance(value, dict) and 'value' in value and 'unit' in value:
                flat_r[f"{key}_value"] = value['value']
                flat_r[f"{key}_unit"] = value['unit']
            else:
                flat_r[key] = value
                
        flat_data.append(flat_r)

    df = pd.DataFrame(flat_data)
    
    # Rename 'ts' column to 'timestamp' for consistency with other modules
    if 'ts' in df.columns:
        df = df.rename(columns={'ts': 'timestamp'})
        
    # Write to CSV
    df.to_csv(output_path, index=False)
    logger.info(f"Combined data for {len(readings)} records written to {output_path}")