# Orchestrator: The Controller Layer
import os
import logging
import pandas as pd
from typing import Optional, List, Tuple, Dict
from .config import settings
from .utils import logger, date_range_to_ts
from .plant_registry_store import PlantStore
from .poa_importer import import_solargis_data
from .poa_bulk_importer import POABulkImporter, format_linkage_preview, PREVIEW_LIMIT
from .fouling_analysis import FoulingConfig, run_fouling_analysis, auto_select_clean_period, filter_by_date_range
from .shading_analysis import (
    ShadingSettings, 
    load_and_prepare, 
    process_season, 
    generate_plots,
    compare_profiles,
    summarise_shading,
    run_shading_analysis as run_shading_analysis_from_csv,
    analyze_from_dataframes,
    compute_daily_monthly_loss,
    plot_ratio_heatmap
)

class AnalysisOrchestrator:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH
        self.store = PlantStore(self.db_path)

    # --- PLANT REGISTRY ---
    def get_plants(self):
        return self.store.list_all()
    
    def save_plant(self, alias: str, uid: str, inv_ids: List[str], weth_id: Optional[str], dc_size: Optional[float]):
        self.store.save(alias, uid, inv_ids, weth_id, dc_size)
    
    def get_plant_devices(self, alias: str) -> List[str]:
        rec = self.store.load(alias)
        if rec:
            devices = rec.get('inverter_ids', [])
            if rec.get('weather_id'):
                devices.append(rec['weather_id'])
            return devices
        return []

    # --- FOULING ANALYSIS ---
    def run_fouling_auto(self, data_source_path: str, dc_size: float, auto_days: int = 3) -> dict:
        """
        Run fouling analysis with auto-detected clean period.
        
        Args:
            data_source_path: Path to the operational data CSV
            dc_size: DC system size in kW
            auto_days: Number of days to use for clean period detection
            
        Returns:
            Dict with analysis results including fouling_index and df_result
        """
        cfg = FoulingConfig()
        cfg.dc_size_kw = dc_size
        
        # Load data
        df = pd.read_csv(data_source_path)
        
        logger.info(f"Attempting to auto-select a {auto_days}-day clean period.")
        clean_df, (start_dt, end_dt) = auto_select_clean_period(df, cfg, days=auto_days)
            
        if clean_df.empty:
            raise ValueError("Could not determine a valid clean period for baseline calculation.")
        
        logger.info(f"Auto-selected clean period: {start_dt} to {end_dt}")
        return run_fouling_analysis(df, clean_df, cfg)
        
    # --- SHADING ANALYSIS ---
    def run_shading_analysis(self, summer_csv: str, winter_csv: str, output_base: str) -> pd.DataFrame:
        """
        Runs shading analysis comparing two seasonal CSV files.
        
        Args:
            summer_csv: Path to summer (baseline) CSV
            winter_csv: Path to winter (test) CSV
            output_base: Base filename for output files
            
        Returns:
            DataFrame with detailed comparison data
        """
        merged, summary = run_shading_analysis_from_csv(summer_csv, winter_csv, output_base)
        
        # Log summary
        if not summary.empty:
            logger.info("\n=== SHADING ANALYSIS SUMMARY ===")
            for _, row in summary.iterrows():
                logger.info(f"  {row[ShadingSettings().emigid_col]}: {row['classification']} (ratio: {row['ratio']:.2f}, loss: {row['estimated_loss_pct']:.1f}%)")
        
        return merged
    
    def run_shading_analysis_from_db(
        self, 
        summer_inv_df: pd.DataFrame, 
        winter_inv_df: pd.DataFrame,
        power_col: str,
        summer_irr_df: Optional[pd.DataFrame] = None,
        winter_irr_df: Optional[pd.DataFrame] = None,
        irr_col: str = 'poaIrradiance',
        output_base: str = None
    ) -> tuple:
        """
        Runs shading analysis using data loaded from the database.
        
        Args:
            summer_inv_df: Summer inverter data
            winter_inv_df: Winter inverter data
            power_col: Name of power column to use
            summer_irr_df: Optional Summer irradiance data
            winter_irr_df: Optional Winter irradiance data
            irr_col: Name of irradiance column
            output_base: Optional base filename for output files
            
        Returns:
            Tuple of (detailed_df, summary_df)
        """
        merged, summary = analyze_from_dataframes(
            summer_inv_df=summer_inv_df,
            winter_inv_df=winter_inv_df,
            power_col=power_col,
            summer_irr_df=summer_irr_df,
            winter_irr_df=winter_irr_df,
            irr_col=irr_col
        )
        
        # Generate outputs if requested
        if output_base and not merged.empty:
            cfg = ShadingSettings()
            csv_name = f"{output_base}_detail.csv"
            pdf_name = f"{output_base}.pdf"
            
            try:
                merged.to_csv(csv_name, index=False)
                logger.info(f"✓ Saved detailed data to {csv_name}")
            except Exception as e:
                logger.error(f"Error saving CSV: {e}")
            
            generate_plots(merged, pdf_name, cfg)
        
        return merged, summary
    # --- DATA FETCHING (Juggle API) ---
    def fetch_data(self, plant_uid: str, start: str, end: str, output: Optional[str] = None) -> int:
        """
        Fetch operational data for a plant via the EMIG API.
        
        This method fetches actual meter readings (time-series data) from the API.
        
        Args:
            plant_uid: Plant unique identifier (e.g., ERS:00001)
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format
            output: Optional path to write combined CSV
            
        Returns:
            Number of readings fetched
        """
        import sys
        import os
        from datetime import datetime
        import pandas as pd
        
        # Add project root to path to import juggle_crawler
        repo_root = os.path.dirname(os.path.dirname(__file__))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        
        from juggle_crawler import EmigApiClient
        
        api_key = settings.JUGGLE_API_KEY or settings.EMIG_API_KEY
        if not api_key:
            raise ValueError(
                "API key not configured. "
                "Please set JUGGLE_API_KEY or EMIG_API_KEY in your environment or .env file."
            )
        
        # Parse dates
        start_date = datetime.strptime(start, "%Y%m%d")
        end_date = datetime.strptime(end, "%Y%m%d")
        
        # Use the EmigApiClient which connects to the correct API
        client = EmigApiClient(api_key)
        
        logger.info(f"Fetching data for plant {plant_uid} from {start} to {end}...")
        
        # Fetch readings for all inverters in the plant
        readings = client.get_all_plant_readings(
            plant_uid=plant_uid,
            start_date=start_date,
            end_date=end_date,
            min_interval_s=settings.DEFAULT_MIN_INTERVAL_S,
            device_types=['INVERTER']
        )
        
        if not readings:
            logger.warning(f"No readings found for plant {plant_uid}")
            return 0
        
        logger.info(f"Retrieved {len(readings)} readings for {plant_uid}")
        
        # Store readings in database grouped by emigId
        readings_by_device = {}
        for r in readings:
            emig_id = r.get('emigId', 'UNKNOWN')
            if emig_id not in readings_by_device:
                readings_by_device[emig_id] = []
            readings_by_device[emig_id].append(r)
        
        total_stored = 0
        for emig_id, device_readings in readings_by_device.items():
            stored = self.store.store_readings(plant_uid, emig_id, device_readings)
            total_stored += stored
            logger.info(f"Stored {stored} readings for {emig_id}")
        
        # No CSV writing; only store to DB
        return len(readings)
    
    def _write_readings_to_csv(self, readings: List[Dict], output_path: str) -> None:
        """
        Write readings to a flattened CSV file.
        
        Flattens nested measurement structures like:
            {"apparentPower": {"value": 100, "unit": "VA"}}
        Into columns:
            apparentPower_value, apparentPower_unit
        """
        if not readings:
            return

        flat_data = []
        for r in readings:
            flat_r = {'timestamp': r.get('ts') or r.get('timestamp'), 'emigId': r.get('emigId')}
            for key, value in r.items():
                if key in ['ts', 'ts:', 'timestamp', 'emigId']:
                    continue
                if isinstance(value, dict) and 'value' in value:
                    flat_r[f"{key}_value"] = value['value']
                    if 'unit' in value:
                        flat_r[f"{key}_unit"] = value['unit']
                else:
                    flat_r[key] = value
            flat_data.append(flat_r)

        df = pd.DataFrame(flat_data)

        # Ensure output directory exists
        out_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else '.'
        os.makedirs(out_dir, exist_ok=True)

        # Robust file writing with error handling
        try:
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                df.to_csv(f, index=False)
            logger.info(f"Wrote {len(df)} records to {output_path}")
        except PermissionError as e:
            logger.error(f"Failed to write CSV due to file lock: {output_path} - {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to write CSV: {output_path} - {e}")
            raise
    # --- POA IMPORT (SolarGIS) ---
    def import_poa(self, plant_alias: str, solargis_folder: str, start_date: str, end_date: str) -> int:
        """
        Import POA data for a single plant.
        
        Args:
            plant_alias: The plant alias to import for
            solargis_folder: Path to folder containing SolarGIS CSVs
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            Number of readings imported
        """
        return import_solargis_data(plant_alias, solargis_folder, start_date, end_date, self.store)
    
    def import_poa_from_file(self, plant_alias: str, file_path: str, start_date: str = None, end_date: str = None) -> int:
        """
        Import POA data from a specific file path (for uploaded files).
        Imports all data in the file (date parameters are optional/ignored).
        
        Args:
            plant_alias: The plant alias to import for
            file_path: Full path to the CSV file
            start_date: (Optional, ignored) Start date in YYYYMMDD format
            end_date: (Optional, ignored) End date in YYYYMMDD format
            
        Returns:
            Number of readings imported
        """
        bulk_importer = POABulkImporter(self.store)
        
        # Get folder and filename from path
        folder = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # If no folder (temp file), use the file's directory
        if not folder:
            folder = '.'
        
        return bulk_importer.import_file(
            plant_alias=plant_alias,
            solargis_folder=folder,
            filename=filename
        )
    
    # --- POA BULK IMPORT PREVIEW ---
    def preview_bulk_poa_matches(self, solargis_folder: str) -> Dict:
        """
        Preview bulk POA import matches without importing.
        
        Args:
            solargis_folder: Path to folder containing SolarGIS CSVs
            
        Returns:
            Dict with matched_files, unmatched_files, and previews
        """
        bulk_importer = POABulkImporter(self.store)
        
        # Scan folder for CSV files
        csv_files = bulk_importer.scan_folder(solargis_folder)
        if not csv_files:
            return {'matched_files': {}, 'unmatched_files': [], 'previews': []}
        
        # Get all registered plants
        plants = bulk_importer.get_all_plants()
        if not plants:
            return {'matched_files': {}, 'unmatched_files': csv_files, 'previews': []}
        
        plant_aliases = [p['alias'] for p in plants]
        
        # Auto-match files to plants
        matches = bulk_importer.fuzzy_match_files(csv_files, plant_aliases)
        
        # Separate matched and unmatched files
        matched_files = {f: alias for f, alias in matches.items() if alias is not None}
        unmatched_files = [f for f, alias in matches.items() if alias is None]
        
        # Generate previews for matched files
        previews = []
        for filename, alias in list(matched_files.items())[:PREVIEW_LIMIT]:
            try:
                linkage = bulk_importer.show_linkage_preview(alias, filename, solargis_folder)
                previews.append(linkage)
            except Exception as e:
                logger.error(f"Error previewing {filename}: {e}")
        
        return {
            'matched_files': matched_files,
            'unmatched_files': unmatched_files,
            'previews': previews
        }
    
    # --- POA BULK IMPORT (SolarGIS) ---
    def bulk_import_poa(
        self, 
        solargis_folder: str, 
        start_date: str, 
        end_date: str,
        auto_confirm: bool = False
    ) -> Dict[str, int]:
        """
        Bulk import POA data with manual matching support.
        
        Args:
            solargis_folder: Path to folder containing SolarGIS CSVs
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            auto_confirm: If True, skip manual confirmation
            
        Returns:
            Dict mapping filename -> number of readings imported
        """
        bulk_importer = POABulkImporter(self.store)
        
        # Scan folder for CSV files
        csv_files = bulk_importer.scan_folder(solargis_folder)
        if not csv_files:
            logger.warning(f"No CSV files found in {solargis_folder}")
            return {}
        
        logger.info(f"Found {len(csv_files)} CSV files in folder.")
        
        # Get all registered plants
        plants = bulk_importer.get_all_plants()
        if not plants:
            logger.error("No plants registered in the database. Please register plants first.")
            return {}
        
        plant_aliases = [p['alias'] for p in plants]
        logger.info(f"Found {len(plant_aliases)} registered plants: {', '.join(plant_aliases)}")
        
        # Auto-match files to plants
        matches = bulk_importer.fuzzy_match_files(csv_files, plant_aliases)
        
        # Separate matched and unmatched files
        matched_files = {f: alias for f, alias in matches.items() if alias is not None}
        unmatched_files = [f for f, alias in matches.items() if alias is None]
        
        logger.info(f"\n{'='*60}")
        logger.info(f"AUTO-MATCHING RESULTS")
        logger.info(f"{'='*60}")
        logger.info(f"Matched: {len(matched_files)} files")
        logger.info(f"Unmatched: {len(unmatched_files)} files")
        
        # Show matches
        if matched_files:
            logger.info(f"\nAuto-matched files:")
            for filename, alias in matched_files.items():
                logger.info(f"  {filename} -> {alias}")
        
        if unmatched_files:
            logger.info(f"\nUnmatched files (will be skipped):")
            for filename in unmatched_files:
                logger.info(f"  {filename}")
        
        # Show preview of first few linkages
        if matched_files and not auto_confirm:
            logger.info(f"\n{'='*60}")
            logger.info(f"LINKAGE PREVIEW (showing first {min(PREVIEW_LIMIT, len(matched_files))})")
            logger.info(f"{'='*60}")
            
            for i, (filename, alias) in enumerate(list(matched_files.items())[:PREVIEW_LIMIT]):
                try:
                    linkage = bulk_importer.show_linkage_preview(alias, filename, solargis_folder)
                    logger.info(format_linkage_preview(linkage))
                except Exception as e:
                    logger.error(f"Error previewing {filename}: {e}")
        
        # Request confirmation
        if not auto_confirm:
            logger.info(f"\n{'='*60}")
            response = input(f"Proceed with import of {len(matched_files)} matched files? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                logger.info("Import cancelled by user.")
                return {}
        
        # Perform bulk import
        logger.info(f"\n{'='*60}")
        logger.info(f"STARTING BULK IMPORT")
        logger.info(f"{'='*60}\n")
        
        results = bulk_importer.bulk_import_with_matches(
            solargis_folder=solargis_folder,
            file_to_plant_map=matched_files,
            start_date=start_date,
            end_date=end_date
        )
        
        return results

    # --- DATA FETCHING (Web Crawler) ---
    def fetch_data_crawl(
        self, 
        plant_uid: str, 
        start: str, 
        end: str, 
        output_dir: Optional[str] = None,
        headless: bool = None
    ) -> int:
        """
        Fetch data using the web crawler for plants with incomplete API data.
        Uses Playwright to scrape the Juggle Energy web interface.
        
        Args:
            plant_uid: Plant unique identifier (e.g., ERS:00001)
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format
            output_dir: Directory for downloaded CSVs (temp dir if None)
            headless: Run browser headless (default from settings)
        
        Returns:
            Number of readings fetched and stored
        """
        from .crawlers.juggle_adapter import JuggleDataAdapter, CrawlerFetchConfig
        
        # Get credentials from settings
        username = settings.JUGGLE_USERNAME
        password = settings.JUGGLE_PASSWORD
        api_key = settings.EMIG_API_KEY
        
        if not username or not password:
            raise ValueError(
                "Crawler credentials not configured. "
                "Please set JUGGLE_USERNAME and JUGGLE_PASSWORD in your environment or .env file."
            )
        
        if not api_key:
            raise ValueError(
                "EMIG API key not configured. "
                "Please set EMIG_API_KEY or JUGGLE_APIKEY in your environment or .env file."
            )
        
        config = CrawlerFetchConfig(
            username=username,
            password=password,
            api_key=api_key,
            plant_uid=plant_uid,
            start_date=start,
            end_date=end,
            output_dir=output_dir,
            headless=headless if headless is not None else settings.CRAWLER_HEADLESS
        )
        
        adapter = JuggleDataAdapter(config)
        
        # Fetch data (store is None for now since PlantStore not fully integrated)
        # When PlantStore is enabled: readings = adapter.fetch_plant_data(self.store)
        readings = adapter.fetch_plant_data(plant_store=None)
        
        logger.info(f"Crawler fetch complete: {len(readings)} readings for {plant_uid}")
        return len(readings)
    
    def fetch_all_missing_plants_crawl(
        self, 
        start: str, 
        end: str, 
        output_dir: Optional[str] = None,
        headless: bool = None
    ) -> Dict[str, int]:
        """
        Analyze all plants and fetch data for those with incomplete API data.
        
        Args:
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format
            output_dir: Directory for downloaded CSVs
            headless: Run browser headless
        
        Returns:
            Dict mapping plant_uid -> number of readings fetched
        """
        from .crawlers.juggle_adapter import JuggleDataAdapter, CrawlerFetchConfig
        
        username = settings.JUGGLE_USERNAME
        password = settings.JUGGLE_PASSWORD
        api_key = settings.EMIG_API_KEY
        
        if not username or not password or not api_key:
            raise ValueError("Crawler credentials not fully configured.")
        
        config = CrawlerFetchConfig(
            username=username,
            password=password,
            api_key=api_key,
            plant_uid="",  # Not used for all-plants fetch
            start_date=start,
            end_date=end,
            output_dir=output_dir,
            headless=headless if headless is not None else settings.CRAWLER_HEADLESS
        )
        
        adapter = JuggleDataAdapter(config)
        results = adapter.fetch_all_plants_with_missing_devices(plant_store=None)
        
        return {uid: len(readings) for uid, readings in results.items()}
