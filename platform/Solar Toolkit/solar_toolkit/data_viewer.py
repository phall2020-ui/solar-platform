"""
Data Viewer module for viewing, filtering, editing and deleting database records.

Provides flexible filtering and management of both plants and readings data.
"""

import json
import sqlite3
from typing import Dict, List, Optional, Tuple
import pandas as pd
from solar_toolkit.config import settings


class DataViewer:
    """Manages viewing and editing database contents."""
    
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
    
    # --- PLANTS DATA OPERATIONS ---
    
    def get_plants_data(self) -> pd.DataFrame:
        """Retrieve all plants data as a DataFrame."""
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql_query(
                "SELECT alias, plant_uid, inverter_ids, weather_id, dc_size_kw FROM plants ORDER BY alias",
                conn
            )
            return df
        finally:
            conn.close()
    
    def update_plant(self, alias: str, plant_uid: str, inverter_ids: str, 
                    weather_id: Optional[str], dc_size_kw: Optional[float]) -> None:
        """Update a plant record."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE plants 
                SET plant_uid = ?, inverter_ids = ?, weather_id = ?, dc_size_kw = ?
                WHERE alias = ?
                """,
                (plant_uid, inverter_ids, weather_id, dc_size_kw, alias)
            )
            conn.commit()
        finally:
            conn.close()
    
    def delete_plant(self, alias: str) -> None:
        """Delete a plant record."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM plants WHERE alias = ?", (alias,))
            conn.commit()
        finally:
            conn.close()
    
    # --- READINGS DATA OPERATIONS ---
    
    def get_readings_data(
        self,
        plant_uid: Optional[str] = None,
        emig_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> Tuple[pd.DataFrame, int]:
        """
        Retrieve readings data with flexible filtering.
        
        Args:
            plant_uid: Filter by plant UID (optional)
            emig_id: Filter by device EMIG ID (optional)
            start_date: Filter by start date in YYYY-MM-DD format (optional)
            end_date: Filter by end date in YYYY-MM-DD format (optional)
            limit: Maximum number of rows to return
            
        Returns:
            Tuple of (DataFrame, total_count)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Build query with filters
            # Note: where_clause only contains static SQL operators (AND, =, >=, <)
            # All user input is passed through parameterized queries (?) for safety
            where_clauses = []
            params = []
            
            if plant_uid:
                where_clauses.append("plant_uid = ?")
                params.append(plant_uid)
            
            if emig_id:
                where_clauses.append("emig_id = ?")
                params.append(emig_id)
            
            if start_date:
                where_clauses.append("ts >= ?")
                params.append(start_date)
            
            if end_date:
                # Add one day to include the end date
                where_clauses.append("ts < date(?, '+1 day')")
                params.append(end_date)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count - safe: where_clause contains only static SQL, params are bound
            count_query = f"SELECT COUNT(*) FROM readings WHERE {where_clause}"
            cursor = conn.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Get limited data - safe: where_clause contains only static SQL, params are bound
            query = f"""
                SELECT plant_uid, emig_id, ts, payload 
                FROM readings 
                WHERE {where_clause}
                ORDER BY ts DESC
                LIMIT ?
            """
            params.append(limit)
            
            df = pd.read_sql_query(query, conn, params=params)
            
            # Parse payload JSON to expand columns
            if not df.empty and 'payload' in df.columns:
                df = self._expand_payload_columns(df)
            
            return df, total_count
        finally:
            conn.close()
    
    def _expand_payload_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expand JSON payload column into separate columns."""
        # Parse JSON payloads
        payload_data = []
        for _, row in df.iterrows():
            try:
                payload = json.loads(row['payload'])
                # Flatten nested structures
                flat_payload = {}
                for key, value in payload.items():
                    # Skip duplicate keys that are already in main columns
                    if key in ['ts', 'emigId', 'plant_uid', 'emig_id', 'timestamp']:
                        continue
                    
                    if isinstance(value, dict):
                        # Flatten nested dicts like {"value": 100, "unit": "W"}
                        for sub_key, sub_value in value.items():
                            flat_payload[f"{key}_{sub_key}"] = sub_value
                    else:
                        flat_payload[key] = value
                payload_data.append(flat_payload)
            except (json.JSONDecodeError, TypeError):
                payload_data.append({})
        
        # Create DataFrame from parsed payloads
        if payload_data:
            payload_df = pd.DataFrame(payload_data)
            # Combine with original columns (excluding payload)
            result_df = pd.concat([
                df[['plant_uid', 'emig_id', 'ts']].reset_index(drop=True),
                payload_df.reset_index(drop=True)
            ], axis=1)
            return result_df
        
        return df
    
    def get_unique_plant_uids(self) -> List[str]:
        """Get list of unique plant UIDs from readings."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT DISTINCT plant_uid FROM readings ORDER BY plant_uid")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_unique_device_ids(self, plant_uid: Optional[str] = None) -> List[str]:
        """Get list of unique device EMIG IDs, optionally filtered by plant."""
        conn = sqlite3.connect(self.db_path)
        try:
            if plant_uid:
                cursor = conn.execute(
                    "SELECT DISTINCT emig_id FROM readings WHERE plant_uid = ? ORDER BY emig_id",
                    (plant_uid,)
                )
            else:
                cursor = conn.execute("SELECT DISTINCT emig_id FROM readings ORDER BY emig_id")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_date_range(self, plant_uid: Optional[str] = None, emig_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Get the date range of readings, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Build WHERE clause with parameterized queries for safety
            where_clauses = []
            params = []
            
            if plant_uid:
                where_clauses.append("plant_uid = ?")
                params.append(plant_uid)
            
            if emig_id:
                where_clauses.append("emig_id = ?")
                params.append(emig_id)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Safe: where_clause contains only static SQL, params are bound
            cursor = conn.execute(
                f"SELECT MIN(ts), MAX(ts) FROM readings WHERE {where_clause}",
                params
            )
            result = cursor.fetchone()
            return result if result else (None, None)
        finally:
            conn.close()
    
    def delete_readings(
        self,
        plant_uid: Optional[str] = None,
        emig_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> int:
        """
        Delete readings with flexible filtering.
        
        Returns:
            Number of rows deleted
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Build WHERE clause with parameterized queries for safety
            where_clauses = []
            params = []
            
            if plant_uid:
                where_clauses.append("plant_uid = ?")
                params.append(plant_uid)
            
            if emig_id:
                where_clauses.append("emig_id = ?")
                params.append(emig_id)
            
            if start_date:
                where_clauses.append("ts >= ?")
                params.append(start_date)
            
            if end_date:
                where_clauses.append("ts < date(?, '+1 day')")
                params.append(end_date)
            
            if not where_clauses:
                raise ValueError("At least one filter must be specified for deletion")
            
            where_clause = " AND ".join(where_clauses)
            
            # Safe: where_clause contains only static SQL, params are bound
            cursor = conn.execute(f"DELETE FROM readings WHERE {where_clause}", params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
    
    def get_readings_stats(
        self,
        plant_uid: Optional[str] = None,
        emig_id: Optional[str] = None
    ) -> Dict:
        """Get statistics about readings."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Build WHERE clause with parameterized queries for safety
            where_clauses = []
            params = []
            
            if plant_uid:
                where_clauses.append("plant_uid = ?")
                params.append(plant_uid)
            
            if emig_id:
                where_clauses.append("emig_id = ?")
                params.append(emig_id)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Safe: where_clause contains only static SQL, params are bound
            cursor = conn.execute(
                f"""
                SELECT 
                    COUNT(*) as total_readings,
                    COUNT(DISTINCT plant_uid) as unique_plants,
                    COUNT(DISTINCT emig_id) as unique_devices,
                    MIN(ts) as earliest_reading,
                    MAX(ts) as latest_reading
                FROM readings 
                WHERE {where_clause}
                """,
                params
            )
            result = cursor.fetchone()
            
            return {
                'total_readings': result[0],
                'unique_plants': result[1],
                'unique_devices': result[2],
                'earliest_reading': result[3],
                'latest_reading': result[4]
            }
        finally:
            conn.close()
