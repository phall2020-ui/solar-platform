"""
Juggle Data Adapter: Wraps the Juggle Crawler to integrate with Solar Toolkit.
Provides same interface as existing data fetching but uses web scraping for plants with missing API devices.
"""
import os
import sys
import tempfile
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

# Add repo root to path for juggle_crawler import
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from juggle_crawler import (
    EmigApiClient, 
    JuggleCrawler, 
    normalize_timestamp, 
    parse_csv_with_aligned_timestamps,
    INTERVAL_MINUTES
)
from ..config import settings

logger = logging.getLogger("solar_toolkit.crawlers")


@dataclass
class CrawlerFetchConfig:
    """Configuration for crawler-based data fetching."""
    username: str
    password: str
    api_key: str
    plant_uid: str
    start_date: str  # YYYYMMDD format
    end_date: str    # YYYYMMDD format
    output_dir: Optional[str] = None
    headless: bool = True
    template_path: str = "report_template.json"


class JuggleDataAdapter:
    """
    Adapter that provides the same interface as existing Data Fetcher
    but uses the web crawler for plants with incomplete API data.
    
    Usage:
        adapter = JuggleDataAdapter(config)
        readings = adapter.fetch_plant_data(plant_store)
    """
    
    def __init__(self, cfg: CrawlerFetchConfig):
        self.cfg = cfg
        self.api_client = EmigApiClient(cfg.api_key)
        self._crawler = None
    
    def _get_dates(self):
        """Parse date strings to datetime objects."""
        start = datetime.strptime(self.cfg.start_date, "%Y%m%d")
        end = datetime.strptime(self.cfg.end_date, "%Y%m%d")
        return start, end
    
    def _ensure_output_dir(self) -> str:
        """Ensure output directory exists and return path."""
        if self.cfg.output_dir:
            output_dir = self.cfg.output_dir
        else:
            output_dir = tempfile.mkdtemp(prefix="juggle_crawl_")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    
    def check_api_completeness(self, plant_uid: str) -> Dict:
        """
        Check if a plant has complete device data in the API.
        Returns dict with 'is_complete', 'inverters', 'weather_devices'.
        """
        details = self.api_client.get_plant_details(plant_uid)
        meters = details.get('meters', [])
        
        inverters = [m.get('emigId') for m in meters if m.get('type') == 'INVERTER']
        weather = [m.get('emigId') for m in meters if m.get('type') in ('WEATHER_STATION', 'PYRANOMETER')]
        
        return {
            'is_complete': bool(inverters) and bool(weather),
            'inverters': inverters,
            'weather_devices': weather,
            'plant_name': details.get('name', 'Unknown')
        }
    
    def fetch_plant_data(self, plant_store=None) -> List[Dict]:
        """
        Fetches data for the configured plant.
        
        1. Checks API completeness
        2. If incomplete, uses web crawler
        3. Returns list of reading dicts with aligned timestamps
        4. Optionally stores to plant_store if provided
        
        Returns:
            List of reading dictionaries with ts, ts_aligned, and data fields
        """
        start_date, end_date = self._get_dates()
        output_dir = self._ensure_output_dir()
        
        # Check API status
        api_status = self.check_api_completeness(self.cfg.plant_uid)
        logger.info(f"[Adapter] Plant {self.cfg.plant_uid}: API complete={api_status['is_complete']}, "
                   f"inverters={len(api_status['inverters'])}, weather={len(api_status['weather_devices'])}")
        
        readings = []
        
        # Always use crawler for now (primary data source as requested)
        logger.info(f"[Adapter] Using web crawler for {self.cfg.plant_uid}...")
        
        crawler = JuggleCrawler(
            headless=self.cfg.headless,
            template_path=self.cfg.template_path
        )
        
        try:
            crawler.start()
            crawler.login()
            
            readings = crawler.download_and_parse(
                api_status['plant_name'],
                self.cfg.plant_uid,
                start_date,
                end_date,
                output_dir
            )
            
            logger.info(f"[Adapter] Fetched {len(readings)} readings via crawler.")
            
        except Exception as e:
            logger.error(f"[Adapter] Crawler error: {e}")
            raise
        finally:
            crawler.close()
        
        # Store to database if plant_store provided
        if plant_store and readings:
            try:
                import json
                # Group readings by emig_id for storage
                emig_groups = {}
                for r in readings:
                    emig_id = r.get('emig_id', 'CRAWLED')
                    if emig_id not in emig_groups:
                        emig_groups[emig_id] = []
                    emig_groups[emig_id].append(r)
                
                total_stored = 0
                for emig_id, group_readings in emig_groups.items():
                    count = plant_store.store_readings(
                        self.cfg.plant_uid,
                        emig_id,
                        group_readings
                    )
                    total_stored += count
                
                logger.info(f"[Adapter] Stored {total_stored} readings to database.")
            except Exception as e:
                logger.error(f"[Adapter] Error storing readings: {e}")
        
        return readings
    
    def fetch_all_plants_with_missing_devices(self, plant_store=None) -> Dict[str, List[Dict]]:
        """
        Analyzes all plants and fetches data for those with incomplete API data.
        
        Returns:
            Dict mapping plant_uid -> list of readings
        """
        plants_needing_crawl = self.api_client.analyze_plants()
        
        if not plants_needing_crawl:
            logger.info("[Adapter] All plants have complete API data.")
            return {}
        
        logger.info(f"[Adapter] Found {len(plants_needing_crawl)} plants needing web crawl.")
        
        results = {}
        start_date, end_date = self._get_dates()
        output_dir = self._ensure_output_dir()
        
        crawler = JuggleCrawler(
            headless=self.cfg.headless,
            template_path=self.cfg.template_path
        )
        
        try:
            crawler.start()
            crawler.login()
            
            for plant in plants_needing_crawl:
                plant_uid = plant['plantUID']
                plant_name = plant['plantName']
                
                logger.info(f"[Adapter] Processing {plant_name} ({plant_uid})...")
                
                readings = crawler.download_and_parse(
                    plant_name,
                    plant_uid,
                    start_date,
                    end_date,
                    output_dir
                )
                
                if readings:
                    results[plant_uid] = readings
                    
                    # Store if plant_store provided
                    if plant_store:
                        try:
                            count = plant_store.store_readings(plant_uid, 'CRAWLED', readings)
                            logger.info(f"[Adapter] Stored {count} readings for {plant_uid}.")
                        except Exception as e:
                            logger.error(f"[Adapter] Error storing {plant_uid}: {e}")
                
        finally:
            crawler.close()
        
        return results


def normalize_readings(readings: List[Dict], interval_minutes: int = INTERVAL_MINUTES) -> List[Dict]:
    """
    Utility to normalize timestamps in a list of readings.
    Adds ts_aligned field if not present.
    """
    for reading in readings:
        if 'ts_aligned' not in reading and 'ts' in reading:
            reading['ts_aligned'] = normalize_timestamp(reading['ts'], interval_minutes)
    return readings
