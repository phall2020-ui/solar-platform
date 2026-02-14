"""
Solar Data Access Layer

This module provides a comprehensive SQLite data access layer for the Solar Asset
Data Manager application. It handles all database operations including:
- Connection management with optimizations
- Data validation and cleaning
- Duplicate detection and handling
- Efficient querying with caching
- Schema management and introspection

The SolarDataExtractor class uses a singleton pattern for connection reuse
and provides methods for safe data import with validation, duplicate detection,
and date format normalization.
"""

import sqlite3
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import pandas as pd


def safe_convert_dates(series: pd.Series) -> pd.Series:
    """
    Safely convert date values to 'Mon-YY' format (e.g., 'Jan-25').
    Handles multiple input formats including when dates are already formatted.
    Handles mixed formats in the same series.

    Args:
        series: Pandas Series containing date values

    Returns:
        Series with dates converted to 'Mon-YY' format
    """
    if series.empty:
        return series

    result = series.copy()

    # Check if ALL values are already in the target format (e.g., "Jan-25")
    non_null_vals = result.dropna()
    if len(non_null_vals) > 0:
        all_valid = True
        for val in non_null_vals:
            try:
                test_val = str(val)
                parsed = pd.to_datetime(test_val, format="%b-%y", errors="coerce")
                if pd.isna(parsed):
                    all_valid = False
                    break
            except (ValueError, TypeError):
                all_valid = False
                break

        if all_valid:
            # All values already in correct format, return as is
            return result

    # Try to convert each value individually (handles mixed formats)
    date_formats = ["%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"]

    def convert_single_date(val):
        if pd.isna(val):
            return val

        val_str = str(val)

        # Try each format
        for fmt in date_formats:
            try:
                parsed = pd.to_datetime(val_str, format=fmt, errors="coerce")
                if pd.notna(parsed):
                    return parsed.strftime("%b-%y")
            except (ValueError, TypeError):
                continue

        # Fallback: let pandas infer the format
        try:
            parsed = pd.to_datetime(val_str, errors="coerce")
            if pd.notna(parsed):
                return parsed.strftime("%b-%y")
        except (ValueError, TypeError):
            pass

        return val  # Return original if cannot convert

    return result.apply(convert_single_date)


class SolarDataExtractor:
    """Handles all SQLite interactions with connection pooling, validation, and duplicate handling."""

    _instance = None
    _conn: Optional[sqlite3.Connection] = None

    def __new__(cls, db_name: str):
        """Singleton pattern to reuse connection."""
        if cls._instance is None or cls._instance.db_name != db_name:
            cls._instance = super(SolarDataExtractor, cls).__new__(cls)
            cls._instance.db_name = db_name
            cls._instance._initialize_connection()
        return cls._instance

    def _initialize_connection(self):
        """Initialize database connection with optimizations."""
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass

        self._conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-64000")
        self.cursor = self._conn.cursor()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDATION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        required_columns: Optional[List[str]] = None,
        numeric_columns: Optional[List[str]] = None,
        date_columns: Optional[List[str]] = None,
        non_empty_columns: Optional[List[str]] = None,
    ) -> Tuple[bool, List[str], pd.DataFrame]:
        """
        Validate a DataFrame before saving.

        Args:
            df: DataFrame to validate
            required_columns: Columns that must exist
            numeric_columns: Columns that should be numeric
            date_columns: Columns that should be dates
            non_empty_columns: Columns that cannot have null values

        Returns:
            Tuple of (is_valid, list of warnings/errors, cleaned DataFrame)
        """
        warnings = []
        errors = []
        df_clean = df.copy()

        # Check for empty DataFrame
        if df_clean.empty:
            return False, ["DataFrame is empty"], df_clean

        # Check required columns
        if required_columns:
            missing = [c for c in required_columns if c not in df_clean.columns]
            if missing:
                errors.append(f"Missing required columns: {missing}")

        # Validate and clean numeric columns
        if numeric_columns:
            for col in numeric_columns:
                if col in df_clean.columns:
                    # Try to convert to numeric
                    original_nulls = df_clean[col].isna().sum()

                    # Clean string formatting (commas, percentages)
                    if df_clean[col].dtype == "object":
                        df_clean[col] = (
                            df_clean[col]
                            .astype(str)
                            .str.replace(",", "", regex=False)
                            .str.replace("%", "", regex=False)
                            .str.strip()
                        )

                    df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
                    new_nulls = df_clean[col].isna().sum()

                    if new_nulls > original_nulls:
                        warnings.append(
                            f"Column '{col}': {new_nulls - original_nulls} values could not be converted to numeric"
                        )

        # Validate date columns
        if date_columns:
            for col in date_columns:
                if col in df_clean.columns:
                    original_nulls = df_clean[col].isna().sum()
                    df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")
                    new_nulls = df_clean[col].isna().sum()

                    if new_nulls > original_nulls:
                        warnings.append(
                            f"Column '{col}': {new_nulls - original_nulls} values could not be parsed as dates"
                        )

        # Check non-empty columns
        if non_empty_columns:
            for col in non_empty_columns:
                if col in df_clean.columns:
                    null_count = df_clean[col].isna().sum()
                    if null_count > 0:
                        warnings.append(f"Column '{col}' has {null_count} null values")

        # Check for completely empty columns
        empty_cols = [c for c in df_clean.columns if df_clean[c].isna().all()]
        if empty_cols:
            warnings.append(f"Completely empty columns: {empty_cols}")

        # Check for duplicate column names
        if len(df_clean.columns) != len(set(df_clean.columns)):
            errors.append("DataFrame has duplicate column names")

        is_valid = len(errors) == 0
        messages = errors + warnings

        return is_valid, messages, df_clean

    def validate_schema_match(
        self,
        df: pd.DataFrame,
        table_name: str,
    ) -> Tuple[bool, List[str]]:
        """
        Check if DataFrame schema matches existing table.

        Returns:
            Tuple of (schemas_match, list of differences)
        """
        if table_name not in self.list_tables():
            return True, ["Table does not exist yet - will be created"]

        existing_schema = self.get_table_schema(table_name)
        existing_cols = {col["name"] for col in existing_schema}
        new_cols = set(df.columns)

        differences = []

        # Check for missing columns in new data
        missing_in_new = existing_cols - new_cols
        if missing_in_new:
            differences.append(f"Columns in table but not in new data: {missing_in_new}")

        # Check for extra columns in new data
        extra_in_new = new_cols - existing_cols
        if extra_in_new:
            differences.append(f"New columns not in existing table: {extra_in_new}")

        schemas_match = len(missing_in_new) == 0 and len(extra_in_new) == 0

        return schemas_match, differences

    # ═══════════════════════════════════════════════════════════════════════════
    # DUPLICATE HANDLING METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def find_duplicates(
        self,
        df: pd.DataFrame,
        key_columns: List[str],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split DataFrame into unique and duplicate rows based on key columns.

        Args:
            df: DataFrame to check
            key_columns: Columns to use as composite key

        Returns:
            Tuple of (unique_rows, duplicate_rows)
        """
        # Check within the DataFrame itself
        duplicated_mask = df.duplicated(subset=key_columns, keep="first")
        unique_rows = df[~duplicated_mask].copy()
        duplicate_rows = df[duplicated_mask].copy()

        return unique_rows, duplicate_rows

    def check_for_duplicates(
        self,
        df: pd.DataFrame,
        table_name: str,
        key_columns: List[str],
    ) -> Tuple[bool, pd.DataFrame, pd.DataFrame, Dict]:
        """
        Check for duplicates before adding data. Flags duplicates that would
        be rejected if trying to insert (same month and site combination).

        This method does not modify the database - it only checks for potential
        conflicts.

        Args:
            df: DataFrame to check
            table_name: Table to check against
            key_columns: Columns to use as composite key (e.g., ['Site', 'Date'] for month and site)

        Returns:
            Tuple of:
                - has_duplicates: True if any duplicates found
                - duplicates_in_input: DataFrame of rows that are duplicates within the input
                - duplicates_with_db: DataFrame of rows that already exist in the database
                - summary: Dict with counts and details
        """
        # Convert date columns for consistent comparison
        df_check = df.copy()
        date_patterns = ["date", "month", "period", "time"]
        for col in df_check.columns:
            if any(pat in col.lower() for pat in date_patterns):
                try:
                    df_check[col] = safe_convert_dates(df_check[col])
                except (ValueError, TypeError):
                    pass

        # Check for duplicates within the input DataFrame
        unique_df, duplicates_in_input = self.find_duplicates(df_check, key_columns)

        # Check for duplicates with the database
        new_rows, duplicates_with_db = self.find_existing_rows(unique_df, table_name, key_columns)

        has_duplicates = len(duplicates_in_input) > 0 or len(duplicates_with_db) > 0

        summary = {
            "total_rows": len(df),
            "unique_in_input": len(unique_df),
            "duplicates_in_input_count": len(duplicates_in_input),
            "duplicates_with_db_count": len(duplicates_with_db),
            "new_rows_count": len(new_rows),
            "has_duplicates": has_duplicates,
        }

        # Add duplicate details for flagging
        if len(duplicates_in_input) > 0:
            summary["flagged_input_duplicates"] = duplicates_in_input[key_columns].to_dict("records")
        if len(duplicates_with_db) > 0:
            summary["flagged_db_duplicates"] = duplicates_with_db[key_columns].to_dict("records")

        return has_duplicates, duplicates_in_input, duplicates_with_db, summary

    def find_existing_rows(
        self,
        df: pd.DataFrame,
        table_name: str,
        key_columns: List[str],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Find which rows already exist in the database.

        Args:
            df: DataFrame to check
            table_name: Table to check against
            key_columns: Columns to use as composite key

        Returns:
            Tuple of (new_rows, existing_rows)
        """
        if table_name not in self.list_tables():
            return df.copy(), pd.DataFrame()

        try:
            # Get existing keys
            key_cols_str = ", ".join([f'"{c}"' for c in key_columns])
            existing = pd.read_sql_query(f"SELECT DISTINCT {key_cols_str} FROM {table_name}", self._conn)

            if existing.empty:
                return df.copy(), pd.DataFrame()

            # Merge to find matches
            merged = df.merge(existing, on=key_columns, how="left", indicator=True)

            new_rows = df[merged["_merge"] == "left_only"].copy()
            existing_rows = df[merged["_merge"] == "both"].copy()

            return new_rows, existing_rows

        except Exception as e:
            print(f"Warning: Could not check existing rows: {e}")
            return df.copy(), pd.DataFrame()

    def remove_duplicates_from_table(
        self,
        table_name: str,
        key_columns: List[str],
        keep: str = "first",
    ) -> Tuple[bool, str]:
        """
        Remove duplicate rows from an existing table.

        Args:
            table_name: Table to deduplicate
            key_columns: Columns to use as composite key
            keep: 'first' or 'last' - which duplicate to keep

        Returns:
            Tuple of (success, message)
        """
        try:
            # Read all data
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", self._conn)
            original_count = len(df)

            # Remove duplicates
            df_deduped = df.drop_duplicates(subset=key_columns, keep=keep)
            new_count = len(df_deduped)

            removed = original_count - new_count

            if removed > 0:
                # Replace table with deduplicated data
                df_deduped.to_sql(table_name, self._conn, if_exists="replace", index=False)
                self._conn.commit()
                self.clear_cache()
                return True, f"Removed {removed:,} duplicate rows from '{table_name}'"
            else:
                return True, f"No duplicates found in '{table_name}'"

        except Exception as e:
            self._conn.rollback()
            return False, f"Error removing duplicates: {e}"

    # ═══════════════════════════════════════════════════════════════════════════
    # ENHANCED DATA EXTRACTION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def extract_from_df(
        self,
        df: pd.DataFrame,
        table_name: str,
        mode: str = "replace",
        debug: bool = False,
    ) -> Tuple[bool, str]:
        """
        Save DataFrame to database with chunking for large datasets.
        Converts date fields to 'Apr-25' format.

        Args:
            df: DataFrame to save
            table_name: Target table name
            mode: 'replace', 'append', or 'fail'
            debug: Print debug information
        """
        try:
            if debug:
                print("[DEBUG] extract_from_df called:")
                print(f"  - DataFrame shape: {df.shape}")
                print(f"  - Table name: {table_name}")
                print(f"  - Mode: {mode}")

            # Convert date columns to standard format using safe conversion
            date_patterns = ["date", "month", "period", "time"]
            for col in df.columns:
                if any(pat in col.lower() for pat in date_patterns):
                    try:
                        df[col] = safe_convert_dates(df[col])
                    except Exception:
                        pass

            chunksize = 10000 if len(df) > 10000 else None

            df.to_sql(table_name, self._conn, if_exists=mode, index=False, chunksize=chunksize)
            self._conn.commit()
            self.clear_cache()

            return True, f"Saved {len(df):,} rows to '{table_name}' (mode={mode})."

        except Exception as e:
            if debug:
                print(f"[DEBUG] Exception: {e}")
            self._conn.rollback()
            return False, f"Error saving: {e}"

    def extract_with_validation(
        self,
        df: pd.DataFrame,
        table_name: str,
        mode: str = "replace",
        required_columns: Optional[List[str]] = None,
        numeric_columns: Optional[List[str]] = None,
        date_columns: Optional[List[str]] = None,
        non_empty_columns: Optional[List[str]] = None,
    ) -> Tuple[bool, str, List[str]]:
        """
        Save DataFrame with validation.

        Returns:
            Tuple of (success, message, list of warnings)
        """
        # Validate
        is_valid, messages, df_clean = self.validate_dataframe(
            df,
            required_columns=required_columns,
            numeric_columns=numeric_columns,
            date_columns=date_columns,
            non_empty_columns=non_empty_columns,
        )

        if not is_valid:
            return False, "Validation failed", messages

        # Check schema match for append mode
        if mode == "append":
            schema_match, schema_messages = self.validate_schema_match(df_clean, table_name)
            if not schema_match:
                return False, "Schema mismatch", messages + schema_messages

        # Save
        success, save_message = self.extract_from_df(df_clean, table_name, mode=mode)

        return success, save_message, messages

    def extract_unique_only(
        self,
        df: pd.DataFrame,
        table_name: str,
        key_columns: List[str],
        update_existing: bool = False,
    ) -> Tuple[bool, str, Dict]:
        """
        Append only unique rows to a table based on key columns.

        Args:
            df: DataFrame to save
            table_name: Target table name
            key_columns: Columns to use as composite key for uniqueness
            update_existing: If True, update existing rows; if False, skip them

        Returns:
            Tuple of (success, message, stats dict)
        """
        stats = {
            "total_input": len(df),
            "duplicates_in_input": 0,
            "already_in_db": 0,
            "new_rows_added": 0,
            "rows_updated": 0,
        }

        try:
            # Validate key columns exist
            missing_keys = [c for c in key_columns if c not in df.columns]
            if missing_keys:
                return False, f"Key columns not found: {missing_keys}", stats

            # Remove duplicates within the input DataFrame
            unique_df, duplicate_df = self.find_duplicates(df, key_columns)
            stats["duplicates_in_input"] = len(duplicate_df)

            # Convert date columns using safe conversion
            date_patterns = ["date", "month", "period", "time"]
            for col in unique_df.columns:
                if any(pat in col.lower() for pat in date_patterns):
                    try:
                        unique_df[col] = safe_convert_dates(unique_df[col])
                    except Exception:
                        pass

            # Check if table exists
            if table_name not in self.list_tables():
                # Create new table
                unique_df.to_sql(table_name, self._conn, if_exists="replace", index=False)
                self._conn.commit()
                self.clear_cache()
                stats["new_rows_added"] = len(unique_df)
                return True, f"Created table '{table_name}' with {len(unique_df):,} rows", stats

            # Find which rows already exist
            new_rows, existing_rows = self.find_existing_rows(unique_df, table_name, key_columns)
            stats["already_in_db"] = len(existing_rows)

            # Handle existing rows
            if update_existing and len(existing_rows) > 0:
                # Delete existing rows and reinsert with new values
                for _, row in existing_rows.iterrows():
                    conditions = " AND ".join([f'"{col}" = ?' for col in key_columns])
                    values = [row[col] for col in key_columns]
                    self.cursor.execute(f"DELETE FROM {table_name} WHERE {conditions}", values)

                # Add updated rows
                existing_rows.to_sql(table_name, self._conn, if_exists="append", index=False)
                stats["rows_updated"] = len(existing_rows)

            # Add new rows
            if len(new_rows) > 0:
                new_rows.to_sql(table_name, self._conn, if_exists="append", index=False)
                stats["new_rows_added"] = len(new_rows)

            self._conn.commit()
            self.clear_cache()

            message_parts = []
            if stats["new_rows_added"] > 0:
                message_parts.append(f"{stats['new_rows_added']:,} new rows added")
            if stats["rows_updated"] > 0:
                message_parts.append(f"{stats['rows_updated']:,} rows updated")
            if stats["already_in_db"] > 0 and not update_existing:
                message_parts.append(f"{stats['already_in_db']:,} existing rows skipped")
            if stats["duplicates_in_input"] > 0:
                message_parts.append(f"{stats['duplicates_in_input']:,} duplicates in input removed")

            message = "; ".join(message_parts) if message_parts else "No changes made"

            return True, message, stats

        except Exception as e:
            self._conn.rollback()
            return False, f"Error: {e}", stats

    def upsert_data(
        self,
        df: pd.DataFrame,
        table_name: str,
        key_columns: List[str],
    ) -> Tuple[bool, str]:
        """
        Insert or update data based on key columns (upsert operation).

        Args:
            df: DataFrame to upsert
            table_name: Target table name
            key_columns: Columns to use as composite key

        Returns:
            Tuple of (success, message)
        """
        return self.extract_unique_only(df, table_name, key_columns, update_existing=True)[:2]

    # ═══════════════════════════════════════════════════════════════════════════
    # ORIGINAL QUERY METHODS (preserved)
    # ═══════════════════════════════════════════════════════════════════════════

    @lru_cache(maxsize=32)
    def query_data(self, query: str):
        """Execute query with caching for repeated queries."""
        try:
            df = pd.read_sql_query(query, self._conn)
            return True, df
        except Exception as e:
            return False, str(e)

    @lru_cache(maxsize=1)
    def list_tables(self):
        """List all tables with caching."""
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            return tuple(r[0] for r in self.cursor.fetchall())
        except Exception:
            return tuple()

    def clear_cache(self):
        """Clear cached table and query results."""
        self.list_tables.cache_clear()
        self.query_data.cache_clear()

    def delete_table(self, table_name: str):
        """Delete table and clear caches."""
        try:
            self.cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            self._conn.commit()
            self.clear_cache()
            return True, f"Deleted table '{table_name}'."
        except Exception as e:
            self._conn.rollback()
            return False, str(e)

    def query_data_paginated(
        self,
        table_name: str,
        page: int = 1,
        page_size: int = 1000,
        where_clause: str = "",
        order_by: str = "",
    ) -> Tuple[bool, pd.DataFrame, int]:
        """Query data with pagination for large tables."""
        try:
            count_query = f"SELECT COUNT(*) as count FROM {table_name}"
            if where_clause:
                count_query += f" WHERE {where_clause}"

            total = pd.read_sql_query(count_query, self._conn)["count"].iloc[0]

            offset = (page - 1) * page_size
            query = f"SELECT * FROM {table_name}"
            if where_clause:
                query += f" WHERE {where_clause}"
            if order_by:
                query += f" ORDER BY {order_by}"
            query += f" LIMIT {page_size} OFFSET {offset}"

            df = pd.read_sql_query(query, self._conn)
            return True, df, total
        except Exception:
            return False, pd.DataFrame(), 0

    def get_table_schema(self, table_name: str) -> List[Dict]:
        """Get column information for a table."""
        try:
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = []
            for row in self.cursor.fetchall():
                columns.append(
                    {
                        "name": row[1],
                        "type": row[2],
                        "notnull": bool(row[3]),
                        "default": row[4],
                        "pk": bool(row[5]),
                    }
                )
            return columns
        except Exception:
            return []

    def get_table_stats(self, table_name: str) -> Dict:
        """Get statistics about a table."""
        try:
            # Row count
            count = pd.read_sql_query(f"SELECT COUNT(*) as count FROM {table_name}", self._conn)["count"].iloc[0]

            # Column info
            schema = self.get_table_schema(table_name)

            # Sample data for date range
            df_sample = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 1000", self._conn)

            # Find date columns and their ranges
            date_ranges = {}
            date_patterns = ["date", "month", "period"]
            for col in df_sample.columns:
                if any(pat in col.lower() for pat in date_patterns):
                    try:
                        dates = pd.to_datetime(df_sample[col], errors="coerce").dropna()
                        if len(dates) > 0:
                            date_ranges[col] = {
                                "min": dates.min().strftime("%Y-%m-%d"),
                                "max": dates.max().strftime("%Y-%m-%d"),
                            }
                    except Exception:
                        pass

            return {
                "row_count": count,
                "column_count": len(schema),
                "columns": [c["name"] for c in schema],
                "date_ranges": date_ranges,
            }

        except Exception as e:
            return {"error": str(e)}

    def get_unique_values(
        self,
        table_name: str,
        column_name: str,
        limit: int = 100,
    ) -> List:
        """Get unique values from a column."""
        try:
            df = pd.read_sql_query(f'SELECT DISTINCT "{column_name}" FROM {table_name} LIMIT {limit}', self._conn)
            return df[column_name].dropna().tolist()
        except Exception:
            return []
