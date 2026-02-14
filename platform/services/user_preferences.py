"""
User Preferences Service
Persists user-specific settings across sessions with DuckDB backend.
"""
import json
from datetime import datetime
from typing import Any

import streamlit as st

from services.db_utils import get_connection as _db_get_connection


class UserPreferences:
    """Manage user preferences with persistence."""
    
    # Default preferences
    DEFAULT_PREFS = {
        "default_fiscal_month": 4,  # April
        "favorite_plants": [],
        "recent_plants": [],
        "dashboard_layout": "compact",  # compact, expanded
        "chart_theme": "ampyr",  # ampyr, plotly_dark, plotly_white
        "notifications_enabled": True,
        "default_date_range_days": 90,
        "show_advanced_options": False,
        "auto_refresh_enabled": False,
        "auto_refresh_interval": 300,  # seconds
        "default_page": "Dashboard",
        "sidebar_collapsed": False,
        "show_tooltips": True,
        "data_source_preference": "Both",  # Both, Solar Toolkit Only, Monthly Reporting Only
        "recent_searches": [],
        "saved_filters": {},
        "theme_mode": "light",  # light, dark, auto
        "language": "en",  # en, es, fr, de (future i18n)
        "timezone": "UTC",
        "date_format": "YYYY-MM-DD",
        "number_format": "1,234.56",  # US style
        "currency": "GBP"
    }
    
    def __init__(self, db_path: str, user_id: str = "default"):
        """
        Initialize preferences manager.
        
        Args:
            db_path: Path to DuckDB database
            user_id: User identifier (default for single-user mode)
        """
        self.db_path = db_path
        self.user_id = user_id
        self._init_db()
        self._cache = None
    
    def _get_connection(self):
        """Get a database connection context manager with fallback handling."""
        try:
            # Test that we can connect before returning the context manager
            return _db_get_connection(self.db_path)
        except Exception:
            import os
            import tempfile
            local_prefs_path = os.path.join(tempfile.gettempdir(), "solar_portfolio_prefs.duckdb")
            self.db_path = local_prefs_path
            return _db_get_connection(self.db_path)

    def _init_db(self):
        """Create preferences table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _user_preferences (
                    user_id TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    pref_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, pref_key)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_prefs ON _user_preferences(user_id)")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a preference value.
        
        Args:
            key: Preference key
            default: Default value if not set
            
        Returns:
            Preference value or default
        """
        # Check cache first
        if self._cache is None:
            self._cache = self._load_all()
        
        if key in self._cache:
            return self._cache[key]
        
        # Return default or from DEFAULT_PREFS
        if default is not None:
            return default
        return self.DEFAULT_PREFS.get(key)
    
    def set(self, key: str, value: Any):
        """
        Set a preference value.
        
        Args:
            key: Preference key
            value: Preference value (will be JSON serialized)
        """
        value_json = json.dumps(value)
        timestamp = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO _user_preferences (user_id, pref_key, pref_value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (self.user_id, key, value_json, timestamp))
        
        # Update cache
        if self._cache is None:
            self._cache = {}
        self._cache[key] = value
    
    def delete(self, key: str):
        """Delete a preference."""
        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM _user_preferences
                WHERE user_id = ? AND pref_key = ?
            """, (self.user_id, key))
        
        # Update cache
        if self._cache and key in self._cache:
            del self._cache[key]
    
    def get_all(self) -> dict[str, Any]:
        """Get all preferences for current user."""
        if self._cache is None:
            self._cache = self._load_all()
        
        # Merge with defaults
        all_prefs = self.DEFAULT_PREFS.copy()
        all_prefs.update(self._cache)
        return all_prefs
    
    def _load_all(self) -> dict[str, Any]:
        """Load all preferences from database."""
        with self._get_connection() as conn:
            result = conn.execute("""
                SELECT pref_key, pref_value
                FROM _user_preferences
                WHERE user_id = ?
            """, (self.user_id,)).fetchall()
        
        prefs = {}
        for row in result:
            key, value_json = row
            try:
                prefs[key] = json.loads(value_json)
            except json.JSONDecodeError:
                # Fallback to string value
                prefs[key] = value_json
        
        return prefs
    
    def reset(self):
        """Reset all preferences to defaults."""
        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM _user_preferences WHERE user_id = ?
            """, (self.user_id,))
        self._cache = {}
    
    def export_preferences(self) -> str:
        """Export preferences as JSON string."""
        return json.dumps(self.get_all(), indent=2)
    
    def import_preferences(self, json_str: str):
        """Import preferences from JSON string."""
        prefs = json.loads(json_str)
        for key, value in prefs.items():
            self.set(key, value)
    
    # Convenience methods for common preferences
    
    def add_favorite_plant(self, plant_id: str):
        """Add a plant to favorites."""
        favorites = self.get("favorite_plants", [])
        if plant_id not in favorites:
            favorites.append(plant_id)
            self.set("favorite_plants", favorites)
    
    def remove_favorite_plant(self, plant_id: str):
        """Remove a plant from favorites."""
        favorites = self.get("favorite_plants", [])
        if plant_id in favorites:
            favorites.remove(plant_id)
            self.set("favorite_plants", favorites)
    
    def is_favorite_plant(self, plant_id: str) -> bool:
        """Check if a plant is favorited."""
        favorites = self.get("favorite_plants", [])
        return plant_id in favorites
    
    def add_recent_plant(self, plant_id: str, max_recent: int = 10):
        """Add a plant to recent list."""
        recent = self.get("recent_plants", [])
        
        # Remove if already exists
        if plant_id in recent:
            recent.remove(plant_id)
        
        # Add to front
        recent.insert(0, plant_id)
        
        # Trim to max
        recent = recent[:max_recent]
        
        self.set("recent_plants", recent)
    
    def get_recent_plants(self) -> list[str]:
        """Get list of recently accessed plants."""
        return self.get("recent_plants", [])
    
    def add_recent_search(self, query: str, max_recent: int = 20):
        """Add a search query to recent searches."""
        recent = self.get("recent_searches", [])
        
        # Remove if already exists
        if query in recent:
            recent.remove(query)
        
        # Add to front
        recent.insert(0, query)
        
        # Trim to max
        recent = recent[:max_recent]
        
        self.set("recent_searches", recent)
    
    def get_recent_searches(self) -> list[str]:
        """Get list of recent searches."""
        return self.get("recent_searches", [])
    
    def save_filter(self, name: str, filter_config: dict):
        """Save a named filter configuration."""
        filters = self.get("saved_filters", {})
        filters[name] = filter_config
        self.set("saved_filters", filters)
    
    def get_saved_filters(self) -> dict[str, dict]:
        """Get all saved filters."""
        return self.get("saved_filters", {})
    
    def delete_saved_filter(self, name: str):
        """Delete a saved filter."""
        filters = self.get("saved_filters", {})
        if name in filters:
            del filters[name]
            self.set("saved_filters", filters)


# Session state integration for Streamlit
def init_preferences_in_session(db_path: str, user_id: str = "default"):
    """Initialize preferences in Streamlit session state."""
    if "_user_preferences" not in st.session_state:
        st.session_state._user_preferences = UserPreferences(db_path, user_id)
    return st.session_state._user_preferences


def get_preferences() -> UserPreferences:
    """Get preferences from session state."""
    if "_user_preferences" in st.session_state:
        return st.session_state._user_preferences
    
    # Initialize with default path
    try:
        from unified_config import config
        return init_preferences_in_session(str(config.REPORTING_DB))
    except Exception:
        raise RuntimeError("Preferences not initialized. Call init_preferences_in_session first.")


# Convenience functions for direct access
def get_pref(key: str, default: Any = None) -> Any:
    """Quick access to preference value."""
    try:
        prefs = get_preferences()
        return prefs.get(key, default)
    except Exception:
        return default


def set_pref(key: str, value: Any):
    """Quick access to set preference value."""
    try:
        prefs = get_preferences()
        prefs.set(key, value)
    except Exception:
        pass
