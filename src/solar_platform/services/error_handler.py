"""
Centralized Error Handling System
Provides user-friendly error messages, recovery suggestions, and error tracking.
"""
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from solar_platform.db.utils import get_connection

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Context information for error tracking."""
    error_type: str
    severity: ErrorSeverity
    user_message: str
    technical_message: str
    recovery_actions: list[str]
    timestamp: str
    context: dict[str, Any]
    traceback: str | None = None


class AppErrorHandler:
    """Centralized error handling with user-friendly messages and recovery options."""
    
    # Error catalog with user-friendly messages and recovery actions
    ERROR_CATALOG = {
        "DB_CONNECTION_FAILED": {
            "user_message": "Unable to connect to the database",
            "recovery": [
                "Check that the database file exists",
                "Verify database path in configuration",
                "Ensure you have read/write permissions"
            ],
            "severity": ErrorSeverity.CRITICAL
        },
        "DB_QUERY_FAILED": {
            "user_message": "Database query failed",
            "recovery": [
                "Try refreshing the page",
                "Check if the table exists",
                "Contact support if problem persists"
            ],
            "severity": ErrorSeverity.ERROR
        },
        "API_TIMEOUT": {
            "user_message": "External API request timed out",
            "recovery": [
                "Check your internet connection",
                "Verify API key is correct",
                "Try again in a few minutes"
            ],
            "severity": ErrorSeverity.WARNING
        },
        "API_KEY_INVALID": {
            "user_message": "API key is invalid or missing",
            "recovery": [
                "Check API key in environment variables",
                "Verify key hasn't expired",
                "Generate a new API key if needed"
            ],
            "severity": ErrorSeverity.ERROR
        },
        "FILE_NOT_FOUND": {
            "user_message": "Required file not found",
            "recovery": [
                "Check the file path",
                "Ensure the file hasn't been moved or deleted",
                "Re-upload the file if necessary"
            ],
            "severity": ErrorSeverity.ERROR
        },
        "INVALID_DATA_FORMAT": {
            "user_message": "Data format is invalid",
            "recovery": [
                "Check that your file has the required columns",
                "Ensure dates are in YYYY-MM-DD format",
                "Review the data validation report"
            ],
            "severity": ErrorSeverity.WARNING
        },
        "VALIDATION_FAILED": {
            "user_message": "Data validation failed",
            "recovery": [
                "Review the validation report for details",
                "Fix data quality issues in source file",
                "Disable 'block on failure' to load anyway"
            ],
            "severity": ErrorSeverity.WARNING
        },
        "PLANT_NOT_FOUND": {
            "user_message": "Plant not found in database",
            "recovery": [
                "Check plant ID is correct",
                "Register the plant first",
                "Refresh the plant list"
            ],
            "severity": ErrorSeverity.WARNING
        },
        "INSUFFICIENT_DATA": {
            "user_message": "Insufficient data for analysis",
            "recovery": [
                "Fetch more historical data",
                "Adjust the date range",
                "Check data completeness"
            ],
            "severity": ErrorSeverity.WARNING
        },
        "CALCULATION_ERROR": {
            "user_message": "Calculation or analysis failed",
            "recovery": [
                "Check input parameters",
                "Ensure data quality is sufficient",
                "Try with different date range"
            ],
            "severity": ErrorSeverity.ERROR
        },
        "UNKNOWN_ERROR": {
            "user_message": "An unexpected error occurred",
            "recovery": [
                "Try refreshing the page",
                "Clear browser cache",
                "Contact support with error details"
            ],
            "severity": ErrorSeverity.ERROR
        }
    }
    
    def __init__(self, db_path: str | None = None) -> None:
        """Initialize error handler with optional error logging database."""
        self.db_path = db_path
        if db_path:
            self._init_error_log_db()
    
    def _init_error_log_db(self) -> None:
        """Create error log table if it doesn't exist."""
        try:
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS _error_log (
                        id INTEGER PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        error_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        user_message TEXT,
                        technical_message TEXT,
                        context TEXT,
                        traceback TEXT,
                        resolved INTEGER DEFAULT 0
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_error_timestamp ON _error_log(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_error_type ON _error_log(error_type)")
                conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_error_log_id START 1")
        except Exception as e:
            print(f"Warning: Could not initialize error log database: {e}")
    
    def handle_error(
        self,
        error_type: str,
        exception: Exception | None = None,
        context: dict[str, Any] | None = None,
        show_traceback: bool = False
    ) -> ErrorContext:
        """
        Handle an error with user-friendly display and logging.
        
        Args:
            error_type: Error type from ERROR_CATALOG
            exception: The caught exception (if any)
            context: Additional context information
            show_traceback: Whether to show technical traceback
            
        Returns:
            ErrorContext with error details
        """
        # Get error info from catalog or use defaults
        error_info = self.ERROR_CATALOG.get(
            error_type,
            self.ERROR_CATALOG["UNKNOWN_ERROR"]
        )
        
        # Build error context
        error_ctx = ErrorContext(
            error_type=error_type,
            severity=error_info["severity"],
            user_message=error_info["user_message"],
            technical_message=str(exception) if exception else "No exception details",
            recovery_actions=error_info["recovery"],
            timestamp=datetime.now().isoformat(),
            context=context or {},
            traceback=traceback.format_exc() if exception else None
        )
        
        # Display to user
        self._display_error(error_ctx, show_traceback)
        
        # Log error
        self._log_error(error_ctx)
        
        # Track in observability if available
        try:
            from solar_platform.services.observability import metrics
            metrics.record_error(error_type, error_ctx.technical_message, error_ctx.context)
        except Exception:
            pass
        
        return error_ctx
    
    def _display_error(self, error_ctx: ErrorContext, show_traceback: bool = False) -> None:
        """Log error using stdlib logging (framework-agnostic)."""
        log_func = {
            ErrorSeverity.INFO: logger.info,
            ErrorSeverity.WARNING: logger.warning,
            ErrorSeverity.ERROR: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }.get(error_ctx.severity, logger.warning)

        log_func("%s", error_ctx.user_message)

        # Log recovery actions
        if error_ctx.recovery_actions:
            for action in error_ctx.recovery_actions:
                logger.info("  Recovery: %s", action)

        # Log technical details if requested
        if show_traceback and error_ctx.traceback:
            logger.debug("Traceback:\n%s", error_ctx.traceback)
            if error_ctx.context:
                logger.debug("Context: %s", error_ctx.context)
    
    def _log_error(self, error_ctx: ErrorContext) -> None:
        """Log error to database."""
        if not self.db_path:
            return
        
        try:
            import json
            with get_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO _error_log 
                    (id, timestamp, error_type, severity, user_message, technical_message, context, traceback)
                    VALUES (nextval('seq_error_log_id'), ?, ?, ?, ?, ?, ?, ?)
                """, (
                    error_ctx.timestamp,
                    error_ctx.error_type,
                    error_ctx.severity.value,
                    error_ctx.user_message,
                    error_ctx.technical_message,
                    json.dumps(error_ctx.context),
                    error_ctx.traceback
                ))
        except Exception as e:
            print(f"Warning: Could not log error to database: {e}")
    
    def get_recent_errors(self, limit: int = 50) -> list[dict[str, str]]:
        """Get recent errors from log."""
        if not self.db_path:
            return []
        
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                result = conn.execute("""
                    SELECT timestamp, error_type, severity, user_message, technical_message
                    FROM _error_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                
                errors = []
                for row in result:
                    errors.append({
                        "timestamp": row[0],
                        "error_type": row[1],
                        "severity": row[2],
                        "user_message": row[3],
                        "technical_message": row[4]
                    })
                
                return errors
        except Exception as e:
            print(f"Warning: Could not fetch error log: {e}")
            return []
    
    def get_error_summary(self) -> dict[str, Any]:
        """Get error statistics summary."""
        if not self.db_path:
            return {}
        
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                # Total errors
                total = conn.execute("SELECT COUNT(*) FROM _error_log").fetchone()[0]
                
                # By severity
                severity_result = conn.execute("""
                    SELECT severity, COUNT(*) 
                    FROM _error_log 
                    GROUP BY severity
                """).fetchall()
                by_severity = {row[0]: row[1] for row in severity_result}
                
                # By type
                type_result = conn.execute("""
                    SELECT error_type, COUNT(*) 
                    FROM _error_log 
                    GROUP BY error_type
                    ORDER BY COUNT(*) DESC
                    LIMIT 10
                """).fetchall()
                by_type = {row[0]: row[1] for row in type_result}
                
                # Recent (last 24h)
                recent_24h = conn.execute("""
                    SELECT COUNT(*) 
                    FROM _error_log 
                    WHERE timestamp >= (now() - INTERVAL '1 day')::VARCHAR
                """).fetchone()[0]
                
                return {
                    "total_errors": total,
                    "by_severity": by_severity,
                    "top_errors": by_type,
                    "last_24h": recent_24h
                }
        except Exception as e:
            print(f"Warning: Could not get error summary: {e}")
            return {}


def safe_execute(
    func: Callable[..., Any],
    error_type: str = "UNKNOWN_ERROR",
    error_handler: AppErrorHandler | None = None,
    show_traceback: bool = False,
    **context: Any
) -> Any | None:
    """
    Decorator/wrapper to safely execute functions with error handling.
    
    Usage:
        result = safe_execute(
            my_function,
            error_type="DB_QUERY_FAILED",
            error_handler=handler,
            plant_id="ABC123"
        )
    """
    try:
        return func()
    except Exception as e:
        if error_handler:
            error_handler.handle_error(error_type, e, context, show_traceback)
        else:
            logger.error("Error: %s", e)
        return None


# Global error handler instance
_global_handler: AppErrorHandler | None = None


def get_error_handler() -> AppErrorHandler:
    """Get or create global error handler instance."""
    global _global_handler
    if _global_handler is None:
        # Try to use reporting DB for error logging
        try:
            from solar_platform.config import config
            _global_handler = AppErrorHandler(db_path=str(config.db_path))
        except Exception:
            _global_handler = AppErrorHandler()
    return _global_handler
