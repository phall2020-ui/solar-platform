"""Tests for the error handler (services/error_handler.py).

Streamlit and database calls are mocked to keep tests self-contained.
"""
from unittest.mock import MagicMock, patch
import sys

import pytest

# We need to mock streamlit before importing the module under test
_st_mock = MagicMock()
with patch.dict(sys.modules, {"streamlit": _st_mock}):
    from solar_platform.services.error_handler import (
        AppErrorHandler,
        ErrorContext,
        ErrorSeverity,
        get_error_handler,
        safe_execute,
    )


# ---------------------------------------------------------------------------
# ErrorSeverity enum
# ---------------------------------------------------------------------------

class TestErrorSeverity:
    """Tests for the ErrorSeverity enum."""

    def test_has_expected_levels(self):
        levels = {e.value for e in ErrorSeverity}
        assert levels == {"info", "warning", "error", "critical"}

    def test_values_are_strings(self):
        for member in ErrorSeverity:
            assert isinstance(member.value, str)


# ---------------------------------------------------------------------------
# ErrorContext dataclass
# ---------------------------------------------------------------------------

class TestErrorContext:
    """Tests for the ErrorContext dataclass."""

    def test_creation_with_required_fields(self):
        ctx = ErrorContext(
            error_type="DB_CONNECTION_FAILED",
            severity=ErrorSeverity.CRITICAL,
            user_message="Unable to connect",
            technical_message="Connection refused",
            recovery_actions=["Retry"],
            timestamp="2025-01-01T00:00:00",
            context={"host": "localhost"},
        )
        assert ctx.error_type == "DB_CONNECTION_FAILED"
        assert ctx.severity == ErrorSeverity.CRITICAL
        assert ctx.traceback is None  # optional, default None

    def test_traceback_is_optional(self):
        ctx = ErrorContext(
            error_type="TEST",
            severity=ErrorSeverity.INFO,
            user_message="msg",
            technical_message="tech",
            recovery_actions=[],
            timestamp="now",
            context={},
            traceback="some traceback",
        )
        assert ctx.traceback == "some traceback"

    def test_context_is_dict(self):
        ctx = ErrorContext(
            error_type="T",
            severity=ErrorSeverity.WARNING,
            user_message="m",
            technical_message="t",
            recovery_actions=[],
            timestamp="ts",
            context={"key": "val"},
        )
        assert ctx.context == {"key": "val"}


# ---------------------------------------------------------------------------
# ERROR_CATALOG classification
# ---------------------------------------------------------------------------

class TestErrorCatalog:
    """Tests for the built-in error catalog."""

    def test_catalog_is_non_empty(self):
        assert len(AppErrorHandler.ERROR_CATALOG) > 0

    def test_all_entries_have_required_keys(self):
        for code, info in AppErrorHandler.ERROR_CATALOG.items():
            assert "user_message" in info, f"{code} missing user_message"
            assert "recovery" in info, f"{code} missing recovery"
            assert "severity" in info, f"{code} missing severity"

    def test_severities_are_valid_enum_members(self):
        for code, info in AppErrorHandler.ERROR_CATALOG.items():
            assert isinstance(info["severity"], ErrorSeverity), \
                f"{code} severity is not ErrorSeverity"

    def test_db_connection_failed_is_critical(self):
        entry = AppErrorHandler.ERROR_CATALOG["DB_CONNECTION_FAILED"]
        assert entry["severity"] == ErrorSeverity.CRITICAL

    def test_api_timeout_is_warning(self):
        entry = AppErrorHandler.ERROR_CATALOG["API_TIMEOUT"]
        assert entry["severity"] == ErrorSeverity.WARNING

    def test_unknown_error_exists(self):
        assert "UNKNOWN_ERROR" in AppErrorHandler.ERROR_CATALOG


# ---------------------------------------------------------------------------
# AppErrorHandler instantiation
# ---------------------------------------------------------------------------

class TestAppErrorHandler:
    """Tests for AppErrorHandler init and error handling."""

    def test_init_without_db(self):
        handler = AppErrorHandler()
        assert handler.db_path is None

    @patch("services.error_handler.get_connection")
    def test_init_with_db_path(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        handler = AppErrorHandler(db_path="/tmp/test.duckdb")
        assert handler.db_path == "/tmp/test.duckdb"

    def test_handle_error_returns_error_context(self):
        handler = AppErrorHandler()
        with patch.object(handler, "_display_error"), \
             patch.object(handler, "_log_error"):
            ctx = handler.handle_error("DB_QUERY_FAILED", ValueError("oops"))
            assert isinstance(ctx, ErrorContext)
            assert ctx.error_type == "DB_QUERY_FAILED"
            assert ctx.severity == ErrorSeverity.ERROR

    def test_handle_unknown_error_type_falls_back(self):
        handler = AppErrorHandler()
        with patch.object(handler, "_display_error"), \
             patch.object(handler, "_log_error"):
            ctx = handler.handle_error("TOTALLY_UNKNOWN_TYPE")
            assert ctx.error_type == "TOTALLY_UNKNOWN_TYPE"
            # Falls back to UNKNOWN_ERROR catalog entry
            assert ctx.severity == ErrorSeverity.ERROR


# ---------------------------------------------------------------------------
# get_error_handler singleton
# ---------------------------------------------------------------------------

class TestGetErrorHandler:
    """Tests for the get_error_handler() factory."""

    def test_returns_app_error_handler(self):
        import services.error_handler as mod
        mod._global_handler = None  # reset singleton
        with patch("services.error_handler.get_connection"), \
             patch.dict(sys.modules, {"streamlit": _st_mock}):
            handler = get_error_handler()
            assert isinstance(handler, AppErrorHandler)

    def test_returns_same_instance_on_second_call(self):
        import services.error_handler as mod
        mod._global_handler = None
        with patch("services.error_handler.get_connection"), \
             patch.dict(sys.modules, {"streamlit": _st_mock}):
            h1 = get_error_handler()
            h2 = get_error_handler()
            assert h1 is h2


# ---------------------------------------------------------------------------
# safe_execute wrapper
# ---------------------------------------------------------------------------

class TestSafeExecute:
    """Tests for the safe_execute() helper."""

    def test_returns_result_on_success(self):
        result = safe_execute(lambda: 42)
        assert result == 42

    def test_returns_none_on_failure(self):
        handler = AppErrorHandler()
        with patch.object(handler, "_display_error"), \
             patch.object(handler, "_log_error"):
            result = safe_execute(
                lambda: 1 / 0,
                error_type="CALCULATION_ERROR",
                error_handler=handler,
            )
            assert result is None
