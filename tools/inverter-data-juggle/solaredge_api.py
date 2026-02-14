"""
SolarEdge API Client
====================

Fetches inverter generation data from the SolarEdge Monitoring API.

Authentication: API Key passed as a query parameter 'api_key'.
"""

import os
import sys
import io
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_URL = "https://monitoringapi.solaredge.com"

def get_details(site_id: int, api_key: str) -> Dict[str, Any]:
    """
    Get site details.
    
    https://monitoringapi.solaredge.com/site/{siteId}/details?api_key={api_key}
    """
    url = f"{BASE_URL}/site/{site_id}/details"
    params = {"api_key": api_key}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("details", {})
    except requests.exceptions.RequestException as e:
        print(f"Error fetching details for site {site_id}: {e}")
        return {}

def get_energy(site_id: int, api_key: str, start_date: str, end_date: str, time_unit: str = "DAY") -> Dict[str, float]:
    """
    Get energy generation for a specific period.
    
    start_date: YYYY-MM-DD
    end_date: YYYY-MM-DD
    time_unit: DAY, MONTH, YEAR
    
    Returns a dictionary mapping date strings to energy values in kWh.
    """
    url = f"{BASE_URL}/site/{site_id}/energy"
    params = {
        "api_key": api_key,
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("energy", {})
        
        values = data.get("values", [])
        result = {}
        for entry in values:
            date_str = entry.get("date", "").split(" ")[0] # Format: YYYY-MM-DD HH:MM:SS
            value = entry.get("value")
            
            # SolarEdge returns None for future/missing data, treat as 0.0 only if strictly needed,
            # but usually None means 'no data'.
            if value is not None:
                result[date_str] = float(value) / 1000.0 # Convert Wh to kWh if unit is Wh?
                # Wait, SolarEdge /energy endpoint unit depends on the site settings or can be inferred.
                # Usually it's in Wh.
                # Let's verify unit if possible, but standard is Wh.
        
        # Check unit
        unit = data.get("unit", "Wh")
        if unit == "Wh":
            # Already divided by 1000 above? No, I did.
            pass
        elif unit == "kWh":
            # If it's already kWh, I shouldn't have divided.
             # Let's re-process to be safe.
            result = {}
            for entry in values:
                date_str = entry.get("date", "").split(" ")[0]
                val = entry.get("value")
                if val is not None:
                    if unit == "Wh":
                        result[date_str] = float(val) / 1000.0
                    else:
                         result[date_str] = float(val)
        
        return result

    except requests.exceptions.RequestException as e:
        print(f"Error fetching energy for site {site_id}: {e}")
        return {}

def get_power(site_id: int, api_key: str, start_time: str, end_time: str) -> Dict[str, float]:
    """
    Get power details (15-min resolution usually).
    
    start_time: YYYY-MM-DD HH:MM:SS
    end_time: YYYY-MM-DD HH:MM:SS
    """
    url = f"{BASE_URL}/site/{site_id}/power"
    params = {
        "api_key": api_key,
        "startTime": start_time,
        "endTime": end_time
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("power", {})
        
        values = data.get("values", [])
        result = {}
        for entry in values:
             date_str = entry.get("date")
             val = entry.get("value")
             if val is not None:
                 result[date_str] = float(val)
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error fetching power for site {site_id}: {e}")
        return {}

if __name__ == "__main__":
    # Simple test if run directly
    print("SolarEdge API Module")
