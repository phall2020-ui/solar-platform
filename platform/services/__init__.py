"""Service bridges for unified app."""
from .background_jobs import BackgroundJobManager, Job, JobStatus, get_job_manager, submit_background_job
from .cache_layer import CacheLayer, cached, get_cache_layer
from .incremental_etl import DataQualityReport, DataQualityStatus, IncrementalETL
from .materialized_views import MaterializedViewsManager, views_manager
from .observability import MetricsStore, get_logger, metrics, timed_operation
from .reporting_bridge import ReportingBridge, reporting as reporting_bridge
from .toolkit_bridge import ToolkitBridge, toolkit

# Phase 1 Services
try:
    from .user_preferences import UserPreferences, get_preferences, init_preferences_in_session  # noqa: F401
except ImportError:
    pass

try:
    from .error_handler import AppErrorHandler, get_error_handler  # noqa: F401
except ImportError:
    pass

__all__ = [
    'ToolkitBridge',
    'toolkit',
    'ReportingBridge',
    'reporting_bridge',
    'get_job_manager',
    'submit_background_job',
    'BackgroundJobManager',
    'Job',
    'JobStatus',
    'IncrementalETL',
    'DataQualityReport',
    'DataQualityStatus',
    'get_cache_layer',
    'CacheLayer',
    'cached',
    'metrics',
    'get_logger',
    'timed_operation',
    'MetricsStore',
    'MaterializedViewsManager',
    'views_manager',
]
