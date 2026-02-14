"""
Materialized Views Manager.
Creates and refreshes precomputed aggregates for common dashboard queries.

DuckDB supports this pattern well with fast analytical queries.
We implement materialized views as regular tables that get refreshed on demand.
"""
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from services.db_utils import get_connection as _db_get_connection
from services.observability import get_logger, metrics, timed_operation

# Lazy config import
_config = None

def _get_config():
    global _config
    if _config is None:
        from unified_config import config
        _config = config
    return _config

class MaterializedViewsManager:
    """Manages DuckDB-based materialized views.
    
    Stores aggregate data in prefixed tables (mv_*) and tracks
    refresh timestamps in a metadata table.
    """
    
    # View definitions: each maps view name to a SELECT query
    # These queries run against the source tables and results are stored
    VIEW_DEFINITIONS: dict[str, str] = {
        "mv_site_month_summary": """
            SELECT 
                Site,
                Date,
                AVG(CAST(REPLACE("PR (%)", '%', '') AS REAL)) as avg_pr,
                AVG(CAST(REPLACE("Availability (%)", '%', '') AS REAL)) as avg_availability,
                SUM(CAST("Actual Gen (kWh)" AS REAL)) as total_actual_kwh,
                SUM(CAST("Forecast Gen (kWh)" AS REAL)) as total_forecast_kwh,
                SUM(CAST("Calculated Exp (kWh)" AS REAL)) as total_expected_kwh,
                COUNT(*) as record_count
            FROM solar_data
            WHERE Site IS NOT NULL AND Date IS NOT NULL
            GROUP BY Site, Date
        """,
        
        "mv_loss_breakdown": """
            SELECT
                Site,
                Date,
                SUM(CAST("Loss_Grid_kWh" AS REAL)) as grid_loss,
                SUM(CAST("Loss_Availability_kWh" AS REAL)) as availability_loss,
                SUM(CAST("Loss_Inverter_kWh" AS REAL)) as inverter_loss,
                SUM(CAST("Loss_Weather_kWh" AS REAL)) as weather_loss,
                SUM(CAST("Loss_Total_Tech_kWh" AS REAL)) as total_tech_loss
            FROM solar_data
            WHERE Site IS NOT NULL AND Date IS NOT NULL
            GROUP BY Site, Date
        """,
        
        "mv_portfolio_kpis": """
            SELECT
                Date,
                COUNT(DISTINCT Site) as site_count,
                AVG(CAST(REPLACE("PR (%)", '%', '') AS REAL)) as portfolio_pr,
                AVG(CAST(REPLACE("Availability (%)", '%', '') AS REAL)) as portfolio_availability,
                SUM(CAST("Actual Gen (kWh)" AS REAL)) as portfolio_generation,
                SUM(CAST("Forecast Gen (kWh)" AS REAL)) as portfolio_forecast
            FROM solar_data
            WHERE Date IS NOT NULL
            GROUP BY Date
            ORDER BY Date DESC
        """
    }
    
    METADATA_TABLE = "_mv_metadata"
    
    def __init__(self, db_path: str | None = None):
        """Initialize the manager.
        
        Args:
            db_path: Path to the reporting database. Uses config default if None.
        """
        config = _get_config()
        self.db_path = db_path or str(config.REPORTING_DB)
        self.logger = get_logger()
        self._ensure_metadata_table()
    
    def _get_connection(self):
        """Get a database connection context manager."""
        return _db_get_connection(self.db_path)
    
    def _ensure_metadata_table(self) -> None:
        """Create metadata table if it doesn't exist."""
        try:
            with self._get_connection() as conn:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.METADATA_TABLE} (
                        view_name TEXT PRIMARY KEY,
                        last_refresh TEXT,
                        row_count INTEGER,
                        refresh_duration_ms REAL,
                        status TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            self.logger.warning("metadata_table_creation_failed", error=str(e))
    
    @timed_operation("refresh_all_views")
    def refresh_all(self) -> dict[str, bool]:
        """Refresh all materialized views.
        
        Returns:
            Dictionary mapping view names to success status.
        """
        results = {}
        for view_name in self.VIEW_DEFINITIONS:
            results[view_name] = self.refresh_view(view_name)
        return results
    
    @timed_operation("refresh_view")
    def refresh_view(self, view_name: str) -> bool:
        """Refresh a specific materialized view.
        
        Args:
            view_name: Name of the view to refresh.
            
        Returns:
            True if refresh succeeded, False otherwise.
        """
        if view_name not in self.VIEW_DEFINITIONS:
            self.logger.error("unknown_view", view_name=view_name)
            return False
        
        query = self.VIEW_DEFINITIONS[view_name]
        start_time = datetime.now(UTC)
        
        try:
            with self._get_connection() as conn:
                # Check if source table exists
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'solar_data'"
                )
                if cursor.fetchone()[0] == 0:
                    self.logger.warning("source_table_missing", view=view_name)
                    self._update_metadata(view_name, 0, 0, "source_missing")
                    return False
                
                # Execute the aggregation query
                df = pd.read_sql_query(query, conn)
                
                if df.empty:
                    self.logger.info("empty_result", view=view_name)
                    self._update_metadata(view_name, 0, 0, "empty")
                    return True
                
                # Drop existing view table and recreate
                conn.execute(f"DROP TABLE IF EXISTS {view_name}")
                
                # Write new data
                df.to_sql(view_name, conn, index=False, if_exists="replace")
                
                # Update metadata
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                self._update_metadata(view_name, len(df), duration_ms, "success")
                
                self.logger.info(
                    "view_refreshed",
                    view=view_name,
                    rows=len(df),
                    duration_ms=round(duration_ms, 2)
                )
                return True
                
        except Exception as e:
            self.logger.error("view_refresh_failed", view=view_name, error=str(e))
            metrics.record_error("view_refresh", str(e), {"view": view_name})
            self._update_metadata(view_name, 0, 0, f"error: {str(e)[:100]}")
            return False
    
    def _update_metadata(
        self, 
        view_name: str, 
        row_count: int, 
        duration_ms: float, 
        status: str
    ) -> None:
        """Update metadata for a view."""
        try:
            with self._get_connection() as conn:
                conn.execute(f"""
                    INSERT OR REPLACE INTO {self.METADATA_TABLE}
                    (view_name, last_refresh, row_count, refresh_duration_ms, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    view_name,
                    datetime.now(UTC).isoformat(),
                    row_count,
                    duration_ms,
                    status
                ))
                conn.commit()
        except Exception as e:
            self.logger.warning("metadata_update_failed", view=view_name, error=str(e))
    
    def get_last_refresh(self, view_name: str) -> datetime | None:
        """Get timestamp of last refresh for a view.
        
        Args:
            view_name: Name of the view.
            
        Returns:
            DateTime of last refresh, or None if never refreshed.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(f"""
                    SELECT last_refresh FROM {self.METADATA_TABLE}
                    WHERE view_name = ?
                """, (view_name,))
                row = cursor.fetchone()
                if row and row[0]:
                    return datetime.fromisoformat(row[0])
        except Exception:
            pass
        return None
    
    def get_view_status(self, view_name: str) -> dict[str, Any]:
        """Get full status info for a view.
        
        Returns:
            Dictionary with last_refresh, row_count, duration_ms, status.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(f"""
                    SELECT last_refresh, row_count, refresh_duration_ms, status
                    FROM {self.METADATA_TABLE}
                    WHERE view_name = ?
                """, (view_name,))
                row = cursor.fetchone()
                if row:
                    return {
                        "last_refresh": row[0],
                        "row_count": row[1],
                        "refresh_duration_ms": row[2],
                        "status": row[3]
                    }
        except Exception:
            pass
        return {"last_refresh": None, "row_count": 0, "status": "unknown"}
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all views."""
        return {
            view_name: self.get_view_status(view_name)
            for view_name in self.VIEW_DEFINITIONS
        }
    
    @timed_operation("query_view")
    def query_view(
        self, 
        view_name: str, 
        filters: dict[str, Any] | None = None,
        limit: int | None = None
    ) -> pd.DataFrame:
        """Query a materialized view with optional filters.
        
        Args:
            view_name: Name of the view to query.
            filters: Optional dict of {column: value} filters.
            limit: Optional row limit.
            
        Returns:
            DataFrame with query results, or empty DataFrame on error.
        """
        try:
            with self._get_connection() as conn:
                # Check if view exists
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                    (view_name,)
                )
                if cursor.fetchone()[0] == 0:
                    self.logger.warning("view_not_found", view=view_name)
                    metrics.record_cache_miss("materialized_view")
                    return pd.DataFrame()
                
                # Build query
                query = f"SELECT * FROM {view_name}"
                params: list[Any] = []
                
                if filters:
                    conditions = []
                    for col, val in filters.items():
                        conditions.append(f'"{col}" = ?')
                        params.append(val)
                    query += " WHERE " + " AND ".join(conditions)
                
                if limit:
                    query += f" LIMIT {int(limit)}"
                
                df = pd.read_sql_query(query, conn, params=params if params else None)
                metrics.record_cache_hit("materialized_view")
                return df
                
        except Exception as e:
            self.logger.error("view_query_failed", view=view_name, error=str(e))
            metrics.record_cache_miss("materialized_view")
            return pd.DataFrame()
    
    def is_view_stale(self, view_name: str, max_age_seconds: int = 3600) -> bool:
        """Check if a view is stale (older than max_age_seconds).
        
        Args:
            view_name: Name of the view.
            max_age_seconds: Maximum age in seconds before considered stale.
            
        Returns:
            True if stale or never refreshed, False if fresh.
        """
        last_refresh = self.get_last_refresh(view_name)
        if not last_refresh:
            return True
        
        age = (datetime.now(UTC) - last_refresh).total_seconds()
        return age > max_age_seconds


# Singleton instance — lazy to avoid circular import at module load
_views_manager = None


def get_views_manager() -> MaterializedViewsManager:
    """Get or create the singleton MaterializedViewsManager."""
    global _views_manager
    if _views_manager is None:
        _views_manager = MaterializedViewsManager()
    return _views_manager


# Backwards-compatibility alias (lazy proxy)
class _LazyViewsManager:
    """Proxy that defers construction until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_views_manager(), name)

views_manager = _LazyViewsManager()
