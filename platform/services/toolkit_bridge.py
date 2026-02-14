"""
Bridge service to Solar Toolkit functionality.
Provides a clean interface to access Solar Toolkit features without modifying the original code.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency (unified_config → services → toolkit_bridge → unified_config)
_config = None

def _get_config():
    global _config
    if _config is None:
        from unified_config import config as _cfg
        _config = _cfg
    return _config

def _ensure_toolkit_path():
    """Add Solar Toolkit to sys.path lazily."""
    cfg = _get_config()
    path_str = str(cfg.SOLAR_TOOLKIT_PATH)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Deferred Solar Toolkit imports
TOOLKIT_AVAILABLE = None  # None = not yet checked
_toolkit_modules = {}

def _ensure_toolkit_modules():
    """Lazily import Solar Toolkit modules."""
    global TOOLKIT_AVAILABLE, _toolkit_modules
    if TOOLKIT_AVAILABLE is not None:
        return TOOLKIT_AVAILABLE
    _ensure_toolkit_path()
    try:
        from solar_toolkit.config import settings as toolkit_settings
        from solar_toolkit.data_viewer import DataViewer
        from solar_toolkit.orchestrator import AnalysisOrchestrator
        _toolkit_modules.update({
            'toolkit_settings': toolkit_settings,
            'DataViewer': DataViewer,
            'AnalysisOrchestrator': AnalysisOrchestrator,
        })
        TOOLKIT_AVAILABLE = True
    except Exception as e:
        logger.warning("Solar Toolkit modules unavailable: %s", e)
        TOOLKIT_AVAILABLE = False
    return TOOLKIT_AVAILABLE


class ToolkitBridge:
    """Bridge to Solar Toolkit functionality."""
    
    def __init__(self):
        """Initialize the bridge."""
        _ensure_toolkit_modules()
        if not TOOLKIT_AVAILABLE:
            logger.warning("ToolkitBridge init skipped — Solar Toolkit not available")
            self.orch = None
            self.viewer = None
            return
            
        self.orch = _toolkit_modules['AnalysisOrchestrator']()
        ts = _toolkit_modules['toolkit_settings']
        self.viewer = _toolkit_modules['DataViewer'](db_path=ts.DB_PATH)
        logger.info("ToolkitBridge initialized, db=%s", ts.DB_PATH)
    
    def is_available(self) -> bool:
        """Check if Solar Toolkit functionality is available."""
        return bool(TOOLKIT_AVAILABLE) and self.orch is not None
    
    def get_plants(self) -> list[dict]:
        """Get all registered plants."""
        if not self.orch:
            return []
        return self.orch.get_plants()
    
    def get_plant(self, alias: str) -> dict | None:
        """Get a specific plant by alias."""
        return self.orch.store.load(alias)

    def resolve_plant_uid(self, alias: str) -> str | None:
        """Resolve plant alias to UID."""
        # 1. Direct Lookup
        plant = self.get_plant(alias)
        if plant:
            return plant.get('uid')
            
        # 2. Known Mappings (Reporting Alias -> Toolkit Alias)
        # Based on comparison of verify_id_mapping.py and list_toolkit_plants.py
        ALIAS_MAPPING = {
            "Merry Hill": "Merry Hill Shopping Centre",
            "Parfetts - Birmingham": "Parfetts Birmingham",
            "Sofina Haverhill": "Sofina Foods",
            "Hibernian FC": "Hibernian Stadium",
            "Hibernian Training": "Hibernian Training Ground",
            "Man City": "Man City FC Training Ground",
            "Cromwell": "Cromwell Tools",
            "Blachford": "Blachford UK",
            "Newfold": "Newfold Farm",
            "Sheldons": "Sheldons Bakery"
        }
        
        mapped_alias = ALIAS_MAPPING.get(alias)
        if mapped_alias:
            plant = self.get_plant(mapped_alias)
            if plant:
                return plant.get('uid')
        
        # 3. Case-insensitive / Fuzzy Lookup
        plants = self.get_plants()
        for p in plants:
            p_alias = p.get('alias', '')
            if p_alias.lower() == alias.lower():
                return p.get('uid')
            # Try mapping match against lowercase
            if mapped_alias and p_alias.lower() == mapped_alias.lower():
                return p.get('uid')
                
        return None
    
    def save_plant(
        self,
        alias: str,
        plant_uid: str,
        inverter_ids: list[str],
        weather_id: str | None = None,
        dc_size_kw: float | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        tilt: float | None = None,
        azimuth: float | None = None
    ) -> None:
        """Register or update a plant."""
        self.orch.save_plant(
            alias=alias,
            uid=plant_uid,
            inv_ids=inverter_ids,
            weth_id=weather_id,
            dc_size=dc_size_kw,
            latitude=latitude,
            longitude=longitude,
            tilt=tilt,
            azimuth=azimuth
        )
    
    def delete_plant(self, alias: str) -> bool:
        """Delete a plant from registry."""
        return self.orch.store.delete_plant(alias)
    
    # --- Data Fetching ---
    
    def fetch_readings(
        self,
        plant_uid: str,
        start_date: str,
        end_date: str,
        device_ids: list[str] | None = None
    ) -> int:
        """Fetch readings from API for a plant."""
        # fetch_data uses 'start' and 'end' parameter names
        return self.orch.fetch_data(
            plant_uid=plant_uid,
            start=start_date,
            end=end_date
        )
    
    def check_missing_inverters(
        self,
        plant_uid: str,
        start_date: str | None = None,
        end_date: str | None = None,
        auto_fetch: bool = False
    ) -> dict:
        """Check for and optionally fetch missing inverter data."""
        return self.orch.check_missing_inverters_by_uid(
            plant_uid=plant_uid,
            start_date=start_date,
            end_date=end_date,
            auto_fetch=auto_fetch
        )
    
    # --- Data Viewing ---
    
    def get_available_plants(self) -> list[str]:
        """Get list of plant UIDs with data in database."""
        return self.viewer.get_unique_plant_uids()
    
    def get_date_range(self, plant_uid: str) -> tuple[str | None, str | None]:
        """Get date range of available data for a plant."""
        return self.viewer.get_date_range(plant_uid=plant_uid)
    
    def get_device_ids(self, plant_uid: str) -> list[str]:
        """Get all device IDs for a plant."""
        return self.viewer.get_unique_device_ids(plant_uid)
    
    def get_readings(
        self,
        plant_uid: str,
        start_date: str | None = None,
        end_date: str | None = None,
        device_ids: list[str] | None = None,
        limit: int = 10000
    ) -> tuple[pd.DataFrame, int]:
        """Get readings data from database."""
        # Note: Underlying DataViewer doesn't support filtering by device_ids at query time
        df, count = self.viewer.get_readings_data(
            plant_uid=plant_uid,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        # Filter columns if device_ids provided
        if device_ids and not df.empty:
            # Assumes columns contain device IDs (wide format)
            # Keep timestamp/date columns + specific device columns
            keep_cols = [c for c in df.columns if any(d in c for d in device_ids) or 'time' in c.lower() or 'date' in c.lower()]
            df = df[keep_cols]
            
        return df, count

    def get_readings_stats(self) -> dict:
        """Lightweight stats for readings table (count, plants, devices, dates)."""
        if not self.viewer:
            return {}
        try:
            return self.viewer.get_readings_stats()
        except Exception:
            return {}
    
    # --- Analysis Functions ---
    
    def run_fouling_analysis(
        self,
        plant_uid: str,
        start_date: str,
        end_date: str,
        dc_size_kw: float,
        auto_clean_days: int = 3,
        use_monte_carlo: bool = False,
        mc_iterations: int = 1000
    ) -> dict:
        """Run fouling/soiling analysis."""
        return self.orch.run_fouling_analysis_from_db(
            plant_uid=plant_uid,
            start_date=start_date,
            end_date=end_date,
            dc_size=dc_size_kw,
            auto_days=auto_clean_days
        )

    def run_shading_analysis(
        self,
        plant_uid: str,
        baseline_months: list[str],
        compare_months: list[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Run shading analysis comparing summer baseline to winter period.
        
        Args:
            plant_uid: Plant UID
            baseline_months: List of "YYYY-MM" strings for baseline
            compare_months: List of "YYYY-MM" strings for comparison
            
        Returns:
            Tuple of (merged_data, summary_per_inverter)
        """
        if not self.orch or not self.viewer:
            return pd.DataFrame(), pd.DataFrame()
            
        try:
            # 1. Fetch data for baseline (Summer)
            summer_start = min(baseline_months) + "-01"
            # Get last day of last month
            last_m = max(baseline_months)
            y, m = map(int, last_m.split('-'))
            import calendar
            _, last_day = calendar.monthrange(y, m)
            summer_end = f"{last_m}-{last_day}"
            
            summer_df, _ = self.viewer.get_readings_data(
                plant_uid=plant_uid,
                start_date=summer_start,
                end_date=summer_end
            )
            
            # 2. Fetch data for comparison (Winter)
            winter_start = min(compare_months) + "-01"
            last_m = max(compare_months)
            y, m = map(int, last_m.split('-'))
            _, last_day = calendar.monthrange(y, m)
            winter_end = f"{last_m}-{last_day}"
            
            winter_df, _ = self.viewer.get_readings_data(
                plant_uid=plant_uid,
                start_date=winter_start,
                end_date=winter_end
            )
            
            if summer_df.empty:
                logger.warning("Shading analysis: no data for baseline period, plant_uid=%s", plant_uid)
                return pd.DataFrame(), pd.DataFrame()
            if winter_df.empty:
                logger.warning("Shading analysis: no data for comparison period, plant_uid=%s", plant_uid)
                return pd.DataFrame(), pd.DataFrame()
                
            # Filter for power columns only (assuming they contain 'inverted' or 'power')
            # The logic in run_shading_analysis_from_db expects inverter columns
            
            # 3. separate inverter data
            # Heuristic: columns that look like inverter IDs
            inv_cols = [c for c in summer_df.columns if 'inv' in c.lower() or ':' in c]
            
            summer_inv = summer_df[inv_cols]
            winter_inv = winter_df[inv_cols]
            
            # Prepare output path for reports
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)
            
            # Generate a timestamped filename base
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_base = str(reports_dir / f"shading_analysis_{plant_uid.replace(':','_')}_{timestamp}")
            
            # Run analysis
            merged_df, summary_df = self.orch.run_shading_analysis_from_db(
                summer_inv_df=summer_inv,
                winter_inv_df=winter_inv,
                power_col="power_ac", 
                summer_irr_df=None,
                winter_irr_df=None,
                output_base=output_base
            )
            
            return merged_df, summary_df
            
        except Exception as e:
            logger.error("Shading analysis failed for plant_uid=%s: %s", plant_uid, e, exc_info=True)
            return pd.DataFrame(), pd.DataFrame()
    
    def run_clipping_analysis(
        self,
        plant_alias: str,
        start_date: str,
        end_date: str,
        inverter_specs: dict
    ) -> dict:
        """Run inverter clipping loss simulation."""
        if not self.orch:
            return {}
            
        try:
            # Extract year from start_date
            year = int(start_date.split('-')[0])
            
            # Prepare params
            # Inverter specs from UI: {ac_capacity, efficiency, ...}
            # Module params? We might need to estimate or get from Plant object if not passed
            # For now constructing basics
            
            module_params = {
                'pdc0': inverter_specs.get('dc_capacity', 1000),
                'gamma_pdc': -0.004, # Standard temp coeff
                'temp_ref': 25
            }
            
            inv_params = {
                'pdc0': inverter_specs.get('dc_capacity', 1000),
                'eta_inv_nom': inverter_specs.get('efficiency', 0.98),
                'paco': inverter_specs.get('ac_capacity', 800)
            }
            
            # API key
            api_key = toolkit_settings.JUGGLE_API_KEY
            if not api_key:
                 # Fallback to env var if needed, or user provided
                 import os
                 api_key = os.environ.get("NREL_API_KEY", "")

            # Run analysis
            # Signature: run_clipping_analysis(self, plant_alias, year, module_params, inverter_params, api_key=None, email=None)
            ts_data, metrics = self.orch.run_clipping_analysis(
                plant_alias=plant_alias,
                year=year,
                module_params=module_params,
                inverter_params=inv_params,
                api_key=api_key,
                email="user@example.com" # Placeholder or config
            )
            
            # combine into result dict
            return {
                'timeseries': ts_data,
                'metrics': metrics
            }
            
        except Exception as e:
            logger.error("Clipping analysis failed for plant=%s: %s", plant_alias, e, exc_info=True)
            raise e
    
    # --- POA Import ---
    
    def import_poa_data(
        self,
        plant_alias: str,
        csv_file_path: str,
        start_date: str,
        end_date: str
    ) -> int:
        """Import POA irradiance data from SolarGIS CSV."""
        return self.orch.import_poa(
            plant_alias=plant_alias,
            solargis_folder=Path(csv_file_path).parent,
            start_date=start_date,
            end_date=end_date
        )
    
    # --- API Discovery ---
    
    def discover_plants_from_api(self) -> list[dict]:
        """Discover available plants from API."""
        try:
            from juggle_crawler import EmigApiClient
            
            api_key = toolkit_settings.JUGGLE_API_KEY or toolkit_settings.EMIG_API_KEY
            if not api_key:
                logger.warning("discover_plants: no API key configured (JUGGLE_API_KEY or EMIG_API_KEY)")
                return []
            
            client = EmigApiClient(api_key)
            # Use get_plant_list method to get available plants
            if hasattr(client, 'get_plant_list'):
                plants = client.get_plant_list()
                return plants if plants else []
            else:
                logger.warning("EmigApiClient missing get_plant_list method")
                return []
        except ImportError as e:
            logger.error("Could not import juggle_crawler: %s", e)
            return []
        except Exception as e:
            logger.error("Plant discovery failed: %s", e, exc_info=True)
            return []


# Lazy singleton — instantiated on first access to avoid circular import
_toolkit_instance = None

def _get_toolkit():
    global _toolkit_instance
    if _toolkit_instance is None:
        _toolkit_instance = ToolkitBridge()
    return _toolkit_instance

class _LazyToolkit:
    """Proxy that defers ToolkitBridge() creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(_get_toolkit(), name)
    def __bool__(self):
        return True

toolkit = _LazyToolkit()
