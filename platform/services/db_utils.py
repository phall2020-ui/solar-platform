"""
Database utilities for DuckDB connections.
Provides a consistent interface for database access across the application.
"""
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
import warnings

import duckdb
import pandas as pd

from services.database import get_engine


_DEPRECATION_MESSAGE = (
    "services.db_utils is deprecated and will be removed in a future release. "
    "Use services.database.engine.get_engine(...) and repository classes instead."
)


def _warn_deprecated() -> None:
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)


@contextmanager
def get_connection(db_path: str, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Context manager for DuckDB connections.
    
    Args:
        db_path: Path to DuckDB database file
        read_only: Whether to open in read-only mode
        
    Yields:
        DuckDB connection
    """
    _warn_deprecated()
    engine = get_engine(db_path)
    with engine.connection(read_only=read_only) as conn:
        yield conn


def execute_query(db_path: str, query: str, params: tuple | None = None) -> list[Any]:
    """Execute a query and return results."""
    _warn_deprecated()
    return get_engine(db_path).execute(query, params)


def execute_df(db_path: str, query: str, params: tuple | None = None) -> pd.DataFrame:
    """Execute a query and return results as a DataFrame."""
    _warn_deprecated()
    return get_engine(db_path).execute_df(query, params)


def table_exists(db_path: str, table_name: str) -> bool:
    """Check if a table exists in the database."""
    _warn_deprecated()
    return get_engine(db_path).table_exists(table_name)


def get_tables(db_path: str) -> list[str]:
    """Get list of all tables in the database."""
    _warn_deprecated()
    return get_engine(db_path).get_tables()
