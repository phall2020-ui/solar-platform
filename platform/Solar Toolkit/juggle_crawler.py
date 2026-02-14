import os
import sys
import json
import csv
import time
import argparse
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- TIMESTAMP NORMALIZATION ---
INTERVAL_MINUTES = 15  # Standard interval for all data

def normalize_timestamp(ts: str, interval_minutes: int = INTERVAL_MINUTES) -> str:
    """
    Rounds a timestamp DOWN to the nearest interval boundary.
    E.g., 10:47 -> 10:45 for 15-minute intervals.
    Accepts ISO format (with or without Z) and returns ISO format with Z suffix.
    """
    # Parse various timestamp formats
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"]:
        try:
            dt = datetime.strptime(ts.replace('Z', ''), fmt.replace('Z', ''))
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Cannot parse timestamp: {ts}")
    
    # Round down to nearest interval
    minutes = (dt.minute // interval_minutes) * interval_minutes
    aligned_dt = dt.replace(minute=minutes, second=0, microsecond=0)
    return aligned_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_csv_with_aligned_timestamps(csv_path: str, plant_uid: str, emig_id: str = None) -> List[Dict]:
    """
    Parses a downloaded CSV and returns a list of reading dicts with:
    - ts_raw: original timestamp
    - ts_aligned: normalized to 15-minute boundary (for joining data)
    - All other columns as key-value pairs
    """
    readings = []
    df = pd.read_csv(csv_path)
    
    # Try to detect timestamp column
    ts_col = None
    for candidate in ['timestamp', 'Timestamp', 'ts', 'Time', 'time', 'Date/Time', 'datetime']:
        if candidate in df.columns:
            ts_col = candidate
            break
    
    if ts_col is None:
        # Try first column if it looks like a timestamp
        first_col = df.columns[0]
        if 'date' in first_col.lower() or 'time' in first_col.lower():
            ts_col = first_col
        else:
            raise ValueError(f"Could not detect timestamp column in CSV. Columns: {list(df.columns)}")
    
    for _, row in df.iterrows():
        ts_raw = str(row[ts_col])
        try:
            ts_aligned = normalize_timestamp(ts_raw)
        except ValueError:
            continue  # Skip rows with unparseable timestamps
        
        reading = {
            'plant_uid': plant_uid,
            'emig_id': emig_id or 'CRAWLED',
            'ts': ts_aligned,  # Use aligned as primary timestamp
            'ts_raw': ts_raw,
            'ts_aligned': ts_aligned,
        }
        
        # Add all other columns
        for col in df.columns:
            if col != ts_col:
                reading[col] = row[col] if pd.notna(row[col]) else None
        
        readings.append(reading)
    
    return readings


# --- CONFIGURATION & ENV VARS ---
JUGGLE_USERNAME = os.environ.get("JUGGLE_USERNAME", "peter.hall@ampyrde.com")
JUGGLE_PASSWORD = os.environ.get("JUGGLE_PASSWORD", "SuttonArms25!")
JUGGLE_APIKEY = os.environ.get("JUGGLE_APIKEY", "380fe299-a626-48f1-8456-e701c7383a23")

# EMIG API URLs
# All endpoints use /p/api (the API redirects /api to /p/api)
BASE_API_URL = "https://www.emig.co.uk/p/api"  # For plant-list, plant-details
BASE_METER_URL = "https://www.emig.co.uk/p/api"  # For meter readings (same base)
LOGIN_URL = "https://app.juggle.energy/"

# Data fetch constraints
MAX_DAYS_PER_REQUEST = 90  # API returns 413 if requesting too much data

def check_env_vars():
    missing = []
    if not JUGGLE_USERNAME: missing.append("JUGGLE_USERNAME")
    if not JUGGLE_PASSWORD: missing.append("JUGGLE_PASSWORD")
    if not JUGGLE_APIKEY: missing.append("JUGGLE_APIKEY")
    
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

def get_default_last_month():
    """Returns (start_date, end_date) objects for the previous month."""
    today = datetime.today()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    start_date = last_month.replace(day=1)
    return start_date, last_month

# --- LAYER 1: API CLIENT ---

class EmigApiClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()

    def get_plant_list(self):
        """Fetches the list of all plants."""
        try:
            url = f"{BASE_API_URL}/plant-list"
            resp = self.session.get(url, params={"apikey": self.api_key})
            resp.raise_for_status()
            return resp.json() 
        except Exception as e:
            print(f"[API] Error fetching plant list: {e}")
            return []


    def get_plant_details(self, plant_uid):
        """Fetches details for a specific plant to inspect meters (inverters only)."""
        try:
            url = f"{BASE_API_URL}/plant/{plant_uid}"
            resp = self.session.get(url, params={"apikey": self.api_key})
            resp.raise_for_status()
            details = resp.json()
            # Remove weather devices from meters
            if 'meters' in details:
                details['meters'] = [m for m in details['meters'] if m.get('type') == 'INVERTER']
            return details
        except Exception as e:
            print(f"[API] Error fetching details for {plant_uid}: {e}")
            return {}

    def get_meter_readings(self, emig_id: str, start_date: datetime, end_date: datetime, 
                           min_interval_s: int = 900) -> List[Dict]:
        """
        Fetches meter readings for a specific device (emigId).
        
        Args:
            emig_id: Device identifier (e.g., 'INVERT:002946')
            start_date: Start date for data retrieval
            end_date: End date for data retrieval  
            min_interval_s: Minimum interval in seconds (900=15min, 1800=30min, 3600=hourly)
            
        Returns:
            List of reading dictionaries with timestamp and measurement values
        """
        all_readings = []
        current_start = start_date
        
        # Chunk requests to avoid 413 errors (API has data limits)
        while current_start < end_date:
            chunk_end = min(current_start + timedelta(days=MAX_DAYS_PER_REQUEST), end_date)
            
            try:
                # Meter readings endpoint
                url = f"{BASE_METER_URL}/meter/{emig_id}/readings"
                params = {
                    "apikey": self.api_key,
                    "start": current_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "minIntervalS": min_interval_s
                }
                
                print(f"[API] Fetching {emig_id}: {current_start.date()} to {chunk_end.date()}...")
                resp = self.session.get(url, params=params, timeout=60)
                resp.raise_for_status()
                
                data = resp.json()
                readings = data.get('readings', [])
                
                # Add emigId to each reading for identification
                for r in readings:
                    r['emigId'] = emig_id
                    # Use 'ts' key (API returns both 'ts:' and 'ts')
                    if 'ts' in r:
                        r['timestamp'] = r['ts']
                
                all_readings.extend(readings)
                print(f"[API] Got {len(readings)} readings for chunk.")
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 413:
                    print(f"[API] Warning: 413 error (too much data). Try smaller date range or larger minIntervalS.")
                raise
            except Exception as e:
                print(f"[API] Error fetching readings for {emig_id}: {e}")
                raise
            
            current_start = chunk_end
        
        return all_readings

    def get_all_plant_readings(self, plant_uid: str, start_date: datetime, end_date: datetime,
                               min_interval_s: int = 900, device_types: List[str] = None) -> List[Dict]:
        """
        Fetches readings for all devices of a plant.
        
        Args:
            plant_uid: Plant identifier (e.g., 'ERS:00001')
            start_date: Start date for data retrieval
            end_date: End date for data retrieval
            min_interval_s: Minimum interval in seconds
            device_types: List of device types to include (default: ['INVERTER'])
            
        Returns:
            Combined list of readings from all devices
        """
        if device_types is None:
            device_types = ['INVERTER']
            
        # Get plant details to find devices
        details = self.get_plant_details(plant_uid)
        meters = details.get('meters', [])
        
        # Filter by device type
        target_devices = [m for m in meters if m.get('type') in device_types]
        
        if not target_devices:
            print(f"[API] No devices of type {device_types} found for plant {plant_uid}")
            return []
        
        print(f"[API] Found {len(target_devices)} devices to fetch for plant {plant_uid}")
        
        all_readings = []
        for device in target_devices:
            emig_id = device.get('emigId')
            if not emig_id:
                continue
            try:
                readings = self.get_meter_readings(emig_id, start_date, end_date, min_interval_s)
                all_readings.extend(readings)
            except Exception as e:
                print(f"[API] Failed to fetch {emig_id}: {e}")
                continue
        
        print(f"[API] Total readings fetched: {len(all_readings)}")
        return all_readings

    def analyze_plants(self):
        """
        Orchestrates the API analysis. 
        Returns a list of plant dicts that are missing devices.
        """
        print("[API] Fetching plant list...")
        raw_plants = self.get_plant_list()
        
        missing_device_plants = []
        
        print(f"[API] Analyzing {len(raw_plants)} plants for data completeness...")
        
        for p in raw_plants:
            uid = p.get('uid') or p.get('id') or p.get('plantUID')
            name = p.get('name') or p.get('plantName') or "Unknown"
            
            if not uid:
                continue

            details = self.get_plant_details(uid)
            meters = details.get('meters', [])
            # Only consider inverters from API
            api_inverters = [m.get('emigId') for m in meters if m.get('type') == 'INVERTER']
            # If no inverters, mark for crawling
            if not api_inverters:
                missing_device_plants.append({
                    "uid": uid,
                    "name": name,
                    "reason": "No inverters found"
                })
        default_template = {
            "template_name": "All Inverters 15min",
            "interval": "15 minute CSV",  # Always 15-minute for alignment
            "fields": ["Yield / kWh", "Power / kW"]
        }
        try:
            with open(path, 'r') as f:
                print(f"[System] Loading template from {path}...")
                template = json.load(f)
                # Force 15-minute interval for data alignment
                template['interval'] = "15 minute CSV"
                return template
        except FileNotFoundError:
            print(f"[System] Template not found. Creating default at {path}...")
            with open(path, 'w') as f:
                json.dump(default_template, f, indent=2)
            return default_template

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(viewport={'width': 1280, 'height': 800})
        self.page = self.context.new_page()

    def login(self):
        print(f"[Web] Logging into {LOGIN_URL}...")
        try:
            self.page.goto(LOGIN_URL)
            self.page.fill("input[name='email'], input[type='email']", JUGGLE_USERNAME)
            self.page.fill("input[name='password'], input[type='password']", JUGGLE_PASSWORD)
            self.page.click("button:has-text('Login'), button:has-text('Sign In')")
            self.page.wait_for_selector("text=Plants", timeout=30000)
            print("[Web] Login successful.")
        except Exception as e:
            print(f"[Web] Login failed: {e}")
            self.close()
            sys.exit(1)

    def download_inverter_data(self, plant_name, plant_uid, start_date, end_date, output_dir):
        """
        Navigates to the plant and downloads inverter data based on template.
        """
        print(f"[Web] Processing {plant_name} ({plant_uid})...")
        try:
            # 1. Navigate to Plant
            if "plants" not in self.page.url.lower():
                self.page.click("text=Plants")
                if self.page.is_visible("text=Plant List"):
                    self.page.click("text=Plant List")
                self.page.wait_for_load_state('networkidle')

            # Find and Click the Plant
            # Try by UID first, then Name
            plant_row = self.page.get_by_text(plant_uid, exact=False).first
            if not plant_row.is_visible():
                plant_row = self.page.get_by_text(plant_name, exact=True).first
            
            if plant_row.is_visible():
                plant_row.click()
            else:
                print(f"[Web] Warning: Could not find row for {plant_uid} in list.")
                return False

            self.page.wait_for_load_state('domcontentloaded')
            
            # 2. Go to Plot & Report
            self.page.click("text=Plot & Report")
            time.sleep(2) 
            
            # 3. Set Date Range
            print(f"      -> Setting date range: {start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}")
            
            # Open Date Picker
            self.page.click(".date-range-picker-trigger, button:has(.fa-calendar), [aria-label='Date Range']") 
            
            # TODO: Implement robust date selection. 
            # For now, we are assuming the user might need to manually intervene or we use default if UI is tricky.
            # But the requirement is to use the selected date.
            # If the UI allows typing dates, we should try that.
            # Let's try to find inputs within the picker.
            # self.page.fill("input[name='start']", start_date.strftime('%Y-%m-%d')) ...
            
            # 4. Set Interval
            print(f"      -> Setting interval: {self.template['interval']}")
            self.page.click("text=Frequency") 
            self.page.click(f"text={self.template['interval']}")
            
            # 5. Select Devices (Inverters)
            print("      -> Selecting inverters...")
            self.page.click("text=Uncheck all")
            self.page.click("text=Inverters") # Select all inverters
            
            # 6. Download
            print("      -> Downloading CSV...")
            with self.page.expect_download() as download_info:
                self.page.click("text=Download CSV")
            
            download = download_info.value
            filename = f"{plant_name.replace(' ', '_')}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv"
            save_path = os.path.join(output_dir, filename)
            download.save_as(save_path)
            print(f"      -> Saved to {save_path}")
            return True
            
        except Exception as e:
            print(f"[Web] Error processing {plant_name}: {e}")
            self.page.screenshot(path=os.path.join(output_dir, f"error_{plant_name}.png"))
            return False

    def download_and_parse(self, plant_name: str, plant_uid: str, start_date, end_date, output_dir: str) -> List[Dict]:
        """
        Downloads data for a plant and returns parsed readings with aligned timestamps.
        Returns empty list if download fails.
        """
        success = self.download_inverter_data(plant_name, plant_uid, start_date, end_date, output_dir)
        if not success:
            return []
        
        # Find the downloaded CSV
        filename = f"{plant_name.replace(' ', '_')}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv"
        csv_path = os.path.join(output_dir, filename)
        
        if not os.path.exists(csv_path):
            print(f"[Web] Warning: Expected CSV not found at {csv_path}")
            return []
        
        try:
            readings = parse_csv_with_aligned_timestamps(csv_path, plant_uid)
            print(f"[Web] Parsed {len(readings)} readings with aligned timestamps.")
            return readings
        except Exception as e:
            print(f"[Web] Error parsing CSV: {e}")
            return []

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

# --- MAIN CONTROLLER ---

def save_results(data, output_path):
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Results saved to {output_path}")

# --- UTILITY EXPORTS FOR TOOLING ---
def get_devices_from_api():
    """
    Returns a summary of all devices (inverters and weather stations) from the API.
    """
    check_env_vars()
    api_client = EmigApiClient(JUGGLE_APIKEY)
    raw_plants = api_client.get_plant_list()
    summary = []
    for p in raw_plants:
        uid = p.get('uid') or p.get('id') or p.get('plantUID')
        name = p.get('name') or p.get('plantName') or "Unknown"
        details = api_client.get_plant_details(uid)
        meters = details.get('meters', [])
        inverters = [m.get('emigId') for m in meters if m.get('type') == 'INVERTER']
        summary.append({
            "plantUID": uid,
            "plantName": name,
            "inverters": inverters
        })
    return summary

def run_crawler_for_site(site_uid, headless=True, start_date=None, end_date=None):
    """
    Runs the crawler for a single site (by UID) and returns parsed readings.
    """
    check_env_vars()
    api_client = EmigApiClient(JUGGLE_APIKEY)
    details = api_client.get_plant_details(site_uid)
    name = details.get('name') or details.get('plantName') or "Unknown"
    if not start_date or not end_date:
        start_date, end_date = get_default_last_month()
    output_dir = f"crawler_results_{site_uid}"
    os.makedirs(output_dir, exist_ok=True)
    crawler = JuggleCrawler(headless=headless)
    crawler.start()
    crawler.login()
    try:
        readings = crawler.download_and_parse(name, site_uid, start_date, end_date, output_dir)
    finally:
        crawler.close()
    return readings

def main():
    parser = argparse.ArgumentParser(description="Juggle/EMIG Missing Device Crawler")
    parser.add_argument("--headless", type=bool, default=False, help="Run browser in headless mode")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of plants to process (0 for all)")
    args = parser.parse_args()

    check_env_vars()

    # Date Logic
    if args.start_date and args.end_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
        except ValueError:
            print("Error: Invalid date format. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        print("No dates provided. Defaulting to Last Month.")
        start_date, end_date = get_default_last_month()

    # Output Directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"results_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory created: {output_dir}")

    # Step 1: API Analysis
    api_client = EmigApiClient(JUGGLE_APIKEY)
    plants_to_process = api_client.analyze_plants()

    if not plants_to_process:
        print("All plants appear complete in the API! No crawling needed.")
        return

    print(f"Found {len(plants_to_process)} plants requiring web crawling.")
    
    # Apply Limit
    if args.limit > 0:
        print(f"Limiting processing to {args.limit} plant(s).")
        plants_to_process = plants_to_process[:args.limit]

    # Step 2: Web Crawling
    crawler = JuggleCrawler(headless=args.headless)
    crawler.start()
    crawler.login()

    try:
        for plant in plants_to_process:
            success = crawler.download_inverter_data(
                plant['plantName'], 
                plant['plantUID'], 
                start_date, 
                end_date,
                output_dir
            )
            if success:
                plant['status'] = "processed"
                plant['source']['web']['inverters'] = ["Data Downloaded"] # Placeholder
            
            time.sleep(2)

    finally:
        crawler.close()

    # Step 3: Save Output
    save_results(plants_to_process, os.path.join(output_dir, "summary.json"))

if __name__ == "__main__":
    main()
