"""Migration script: DuckDB -> PostgreSQL/TimescaleDB.

This script provides dry-run schema generation and row-count migration reports
without requiring PostgreSQL to be installed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import duckdb


def get_duckdb_schema(db_path: str) -> dict[str, list[dict[str, Any]]]:
    """Extract main-schema table and column metadata from DuckDB."""
    with duckdb.connect(db_path, read_only=True) as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        ]

        tables: dict[str, list[dict[str, Any]]] = {}
        for table in table_names:
            columns = conn.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'main' AND table_name = ?
                ORDER BY ordinal_position
                """,
                [table],
            ).fetchall()
            tables[table] = [
                {"name": col[0], "type": col[1], "nullable": col[2] == "YES"}
                for col in columns
            ]

    return tables


def duckdb_to_pg_type(duckdb_type: str) -> str:
    """Map DuckDB column type strings to PostgreSQL-friendly types."""
    normalized = duckdb_type.upper().strip()

    mapping = {
        "VARCHAR": "TEXT",
        "CHAR": "TEXT",
        "TEXT": "TEXT",
        "BIGINT": "BIGINT",
        "INTEGER": "INTEGER",
        "INT": "INTEGER",
        "SMALLINT": "SMALLINT",
        "DOUBLE": "DOUBLE PRECISION",
        "DOUBLE PRECISION": "DOUBLE PRECISION",
        "FLOAT": "REAL",
        "REAL": "REAL",
        "BOOLEAN": "BOOLEAN",
        "DATE": "DATE",
        "TIMESTAMP": "TIMESTAMPTZ",
        "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
        "BLOB": "BYTEA",
        "JSON": "JSONB",
        "DECIMAL": "NUMERIC",
        "UUID": "UUID",
    }

    if normalized in mapping:
        return mapping[normalized]

    if normalized.startswith("DECIMAL(") or normalized.startswith("NUMERIC("):
        return normalized.replace("DECIMAL", "NUMERIC")

    if normalized.startswith("TIMESTAMP"):
        return "TIMESTAMPTZ"

    return "TEXT"


def generate_pg_schema(tables: dict[str, list[dict[str, Any]]]) -> str:
    """Generate PostgreSQL CREATE TABLE statements and optional hypertable SQL."""
    statements: list[str] = []

    for table, columns in tables.items():
        col_defs = []
        for column in columns:
            pg_type = duckdb_to_pg_type(column["type"])
            nullable = "" if column["nullable"] else " NOT NULL"
            col_defs.append(f"    {column['name']} {pg_type}{nullable}")

        create_stmt = f"CREATE TABLE IF NOT EXISTS {table} (\n"
        create_stmt += ",\n".join(col_defs)
        create_stmt += "\n);"
        statements.append(create_stmt)

    if "readings" in tables:
        has_timestamp = any(col["name"].lower() in {"timestamp", "ts"} for col in tables["readings"])
        if has_timestamp:
            time_column = "timestamp" if any(col["name"] == "timestamp" for col in tables["readings"]) else "ts"
            statements.append(
                "\n-- Optional TimescaleDB conversion for readings\n"
                f"SELECT create_hypertable('readings', '{time_column}',\n"
                "    chunk_time_interval => INTERVAL '7 days',\n"
                "    if_not_exists => TRUE\n"
                ");"
            )

    return "\n\n".join(statements)


def build_row_count_report(source_path: str, tables: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Build per-table row-count readiness report."""
    report: dict[str, dict[str, Any]] = {}

    with duckdb.connect(source_path, read_only=True) as conn:
        for table in tables:
            try:
                source_rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                report[table] = {"source_rows": int(source_rows), "status": "ready"}
            except Exception as exc:
                report[table] = {"source_rows": 0, "status": f"error: {exc}"}

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate DuckDB schema to PostgreSQL-compatible SQL")
    parser.add_argument("--source", required=True, help="Path to source DuckDB file")
    parser.add_argument("--target", default="", help="PostgreSQL DSN (required for non dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Generate SQL/report without executing migration")
    parser.add_argument("--output", default="migration_schema.sql", help="Output SQL file path for dry-run mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        print(f"Error: Source database not found: {source}")
        return 1

    print(f"Analyzing source: {source}")
    tables = get_duckdb_schema(str(source))

    print(f"\nFound {len(tables)} tables:")
    report = build_row_count_report(str(source), tables)
    for table, info in report.items():
        print(f"  {table:30s} {info['source_rows']:>10,} rows  [{info['status']}]")

    if args.dry_run:
        schema_sql = generate_pg_schema(tables)
        output = Path(args.output)
        output.write_text(schema_sql, encoding="utf-8")
        print(f"\nSchema SQL written to: {output}")
        print("Dry-run complete. Review SQL before applying to PostgreSQL/TimescaleDB.")
        return 0

    if not args.target:
        print("Error: --target required when not using --dry-run")
        return 1

    print("\nFull migration execution is not implemented yet. Use --dry-run for now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
