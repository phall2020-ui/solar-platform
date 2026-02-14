"""Tests for database utilities (services/db_utils.py).

Uses a temporary DuckDB in-memory database — no persistent files created.
"""
import duckdb
import pytest

from services.db_utils import execute_query, get_connection, table_exists, get_tables, execute_df


# ---------------------------------------------------------------------------
# get_connection context manager
# ---------------------------------------------------------------------------

class TestGetConnection:
    """Tests for the get_connection() context manager."""

    def test_opens_and_closes_connection(self, tmp_path):
        db = str(tmp_path / "test.duckdb")
        with get_connection(db) as conn:
            assert conn is not None
            conn.execute("SELECT 1")
        # After context exits, the connection should be closed.
        # DuckDB raises an error when you try to use a closed connection.
        with pytest.raises(Exception):
            conn.execute("SELECT 1")

    def test_read_only_mode(self, tmp_path):
        db = str(tmp_path / "ro.duckdb")
        # Create the DB first so it exists for read-only open
        duckdb.connect(db).close()
        with get_connection(db, read_only=True) as conn:
            result = conn.execute("SELECT 42").fetchone()
            assert result[0] == 42

    def test_yields_usable_connection(self, tmp_path):
        db = str(tmp_path / "usable.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.execute("INSERT INTO t VALUES (1), (2)")
            rows = conn.execute("SELECT * FROM t").fetchall()
            assert len(rows) == 2


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------

class TestExecuteQuery:
    """Tests for execute_query()."""

    def test_returns_results(self, tmp_path):
        db = str(tmp_path / "eq.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE demo (val INTEGER)")
            conn.execute("INSERT INTO demo VALUES (10), (20), (30)")
        results = execute_query(db, "SELECT val FROM demo ORDER BY val")
        assert results == [(10,), (20,), (30,)]

    def test_with_params(self, tmp_path):
        db = str(tmp_path / "eq_params.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE nums (n INTEGER)")
            conn.execute("INSERT INTO nums VALUES (1),(2),(3),(4),(5)")
        rows = execute_query(db, "SELECT n FROM nums WHERE n > ?", (3,))
        assert sorted([r[0] for r in rows]) == [4, 5]

    def test_empty_result(self, tmp_path):
        db = str(tmp_path / "eq_empty.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE empty_t (x TEXT)")
        results = execute_query(db, "SELECT * FROM empty_t")
        assert results == []


# ---------------------------------------------------------------------------
# execute_df
# ---------------------------------------------------------------------------

class TestExecuteDf:
    """Tests for execute_df()."""

    def test_returns_dataframe(self, tmp_path):
        db = str(tmp_path / "edf.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE plants (name TEXT, mw DOUBLE)")
            conn.execute("INSERT INTO plants VALUES ('Alpha', 5.0), ('Beta', 10.0)")
        df = execute_df(db, "SELECT * FROM plants ORDER BY name")
        assert list(df.columns) == ["name", "mw"]
        assert len(df) == 2
        assert df["name"].iloc[0] == "Alpha"


# ---------------------------------------------------------------------------
# table_exists
# ---------------------------------------------------------------------------

class TestTableExists:
    """Tests for table_exists()."""

    def test_existing_table_returns_true(self, tmp_path):
        db = str(tmp_path / "te.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE my_table (id INTEGER)")
        assert table_exists(db, "my_table") is True

    def test_nonexistent_table_returns_false(self, tmp_path):
        db = str(tmp_path / "te2.duckdb")
        # Create an empty database
        duckdb.connect(db).close()
        assert table_exists(db, "no_such_table") is False

    def test_case_insensitive_lookup(self, tmp_path):
        """DuckDB lowercases table names by default; verify lookup works."""
        db = str(tmp_path / "te3.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE readings (ts TIMESTAMP)")
        # information_schema stores in lower-case
        assert table_exists(db, "readings") is True


# ---------------------------------------------------------------------------
# get_tables
# ---------------------------------------------------------------------------

class TestGetTables:
    """Tests for get_tables()."""

    def test_lists_created_tables(self, tmp_path):
        db = str(tmp_path / "gt.duckdb")
        with get_connection(db) as conn:
            conn.execute("CREATE TABLE alpha (x INT)")
            conn.execute("CREATE TABLE beta (y INT)")
        tables = get_tables(db)
        assert "alpha" in tables
        assert "beta" in tables

    def test_empty_database_returns_empty_list(self, tmp_path):
        db = str(tmp_path / "gt_empty.duckdb")
        duckdb.connect(db).close()
        tables = get_tables(db)
        assert tables == []
