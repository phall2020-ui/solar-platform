"""Tests for services.database.engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from solar_platform.db.engine import DuckDBEngine, get_engine


def test_get_engine_returns_singleton_for_same_path(tmp_path):
    db_path = tmp_path / "singleton.duckdb"
    db_path.touch()

    engine_a = get_engine(db_path)
    engine_b = get_engine(str(db_path))

    assert engine_a is engine_b


def test_connection_context_is_usable_and_closes(test_engine: DuckDBEngine):
    with test_engine.connection() as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1), (2)")
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2

    with test_engine.connection(read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2


def test_transaction_commits_and_rolls_back(test_engine: DuckDBEngine):
    test_engine.execute("CREATE TABLE tx_test (id INTEGER)")

    with test_engine.transaction() as conn:
        conn.execute("INSERT INTO tx_test VALUES (1)")

    assert test_engine.execute("SELECT COUNT(*) FROM tx_test")[0][0] == 1

    try:
        with test_engine.transaction() as conn:
            conn.execute("INSERT INTO tx_test VALUES (2)")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    assert test_engine.execute("SELECT COUNT(*) FROM tx_test")[0][0] == 1


def test_execute_df_and_bulk_insert_df(test_engine: DuckDBEngine):
    test_engine.execute("CREATE TABLE plants (plant_uid VARCHAR, alias VARCHAR)")
    df = pd.DataFrame(
        [
            {"plant_uid": "u-1", "alias": "Alpha"},
            {"plant_uid": "u-2", "alias": "Beta"},
        ]
    )

    inserted = test_engine.bulk_insert_df("plants", df)

    assert inserted == 2
    rows = test_engine.execute("SELECT alias FROM plants ORDER BY alias")
    assert rows == [("Alpha",), ("Beta",)]

    out_df = test_engine.execute_df("SELECT * FROM plants ORDER BY alias")
    assert list(out_df.columns) == ["plant_uid", "alias"]
    assert len(out_df) == 2


def test_table_helpers_and_upsert(test_engine: DuckDBEngine):
    test_engine.execute(
        "CREATE TABLE plants (plant_uid VARCHAR PRIMARY KEY, alias VARCHAR, dc_size_kw DOUBLE)"
    )
    assert test_engine.table_exists("plants") is True
    assert "plants" in test_engine.get_tables()

    test_engine.execute_insert("plants", {"plant_uid": "uid-1", "alias": "One", "dc_size_kw": 1.0})
    test_engine.execute_upsert(
        "plants",
        {"plant_uid": "uid-1", "alias": "One Updated", "dc_size_kw": 2.0},
        ["plant_uid"],
    )

    row = test_engine.execute("SELECT alias, dc_size_kw FROM plants WHERE plant_uid = ?", ("uid-1",))[0]
    assert row == ("One Updated", 2.0)


def test_identifier_validation_prevents_unsafe_table_name(test_engine: DuckDBEngine):
    test_engine.execute("CREATE TABLE safe_table (id INTEGER)")

    try:
        test_engine.execute_insert("safe_table; DROP TABLE safe_table", {"id": 1})
        assert False, "Expected ValueError for unsafe identifier"
    except ValueError:
        assert True
