"""
Bridge service to Monthly Reporting functionality.
Provides a clean interface to access Monthly Reporting features without modifying the original code.
"""
import logging
import sys

import pandas as pd

logger = logging.getLogger(__name__)

# Observability
from solar_platform.db.utils import get_connection as _db_get_connection
from solar_platform.services.observability import get_logger

# Lazy import to avoid circular dependency (unified_config → services → reporting_bridge → unified_config)
_config = None

def _get_config():
    global _config
    if _config is None:
        from solar_platform.config import config as _cfg
        _config = _cfg
    return _config

def _ensure_reporting_path():
    """Add Monthly Reporting to sys.path lazily."""
    cfg = _get_config()
    path_str = str(cfg.MONTHLY_REPORTING_PATH)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# Deferred Monthly Reporting imports
REPORTING_AVAILABLE = None  # None = not yet checked
_reporting_modules = {}

def _ensure_reporting_modules():
    """Lazily import Monthly Reporting modules."""
    global REPORTING_AVAILABLE, _reporting_modules
    if REPORTING_AVAILABLE is not None:
        return REPORTING_AVAILABLE
    _ensure_reporting_path()
    try:
        from analysis import aggregate_flexible, plot_waterfall
        from data_access import SolarDataExtractor
        from ui_excom_report import (
            calculate_kpis,
            calculate_waterfall_components,
            create_excom_waterfall,
        )
        _reporting_modules.update({
            'aggregate_flexible': aggregate_flexible,
            'plot_waterfall': plot_waterfall,
            'SolarDataExtractor': SolarDataExtractor,
            'calculate_kpis': calculate_kpis,
            'calculate_waterfall_components': calculate_waterfall_components,
            'create_excom_waterfall': create_excom_waterfall,
        })
        REPORTING_AVAILABLE = True
    except ImportError as e:
        logger.warning("Monthly Reporting modules unavailable: %s", e)
        REPORTING_AVAILABLE = False
    return REPORTING_AVAILABLE

# Import cache layer
try:
    from services.cache_layer import get_cache_layer
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


class ReportingBridge:
    """Bridge to Monthly Reporting functionality."""
    
    def __init__(self, db_path: str | None = None, use_cache: bool = True):
        """
        Initialize the bridge.
        
        Args:
            db_path: Path to reporting database. If None, uses unified DuckDB database.
            use_cache: Whether to use caching for expensive operations
        """
        # Use the unified DuckDB database
        if db_path is None:
            from solar_platform.config import get_settings
            self.db_path = str(get_settings().db_path)
        else:
            self.db_path = db_path
        self.extractor = None
        self.use_cache = use_cache and CACHE_AVAILABLE
        self.logger = get_logger()
        
        # Initialize materialized views manager if feature enabled
        self.views_manager = None
        cfg = _get_config()
        if cfg.use_cached_views:
            try:
                from services.materialized_views import MaterializedViewsManager
                self.views_manager = MaterializedViewsManager(self.db_path)
                self.logger.info("materialized_views_enabled")
            except Exception as e:
                self.logger.warning("materialized_views_init_failed", error=str(e))
        
        if self.use_cache:
            # Use memory cache to avoid DuckDB lock conflicts with synced database
            self.cache = get_cache_layer(backend="memory", default_ttl=300)
        
        _ensure_reporting_modules()
        if REPORTING_AVAILABLE:
            try:
                self.extractor = _reporting_modules['SolarDataExtractor'](self.db_path)
            except Exception:
                # Legacy SQLite extractor won't work with DuckDB - this is expected
                pass
        logger.info("ReportingBridge initialized, db=%s, cache=%s", self.db_path, self.use_cache)
    
    def _get_connection(self, read_only=True):
        """Get a DuckDB connection context manager."""
        return _db_get_connection(self.db_path, read_only=read_only)
    
    def is_available(self) -> bool:
        """Check if Monthly Reporting functionality is available."""
        # Now available if we can connect to the database
        try:
            with self._get_connection() as conn:
                result = conn.execute("SELECT 1").fetchone()
                return result is not None
        except Exception:
            return False
    
    # --- Database Operations ---
    
    def get_tables(self) -> list[str]:
        """Get list of available tables in the database."""
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
                ).fetchall()
                return [r[0] for r in result]
        except Exception as e:
            self.logger.error("get_tables_failed", error=str(e))
            return []
    
    def get_raw_data(self, table_name: str = "solar_data") -> pd.DataFrame | None:
        """
        Get raw data from the database for analysis.
        
        Args:
            table_name: Name of table to query (default: solar_data)
            
        Returns:
            DataFrame with raw data or None if error
        """
        try:
            with self._get_connection() as conn:
                df = conn.execute(f"SELECT * FROM {table_name}").fetchdf()
                return df
        except Exception as e:
            self.logger.error("get_raw_data_failed", error=str(e))
            return None
    
    def query_data(self, query: str) -> tuple[bool, pd.DataFrame | None]:
        """Execute a SQL query and return results."""
        try:
            with self._get_connection() as conn:
                df = conn.execute(query).fetchdf()
                return True, df
        except Exception as e:
            self.logger.error("query_data_failed", error=str(e))
            return False, None
    
    def get_table_data(self, table_name: str, limit: int | None = None) -> pd.DataFrame | None:
        """Get all data from a table."""
        try:
            with self._get_connection() as conn:
                query = f"SELECT * FROM {table_name}"
                if limit:
                    query += f" LIMIT {limit}"
                df = conn.execute(query).fetchdf()
                return df
        except Exception as e:
            self.logger.error("get_table_data_failed", error=str(e))
            return None

    def save_table_data(self, table_name: str, df: pd.DataFrame, if_exists: str = 'replace') -> bool:
        """
        Save dataframe to database table.
        
        Args:
            table_name: Name of table to save to
            df: Dataframe to save
            if_exists: What to do if table exists ('fail', 'replace', 'append')
            
        Returns:
            bool: True if successful
        """
        try:
            with self._get_connection(read_only=False) as conn:
                if if_exists == 'replace':
                    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
                elif if_exists == 'append':
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM df")
                else:
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
            return True
        except Exception as e:
            logger.error("save_table_data failed for table=%s: %s", table_name, e)
            return False

    def get_last_updated(self, table_name: str, candidate_cols: list[str] | None = None) -> str | None:
        """
        Return ISO date string of most recent timestamp in a table.
        """
        if not self.extractor:
            return None
        columns = self._get_table_columns(table_name)
        if not columns:
            return None
        candidate_cols = candidate_cols or ["Date", "date", "timestamp", "Timestamp"]
        col = next((c for c in candidate_cols if c in columns), None)
        if not col:
            return None
        query = f'SELECT MAX("{col}") AS max_ts FROM {table_name}'
        success, df = self.extractor.query_data(query)
        if success and df is not None and not df.empty:
            return str(df.iloc[0]["max_ts"])
        return None
    
    # --- Portfolio Summary ---
    
    def get_portfolio_summary(self, table_name: str, colmap: dict[str, str]) -> dict:
        """
        Get portfolio-wide summary statistics.
        
        Args:
            table_name: Name of the source table
            colmap: Column mapping dictionary
            
        Returns:
            Dictionary with portfolio metrics
        """
        if not self.extractor:
            return {}

        # Try cache first if enabled
        if self.use_cache:
            cache_key = self.cache._make_key("portfolio_summary", table_name, tuple(sorted(colmap.items())))
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        columns = self._get_table_columns(table_name)
        if not columns:
            return {}

        # Only use columns that actually exist to avoid SQL errors
        mapped_cols = {k: v for k, v in colmap.items() if v in columns}
        if not mapped_cols:
            return {}

        def q(col_name: str) -> str:
            """Quote column names safely for DuckDB."""
            return f'"{col_name}"'

        select_parts = []
        if 'Site' in mapped_cols:
            select_parts.append(f"COUNT(DISTINCT {q(mapped_cols['Site'])}) AS total_sites")
        if 'Gen_Budget_kWh' in mapped_cols:
            select_parts.append(f"SUM({q(mapped_cols['Gen_Budget_kWh'])}) AS total_budget_kwh")
        if 'Gen_Actual_kWh' in mapped_cols:
            select_parts.append(f"SUM({q(mapped_cols['Gen_Actual_kWh'])}) AS total_actual_kwh")
        if 'PR' in mapped_cols:
            select_parts.append(f"AVG({q(mapped_cols['PR'])}) AS avg_pr")
        if 'Availability' in mapped_cols:
            select_parts.append(f"AVG({q(mapped_cols['Availability'])}) AS avg_availability")

        if not select_parts:
            return {}

        query = f"SELECT {', '.join(select_parts)} FROM {table_name}"
        success, df = self.extractor.query_data(query)
        if not success or df is None or df.empty:
            return {}

        row = df.iloc[0]
        summary = {
            "total_sites": int(row.get('total_sites', 0) or 0),
            "total_budget_kwh": float(row.get('total_budget_kwh', 0) or 0),
            "total_actual_kwh": float(row.get('total_actual_kwh', 0) or 0),
            "avg_pr": float(row.get('avg_pr', 0) or 0),
            "avg_availability": float(row.get('avg_availability', 0) or 0),
        }

        if summary["total_budget_kwh"] > 0 and 'total_actual_kwh' in summary:
            summary['variance_kwh'] = summary['total_actual_kwh'] - summary['total_budget_kwh']
            summary['variance_pct'] = summary['variance_kwh'] / summary['total_budget_kwh'] * 100
        else:
            summary['variance_kwh'] = 0
            summary['variance_pct'] = 0

        # Cache the result
        if self.use_cache:
            self.cache.set(cache_key, summary)
        
        return summary

    def _get_table_columns(self, table_name: str) -> set:
        """Return the set of column names for a table."""
        # Validate table_name against actual tables in the database
        allowed_tables = self.get_tables()
        if table_name not in allowed_tables:
            self.logger.warning("_get_table_columns rejected invalid table name: %s", table_name)
            return set()

        try:
            success, df = self.extractor.query_data(
                f"SELECT column_name AS name FROM information_schema.columns WHERE table_name = '{table_name}'"
            )
            if success and df is not None:
                return set(df['name'].tolist())
        except Exception:
            return set()
        return set()
    
    # --- ExCom Report ---
    
    def generate_excom_report(
        self,
        df: pd.DataFrame,
        colmap: dict[str, str],
        period_label: str = "Month"
    ) -> tuple[dict, dict, object | None]:
        """
        Generate ExCom-style waterfall report.
        
        Args:
            df: Source dataframe
            colmap: Column mapping
            period_label: Label for the time period
            
        Returns:
            Tuple of (waterfall_data, kpis, figure)
        """
        _ensure_reporting_modules()
        if not REPORTING_AVAILABLE:
            logger.warning("generate_excom_report called but reporting modules unavailable")
            return {}, {}, None
        
        # Apply column mapping
        df = df.rename(columns={v: k for k, v in colmap.items()})
        
        # Calculate waterfall components
        waterfall_data = _reporting_modules['calculate_waterfall_components'](df)
        
        # Calculate KPIs
        kpis = _reporting_modules['calculate_kpis'](df)
        
        # Create waterfall chart
        fig = _reporting_modules['create_excom_waterfall'](waterfall_data, period_label)
        
        return waterfall_data, kpis, fig
    
    def get_waterfall_components(self, df: pd.DataFrame, colmap: dict[str, str]) -> dict:
        """
        Calculate waterfall components from dataframe.
        
        Args:
            df: Source dataframe
            colmap: Column mapping
            
        Returns:
            Dictionary of waterfall components
        """
        _ensure_reporting_modules()
        if not REPORTING_AVAILABLE:
            return {}
            
        # Apply column mapping
        df = df.rename(columns={v: k for k, v in colmap.items()})
        
        return _reporting_modules['calculate_waterfall_components'](df)
    
    # --- Flexible Waterfall ---
    
    def create_waterfall_chart(
        self,
        df: pd.DataFrame,
        colmap: dict[str, str],
        time_agg: str = "Monthly",
        group_by: str | None = None
    ) -> tuple[pd.DataFrame, object | None]:
        """
        Create flexible waterfall chart with aggregation.
        
        Args:
            df: Source dataframe
            colmap: Column mapping
            time_agg: Time aggregation (Daily, Weekly, Monthly, etc.)
            group_by: Optional grouping dimension (Site, Type, etc.)
            
        Returns:
            Tuple of (aggregated_data, figure)
        """
        _ensure_reporting_modules()
        if not REPORTING_AVAILABLE:
            return pd.DataFrame(), None
        
        # Apply column mapping
        df = df.rename(columns={v: k for k, v in colmap.items()})
        
        # Aggregate data
        agg_df = _reporting_modules['aggregate_flexible'](df, time_agg, group_by)
        
        # Create waterfall chart
        fig = _reporting_modules['plot_waterfall'](agg_df, time_agg, group_by)
        
        return agg_df, fig
    
    # --- Site Analysis ---
    
    def get_site_performance(
        self,
        df: pd.DataFrame,
        colmap: dict[str, str],
        site_name: str
    ) -> dict:
        """Get performance metrics for a specific site."""
        # Apply column mapping
        df = df.rename(columns={v: k for k, v in colmap.items()})
        
        site_df = df[df['Site'] == site_name] if 'Site' in df.columns else df
        
        if site_df.empty:
            return {}
        
        metrics = {
            "site_name": site_name,
            "total_budget_kwh": site_df['Gen_Budget_kWh'].sum() if 'Gen_Budget_kWh' in site_df.columns else 0,
            "total_actual_kwh": site_df['Gen_Actual_kWh'].sum() if 'Gen_Actual_kWh' in site_df.columns else 0,
            "avg_pr": site_df['PR'].mean() if 'PR' in site_df.columns else 0,
            "avg_availability": site_df['Availability'].mean() if 'Availability' in site_df.columns else 0,
            "total_tech_loss_kwh": site_df['Loss_Total_Tech_kWh'].sum() if 'Loss_Total_Tech_kWh' in site_df.columns else 0,
        }
        
        return metrics
    
    # --- Top/Bottom Performers ---
    
    def get_top_bottom_sites(
        self,
        df: pd.DataFrame,
        colmap: dict[str, str],
        metric: str = "PR",
        n: int = 5
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get top and bottom performing sites.
        
        Args:
            df: Source dataframe
            colmap: Column mapping
            metric: Metric to rank by (PR, Availability, etc.)
            n: Number of sites to return
            
        Returns:
            Tuple of (top_sites, bottom_sites) DataFrames
        """
        # Apply column mapping
        df = df.rename(columns={v: k for k, v in colmap.items()})
        
        if 'Site' not in df.columns or metric not in df.columns:
            return pd.DataFrame(), pd.DataFrame()
        
        # Aggregate by site
        site_metrics = df.groupby('Site')[metric].mean().reset_index()
        site_metrics = site_metrics.sort_values(by=metric, ascending=False)
        
        top_sites = site_metrics.head(n)
        bottom_sites = site_metrics.tail(n)
        
        return top_sites, bottom_sites


# Lazy singleton — instantiated on first access to avoid circular import
_reporting_instance = None

def _get_reporting():
    global _reporting_instance
    if _reporting_instance is None:
        _reporting_instance = ReportingBridge()
    return _reporting_instance

class _LazyReporting:
    """Proxy that defers ReportingBridge() creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(_get_reporting(), name)
    def __bool__(self):
        return True

reporting = _LazyReporting()
