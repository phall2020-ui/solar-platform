"""
Bulk POA Data Import Module.
Handles importing POA (Plane of Array) irradiance data from multiple SolarGIS CSV files
with manual matching when file names don't exactly match site names.

Supports multiple arrays per site with capacity-weighted consolidation aligned to 
inverter data periods (e.g., 15-minute intervals).
"""
import os
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from solar_toolkit.plant_registry_store import PlantStore
from solar_toolkit.utils import logger
from solar_toolkit.config import settings

# Constants
PREVIEW_LIMIT = 5  # Number of previews to show in UI/CLI


class POABulkImporter:
    """Handles bulk import of POA data with manual matching support."""
    
    def __init__(self, store: PlantStore):
        self.store = store
        
    def scan_folder(self, solargis_folder: str) -> List[str]:
        """Scan folder for CSV files."""
        if not os.path.isdir(solargis_folder):
            raise ValueError(f"Folder not found: {solargis_folder}")
        
        files = [f for f in os.listdir(solargis_folder) if f.endswith('.csv')]
        return sorted(files)
    
    def get_all_plants(self) -> List[Dict[str, Any]]:
        """Get all registered plants from the store."""
        return self.store.list_all()
    
    def fuzzy_match_files(
        self, 
        filenames: List[str], 
        plant_aliases: List[str], 
        threshold: float = 0.6
    ) -> Dict[str, Optional[str]]:
        """
        Fuzzy match files to plant aliases.
        
        Returns:
            Dict mapping filename -> plant_alias (or None if no match)
        """
        matches = {}
        used_aliases = set()
        
        for filename in filenames:
            base_name = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
            best_match = None
            best_score = 0.0
            
            for alias in plant_aliases:
                if alias in used_aliases:
                    continue
                    
                alias_lower = alias.lower().replace("_", " ").replace("-", " ")
                score = SequenceMatcher(None, base_name, alias_lower).ratio()
                
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = alias
            
            if best_match:
                matches[filename] = best_match
                used_aliases.add(best_match)
            else:
                matches[filename] = None
                
        return matches
    
    def preview_file_data(
        self, 
        solargis_folder: str, 
        filename: str, 
        max_rows: int = 5
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Preview the first few rows of a POA data file and extract metadata.
        Detects multi-array files and reports array information.
        
        Returns:
            Tuple of (preview_dataframe, metadata_dict)
        """
        file_path = os.path.join(solargis_folder, filename)
        
        try:
            # Read the CSV file
            df = pd.read_csv(file_path)
            
            # Map lowercase column names to original
            cols_lower = {c.lower(): c for c in df.columns}
            
            # Check if multi-array format (SolarGIS format has array_cap or array_capacity)
            has_multi_array = (
                any(k in cols_lower for k in ["array_capacity", "array_cap"]) and 
                "azimuth" in cols_lower and
                any(k in cols_lower for k in ["tilt", "slope"])
            )
            
            # Find time column - check multiple possible names
            time_col = None
            for candidate in ["time", "date & time", "timestamp", "datetime", "date"]:
                if candidate in cols_lower:
                    time_col = cols_lower[candidate]
                    break
            
            if time_col:
                # Try multiple timestamp formats for SolarGIS data
                df[time_col] = pd.to_datetime(df[time_col], errors="coerce", format="mixed")
            
            # Find POA/GTI column - SolarGIS uses 'gti'
            poa_col = None
            for candidate in ["gti", "poa irradiance", "poairradiance", "poa"]:
                if candidate in cols_lower:
                    poa_col = cols_lower[candidate]
                    break
            if poa_col is None:
                poa_col = next(
                    (col for col in df.columns if 'POA' in col and 'Irradiance' in col and 'GTI' not in col), 
                    None
                )
            
            # Extract metadata
            metadata = {
                'total_rows': len(df),
                'date_range': (
                    df[time_col].min().strftime('%Y-%m-%d') if time_col and not df[time_col].isna().all() else 'N/A',
                    df[time_col].max().strftime('%Y-%m-%d') if time_col and not df[time_col].isna().all() else 'N/A'
                ),
                'poa_column': poa_col,
                'columns': df.columns.tolist(),
                'is_multi_array': has_multi_array,
            }
            
            # Multi-array specific metadata
            if has_multi_array:
                # Handle both array_capacity and array_cap column names
                cap_col = cols_lower.get("array_capacity") or cols_lower.get("array_cap")
                az_col = cols_lower["azimuth"]
                tilt_key = "tilt" if "tilt" in cols_lower else "slope"
                slope_col = cols_lower[tilt_key]
                name_col = cols_lower.get("name")
                
                # Build array key
                if name_col:
                    df["_ArrayKey"] = (
                        df[name_col].astype(str).str.strip() + "|" +
                        df[cap_col].astype(str) + "|" +
                        df[az_col].astype(str).str.strip() + "|" +
                        df[slope_col].astype(str).str.strip()
                    )
                else:
                    df["_ArrayKey"] = (
                        df[cap_col].astype(str) + "|" +
                        df[az_col].astype(str).str.strip() + "|" +
                        df[slope_col].astype(str).str.strip()
                    )
                
                # Get unique arrays
                array_info = df.groupby("_ArrayKey").agg({
                    cap_col: "first",
                    az_col: "first",
                    slope_col: "first"
                }).reset_index()
                
                arrays = []
                for _, row in array_info.iterrows():
                    arrays.append({
                        'key': row["_ArrayKey"],
                        'capacity_kw': float(row[cap_col]),
                        'azimuth': row[az_col],
                        'tilt': row[slope_col],
                    })
                
                total_capacity = sum(a['capacity_kw'] for a in arrays)
                metadata['arrays'] = arrays
                metadata['num_arrays'] = len(arrays)
                metadata['total_capacity_kw'] = total_capacity
                
                # Drop temp column
                df = df.drop(columns=["_ArrayKey"])
            
            if poa_col and not df[poa_col].isna().all():
                # Calculate statistics, handling NaN values
                poa_series = df[poa_col].dropna()
                if len(poa_series) > 0:
                    metadata['poa_stats'] = {
                        'mean': float(poa_series.mean()),
                        'max': float(poa_series.max()),
                        'min': float(poa_series.min()),
                    }
            
            # Return preview
            preview_df = df.head(max_rows)
            
            return preview_df, metadata
            
        except Exception as e:
            logger.error(f"Error previewing file {filename}: {e}")
            raise
    
    def show_linkage_preview(
        self, 
        plant_alias: str, 
        filename: str,
        solargis_folder: str
    ) -> Dict[str, Any]:
        """
        Show how POA data will be linked to existing inverters and site data.
        Includes multi-array information when applicable.
        
        Returns:
            Dict with linkage information
        """
        # Get plant record
        plant_rec = self.store.load(plant_alias)
        if not plant_rec:
            raise ValueError(f"Plant alias '{plant_alias}' not found in registry.")
        
        # Preview file data
        preview_df, metadata = self.preview_file_data(solargis_folder, filename, max_rows=3)
        
        # Create POA EMIG ID
        poa_emig_id = f"POA:{plant_alias.replace(' ', '_').upper()}"
        
        linkage = {
            'plant_alias': plant_alias,
            'plant_uid': plant_rec['plant_uid'],
            'poa_emig_id': poa_emig_id,
            'inverter_ids': plant_rec.get('inverter_ids', []),
            'weather_id': plant_rec.get('weather_id'),
            'dc_size_kw': plant_rec.get('dc_size_kw'),
            'file_info': {
                'filename': filename,
                'total_rows': metadata['total_rows'],
                'date_range': metadata['date_range'],
                'poa_column': metadata['poa_column'],
                'is_multi_array': metadata.get('is_multi_array', False),
            },
            'preview_data': preview_df.head(3).to_dict() if not preview_df.empty else {},
            'poa_stats': metadata.get('poa_stats', {}),
        }
        
        # Add multi-array info if present
        if metadata.get('is_multi_array'):
            linkage['file_info']['num_arrays'] = metadata.get('num_arrays', 0)
            linkage['file_info']['total_capacity_kw'] = metadata.get('total_capacity_kw', 0)
            linkage['file_info']['arrays'] = metadata.get('arrays', [])
        
        return linkage
    
    def import_file(
        self,
        plant_alias: str,
        solargis_folder: str,
        filename: str,
        start_date: str = None,
        end_date: str = None
    ) -> int:
        """
        Import a single POA file for a specific plant.
        Imports ALL data from the file (date parameters are ignored).
        
        Supports multiple arrays per site with capacity-weighted consolidation.
        Data is aligned to the configured interval (e.g., 15 minutes) to match inverter data.
        
        Args:
            plant_alias: The plant alias to link the data to
            solargis_folder: Path to folder containing CSV files
            filename: Name of the CSV file to import
            start_date: (Optional, ignored) Start date in YYYYMMDD format
            end_date: (Optional, ignored) End date in YYYYMMDD format
            
        Returns:
            Number of readings imported
        """
        plant_rec = self.store.load(plant_alias)
        if not plant_rec:
            raise ValueError(f"Plant alias '{plant_alias}' not found in registry.")
        
        plant_uid = plant_rec["plant_uid"]
        file_path = os.path.join(solargis_folder, filename)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Load CSV data
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise ValueError(f"Error reading CSV file {file_path}: {e}")
        
        # Map lowercase column names to original for flexible matching
        cols_lower = {c.lower(): c for c in df.columns}
        
        # Check if this is a multi-array file (has array_capacity/array_cap, azimuth, tilt/slope columns)
        has_multi_array = (
            any(k in cols_lower for k in ["array_capacity", "array_cap"]) and 
            "azimuth" in cols_lower and
            any(k in cols_lower for k in ["tilt", "slope"])
        )
        
        if has_multi_array:
            return self._import_multi_array_file(
                df, cols_lower, plant_alias, plant_uid, filename
            )
        else:
            return self._import_single_array_file(
                df, cols_lower, plant_alias, plant_uid, filename
            )
    
    def _import_single_array_file(
        self,
        df: pd.DataFrame,
        cols_lower: Dict[str, str],
        plant_alias: str,
        plant_uid: str,
        filename: str
    ) -> int:
        """Import a simple single-array POA file (legacy format)."""
        
        # Try to find the time column - check multiple possible names
        time_col = None
        for candidate in ["time", "date & time", "timestamp", "datetime", "date"]:
            if candidate in cols_lower:
                time_col = cols_lower[candidate]
                break
        
        if time_col is None:
            raise ValueError(f"Could not find time column in {filename}. Available: {list(df.columns)}")
        
        # Parse timestamps with flexible format (handles various SolarGIS date/time formats)
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce", format="mixed")
        df = df.dropna(subset=[time_col])
        df = df.set_index(time_col)
        
        # Find POA Irradiance column (GTI or POA Irradiance)
        poa_col = None
        for candidate in ["gti", "poa irradiance", "poairradiance", "poa"]:
            if candidate in cols_lower:
                poa_col = cols_lower[candidate]
                break
        
        # Fallback: look for column containing POA and Irradiance
        if poa_col is None:
            poa_col = next(
                (col for col in df.columns if 'POA' in col and 'Irradiance' in col and 'GTI' not in col), 
                None
            )
        
        if not poa_col:
            raise ValueError(f"Could not find POA/GTI column in {filename}. Available: {list(df.columns)}")
        
        # No date filtering - import all data from file
        if df.empty:
            logger.warning(f"No valid data found in {filename}.")
            return 0
        
        # Log the date range found in file
        logger.info(f"Importing POA data from {df.index.min()} to {df.index.max()}")
        
        # Align to configured interval (e.g., 15 minutes)
        interval_minutes = settings.DATA_INTERVAL_MINUTES
        df_aligned = self._align_to_interval(df[[poa_col]], interval_minutes, poa_col)
        
        # Create POA EMIG ID
        poa_emig_id = f"POA:{plant_alias.replace(' ', '_').upper()}"
        
        # Convert to readings format
        readings = []
        for ts, row in df_aligned.iterrows():
            poa_value = row[poa_col]
            
            if pd.isna(poa_value):
                continue
            
            reading = {
                "ts": ts.isoformat() + "Z",
                "emigId": poa_emig_id,
                settings.POA_IRRADIANCE_COL: {"value": float(poa_value), "unit": "W/m2"},
            }
            readings.append(reading)
        
        # Store in database
        self.store.store_readings(plant_uid, poa_emig_id, readings)
        
        logger.info(
            f"Imported {len(readings)} readings for {plant_alias} ({poa_emig_id}). "
            f"POA range: {df_aligned[poa_col].min():.1f} - {df_aligned[poa_col].max():.1f} W/m2"
        )
        
        return len(readings)
    
    def _import_multi_array_file(
        self,
        df: pd.DataFrame,
        cols_lower: Dict[str, str],
        plant_alias: str,
        plant_uid: str,
        filename: str
    ) -> int:
        """
        Import a multi-array POA file with capacity-weighted consolidation.
        
        Arrays are identified by their unique combination of:
        - name (if present)
        - array_capacity or array_cap
        - azimuth
        - tilt/slope
        
        GTI values are weighted by array capacity and consolidated to aligned intervals.
        """
        # Identify required columns
        time_col = None
        for candidate in ["time", "date & time", "timestamp", "datetime", "date"]:
            if candidate in cols_lower:
                time_col = cols_lower[candidate]
                break
        
        if time_col is None:
            raise ValueError(f"Could not find time column in {filename}.")
        
        # GTI column
        gti_col = None
        for candidate in ["gti", "poa irradiance", "poairradiance", "poa"]:
            if candidate in cols_lower:
                gti_col = cols_lower[candidate]
                break
        
        if gti_col is None:
            raise ValueError(f"Could not find GTI/POA column in {filename}.")
        
        # Handle both array_capacity and array_cap column names
        cap_col = cols_lower.get("array_capacity") or cols_lower.get("array_cap")
        az_col = cols_lower["azimuth"]
        tilt_key = "tilt" if "tilt" in cols_lower else "slope"
        slope_col = cols_lower[tilt_key]
        name_col = cols_lower.get("name")
        
        # Parse timestamps with flexible format
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce", format="mixed")
        df = df.dropna(subset=[time_col])
        
        # No date filtering - import all data from file
        if df.empty:
            logger.warning(f"No valid data found in {filename}.")
            return 0
        
        # Log the date range found in file
        logger.info(f"Importing POA data from {df[time_col].min()} to {df[time_col].max()}")
        
        # Build array key to identify unique arrays
        if name_col:
            df["ArrayKey"] = (
                df[name_col].astype(str).str.strip() + "|" +
                df[cap_col].astype(str) + "|" +
                df[az_col].astype(str).str.strip() + "|" +
                df[slope_col].astype(str).str.strip()
            )
        else:
            df["ArrayKey"] = (
                df[cap_col].astype(str) + "|" +
                df[az_col].astype(str).str.strip() + "|" +
                df[slope_col].astype(str).str.strip()
            )
        
        # Get unique arrays and their capacities
        array_capacities = df.groupby("ArrayKey")[cap_col].first().to_dict()
        total_capacity = sum(array_capacities.values())
        num_arrays = len(array_capacities)
        
        logger.info(f"Found {num_arrays} arrays in {filename}:")
        for array_key, capacity in array_capacities.items():
            logger.info(f"  - {array_key}: {capacity} kW ({capacity/total_capacity*100:.1f}%)")
        
        # Remove duplicate readings per array per timestamp
        df["ts_str"] = df[time_col].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_unique = df.drop_duplicates(subset=["ArrayKey", "ts_str"])
        
        # Calculate capacity-weighted GTI for each timestamp
        # weighted_gti = sum(gti_i * capacity_i) / total_capacity
        df_unique["weighted_gti"] = df_unique[gti_col] * df_unique[cap_col]
        
        # Group by timestamp and sum weighted GTI
        weighted_sum = df_unique.groupby(time_col).agg(
            weighted_gti_sum=("weighted_gti", "sum"),
            capacity_sum=(cap_col, "sum")  # Should equal total_capacity for complete timestamps
        ).reset_index()
        
        # Calculate final weighted average GTI
        weighted_sum["weighted_poa"] = weighted_sum["weighted_gti_sum"] / weighted_sum["capacity_sum"]
        
        # Set timestamp as index for alignment
        weighted_sum = weighted_sum.set_index(time_col)
        
        # Align to configured interval (e.g., 15 minutes)
        interval_minutes = settings.DATA_INTERVAL_MINUTES
        df_aligned = self._align_to_interval(
            weighted_sum[["weighted_poa"]], 
            interval_minutes, 
            "weighted_poa"
        )
        
        # Create POA EMIG ID
        poa_emig_id = f"POA:{plant_alias.replace(' ', '_').upper()}"
        
        # Convert to readings format
        readings = []
        for ts, row in df_aligned.iterrows():
            poa_value = row["weighted_poa"]
            
            if pd.isna(poa_value):
                continue
            
            reading = {
                "ts": ts.isoformat() + "Z",
                "emigId": poa_emig_id,
                settings.POA_IRRADIANCE_COL: {"value": float(poa_value), "unit": "W/m2"},
                # Store metadata about the weighting
                "arrayCount": num_arrays,
                "totalCapacityKw": total_capacity,
            }
            readings.append(reading)
        
        # Store in database
        self.store.store_readings(plant_uid, poa_emig_id, readings)
        
        poa_min = df_aligned["weighted_poa"].min()
        poa_max = df_aligned["weighted_poa"].max()
        logger.info(
            f"Imported {len(readings)} weighted POA readings for {plant_alias} ({poa_emig_id}). "
            f"Consolidated from {num_arrays} arrays ({total_capacity:.1f} kW total). "
            f"POA range: {poa_min:.1f} - {poa_max:.1f} W/m2"
        )
        
        return len(readings)
    
    def _align_to_interval(
        self, 
        df: pd.DataFrame, 
        interval_minutes: int,
        value_col: str
    ) -> pd.DataFrame:
        """
        Align data to regular intervals (e.g., 15-minute periods).
        
        Uses mean aggregation for values within each interval period.
        Rounds timestamps down to the nearest interval boundary.
        """
        if df.empty:
            return df
        
        # Round timestamps to interval boundaries
        freq = f"{interval_minutes}min"
        
        # Resample and take mean of values within each interval
        df_resampled = df.resample(freq).mean()
        
        # Drop NaN values (periods with no data)
        df_resampled = df_resampled.dropna(subset=[value_col])
        
        return df_resampled
    
    def bulk_import_with_matches(
        self,
        solargis_folder: str,
        file_to_plant_map: Dict[str, str],
        start_date: str,
        end_date: str
    ) -> Dict[str, int]:
        """
        Bulk import multiple POA files with confirmed matches.
        
        Args:
            solargis_folder: Path to folder containing CSV files
            file_to_plant_map: Dict mapping filename -> plant_alias
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            
        Returns:
            Dict mapping filename -> number of readings imported
        """
        results = {}
        
        for filename, plant_alias in file_to_plant_map.items():
            try:
                count = self.import_file(
                    plant_alias=plant_alias,
                    solargis_folder=solargis_folder,
                    filename=filename,
                    start_date=start_date,
                    end_date=end_date
                )
                results[filename] = count
            except Exception as e:
                logger.error(f"Failed to import {filename}: {e}")
                results[filename] = 0
                
        return results


def format_linkage_preview(linkage: Dict[str, Any]) -> str:
    """Format linkage information as a human-readable string."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"POA DATA LINKAGE PREVIEW")
    lines.append(f"{'='*60}")
    lines.append(f"\nFile: {linkage['file_info']['filename']}")
    lines.append(f"  - Rows: {linkage['file_info']['total_rows']}")
    lines.append(f"  - Date Range: {linkage['file_info']['date_range'][0]} to {linkage['file_info']['date_range'][1]}")
    lines.append(f"  - POA Column: {linkage['file_info']['poa_column']}")
    
    # Multi-array information
    if linkage['file_info'].get('is_multi_array'):
        num_arrays = linkage['file_info'].get('num_arrays', 0)
        total_cap = linkage['file_info'].get('total_capacity_kw', 0)
        lines.append(f"  - Multi-Array: YES ({num_arrays} arrays, {total_cap:.1f} kW total)")
        
        arrays = linkage['file_info'].get('arrays', [])
        if arrays:
            lines.append(f"  - Arrays:")
            for arr in arrays:
                weight_pct = (arr['capacity_kw'] / total_cap * 100) if total_cap > 0 else 0
                lines.append(f"      • {arr['capacity_kw']:.1f} kW @ Az={arr['azimuth']}°, Tilt={arr['tilt']}° ({weight_pct:.1f}% weight)")
        
        lines.append(f"  - Consolidation: Capacity-weighted average POA")
    else:
        lines.append(f"  - Multi-Array: NO (single array)")
    
    if linkage.get('poa_stats'):
        stats = linkage['poa_stats']
        lines.append(f"  - POA Stats: Mean={stats['mean']:.1f}, Max={stats['max']:.1f}, Min={stats['min']:.1f} W/m2")
    
    lines.append(f"\nWill be linked to:")
    lines.append(f"  Plant Alias: {linkage['plant_alias']}")
    lines.append(f"  Plant UID: {linkage['plant_uid']}")
    lines.append(f"  POA Device ID: {linkage['poa_emig_id']}")
    lines.append(f"  DC Size: {linkage['dc_size_kw']} kW" if linkage['dc_size_kw'] else "  DC Size: Not set")
    lines.append(f"\nExisting devices at this site:")
    lines.append(f"  Inverters: {', '.join(linkage['inverter_ids']) if linkage['inverter_ids'] else 'None'}")
    lines.append(f"  Weather Station: {linkage['weather_id'] if linkage['weather_id'] else 'None'}")
    
    lines.append(f"\n{'='*60}\n")
    
    return "\n".join(lines)
