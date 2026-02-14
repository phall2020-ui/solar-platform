"""Smoke tests to verify basic imports work."""


def test_config_imports():
    """Verify config module imports without error."""
    from services.config import APP_NAME, APP_VERSION

    assert APP_NAME
    assert APP_VERSION


def test_db_utils_imports():
    """Verify db_utils module imports."""
    from services.db_utils import execute_df, execute_query, get_connection

    assert callable(get_connection)
    assert callable(execute_query)
    assert callable(execute_df)
