"""
Lightweight SQLite-backed registry for plant metadata and cached readings.

Stores:
  - alias (human-friendly key)
  - plant_uid
  - inverter_ids (JSON array of EMIG IDs)
  - poa_id (POA device ID for irradiance data, stored in 'weather_id' column for compatibility)
  - dc_size_kw (DC nameplate capacity)
"""

import json
import os
import sqlite3
from typing import Dict, List, Optional, Sequence
from datetime import datetime
from solar_toolkit.config import settings

class PlantStore:
    def __init__(self, db_path: str = settings.DB_PATH) -> None:
        self.db_path = db_path
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plants (
                    alias TEXT PRIMARY KEY,
                    plant_uid TEXT NOT NULL,
                    inverter_ids TEXT NOT NULL,
                    weather_id TEXT,
                    dc_size_kw REAL
                )
                """
            )
            # Add dc_size_kw if missing (for backward compatibility)
            try:
                conn.execute("ALTER TABLE plants ADD COLUMN dc_size_kw REAL")
            except Exception:
                pass # Column already exists
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    plant_uid TEXT NOT NULL,
                    emig_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (plant_uid, emig_id, ts)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, alias: str, plant_uid: str, inverter_ids: List[str], weather_id: Optional[str] = None, dc_size_kw: Optional[float] = None) -> None:
        """Saves or updates a plant record."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO plants 
                (alias, plant_uid, inverter_ids, weather_id, dc_size_kw)
                VALUES (?, ?, ?, ?, ?)
                """,
                (alias, plant_uid, json.dumps(inverter_ids), weather_id, dc_size_kw),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, alias: str) -> Optional[Dict]:
        """Loads a single plant record by alias."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT plant_uid, inverter_ids, weather_id, dc_size_kw
                FROM plants
                WHERE alias = ?
                """,
                (alias,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "alias": alias,
                    "plant_uid": row[0],
                    "inverter_ids": json.loads(row[1]),
                    "weather_id": row[2],
                    "dc_size_kw": row[3],
                }
            return None
        finally:
            conn.close()

    def list_all(self) -> List[Dict]:
        """Lists all registered plants."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT alias, plant_uid, inverter_ids, weather_id, dc_size_kw
                FROM plants
                ORDER BY alias
                """
            )
            results = []
            for row in cur.fetchall():
                results.append({
                    "alias": row[0],
                    "plant_uid": row[1],
                    "inverter_ids": json.loads(row[2]),
                    "weather_id": row[3],
                    "dc_size_kw": row[4],
                })
            return results
        finally:
            conn.close()

    def delete_plant(self, alias: str) -> bool:
        """Deletes a plant record by alias. Returns True if deleted, False if not found."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("DELETE FROM plants WHERE alias = ?", (alias,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def store_readings(self, plant_uid: str, emig_id: str, readings: Sequence[Dict]) -> int:
        """Stores a sequence of reading payloads."""
        if not readings:
            return 0
            
        conn = sqlite3.connect(self.db_path)
        try:
            # Prepare data for batch insertion
            data = [
                (plant_uid, emig_id, r["ts"], json.dumps(r))
                for r in readings
            ]
            
            # Use INSERT OR REPLACE to handle duplicates (same key: plant_uid, emig_id, ts)
            conn.executemany(
                """
                INSERT OR REPLACE INTO readings 
                (plant_uid, emig_id, ts, payload) 
                VALUES (?, ?, ?, ?)
                """,
                data,
            )
            conn.commit()
            return len(readings)
        finally:
            conn.close()

    def query_readings(self, plant_uid: str, emig_id: str, start_ts: str, end_ts: str) -> List[Dict]:
        """Queries stored readings for a device within a timestamp range."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT payload FROM readings
                WHERE plant_uid = ? AND emig_id = ? AND ts >= ? AND ts <= ?
                ORDER BY ts
                """,
                (plant_uid, emig_id, start_ts, end_ts),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]
        finally:
            conn.close()
            
    def query_all_readings(self, plant_uid: str, emig_ids: List[str], start_ts: str, end_ts: str) -> List[Dict]:
        """Queries stored readings for a list of devices within a timestamp range."""
        if not emig_ids:
            return []
        
        # Build placeholders safely based on the count of emig_ids
        # This is safe as we're only using the count (int) not the values themselves
        num_placeholders = len(emig_ids)
        placeholders = ','.join(['?'] * num_placeholders)
        query_params = [plant_uid] + emig_ids + [start_ts, end_ts]
        
        conn = sqlite3.connect(self.db_path)
        try:
            # Using parameterized query with placeholders - safe from SQL injection
            cur = conn.execute(
                f"""
                SELECT payload FROM readings
                WHERE plant_uid = ? AND emig_id IN ({placeholders}) AND ts >= ? AND ts <= ?
                ORDER BY ts
                """,
                query_params,
            )
            return [json.loads(row[0]) for row in cur.fetchall()]
        finally:
            conn.close()