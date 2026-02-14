"""
Test Data Import Validation
============================
Tests for validating data import functionality:
- Tests use a separate test database (not solar_assets.db)
- Duplicate data (same month and site) is flagged before being added
- Future data (new month/site combinations) is appended
"""

import unittest
import pandas as pd
import os
import sys
import tempfile

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_access import SolarDataExtractor, safe_convert_dates


class TestDataImportValidation(unittest.TestCase):
    """Test data import with validation for duplicates and appending."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary test database file."""
        # Create a unique test database file in temp directory
        cls.test_db_fd, cls.test_db_path = tempfile.mkstemp(suffix=".db", prefix="test_import_")
        os.close(cls.test_db_fd)
        
    @classmethod
    def tearDownClass(cls):
        """Remove the temporary test database file."""
        try:
            if os.path.exists(cls.test_db_path):
                os.remove(cls.test_db_path)
            # Also clean up any WAL/SHM files
            for suffix in ["-wal", "-shm"]:
                wal_path = cls.test_db_path + suffix
                if os.path.exists(wal_path):
                    os.remove(wal_path)
        except (OSError, FileNotFoundError):
            pass

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton to use a fresh instance with test database
        # This is necessary for test isolation with the singleton pattern
        SolarDataExtractor._instance = None
        self.extractor = SolarDataExtractor(self.test_db_path)
        self.table_name = "test_solar_data"
        # Clean up the table before each test
        self.extractor.delete_table(self.table_name)
        
    def tearDown(self):
        """Clean up after each test."""
        self.extractor.delete_table(self.table_name)

    def test_uses_test_database_not_production(self):
        """Verify tests use a separate test database, not the production one."""
        # The test database path should be in temp directory
        self.assertIn("test_import_", self.extractor.db_name)
        self.assertNotIn("solar_assets.db", self.extractor.db_name)
        print(f"\n[INFO] Using test database: {self.extractor.db_name}")

    def test_check_for_duplicates_flags_input_duplicates(self):
        """Test that duplicate rows within input data are flagged."""
        # Create data with duplicates (same Site and Date)
        df = pd.DataFrame({
            "Site": ["Site A", "Site A", "Site B"],  # First two are duplicates
            "Date": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "Energy": [100, 150, 200]  # Different values but same key
        })
        
        has_dups, dups_in_input, dups_with_db, summary = self.extractor.check_for_duplicates(
            df, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] Duplicate check summary: {summary}")
        
        # Should flag that there are duplicates
        self.assertTrue(has_dups, "Should detect duplicates")
        self.assertEqual(len(dups_in_input), 1, "Should find 1 duplicate in input")
        self.assertEqual(dups_in_input.iloc[0]["Site"], "Site A")
        self.assertIn("flagged_input_duplicates", summary)
        
    def test_check_for_duplicates_flags_db_conflicts(self):
        """Test that rows conflicting with database are flagged."""
        # First, add some data to the database
        df_initial = pd.DataFrame({
            "Site": ["Site A", "Site B"],
            "Date": ["2025-01-01", "2025-01-01"],
            "Energy": [100, 200]
        })
        success, msg, stats = self.extractor.extract_unique_only(
            df_initial, self.table_name, key_columns=["Site", "Date"]
        )
        self.assertTrue(success)
        
        # Now try to check if new data would conflict
        df_new = pd.DataFrame({
            "Site": ["Site A", "Site C"],  # Site A already exists for Jan-25
            "Date": ["2025-01-01", "2025-02-01"],  # Site A/Jan already in DB
            "Energy": [500, 300]  # Different values
        })
        
        has_dups, dups_in_input, dups_with_db, summary = self.extractor.check_for_duplicates(
            df_new, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] DB conflict check summary: {summary}")
        
        # Should flag that Site A for Jan-25 conflicts with DB
        self.assertTrue(has_dups, "Should detect DB conflicts")
        self.assertEqual(len(dups_with_db), 1, "Should find 1 conflict with DB")
        self.assertEqual(dups_with_db.iloc[0]["Site"], "Site A")
        self.assertIn("flagged_db_duplicates", summary)
        
    def test_check_for_duplicates_no_false_positives(self):
        """Test that unique data is not flagged as duplicate."""
        # Add initial data
        df_initial = pd.DataFrame({
            "Site": ["Site A", "Site B"],
            "Date": ["2025-01-01", "2025-01-01"],
            "Energy": [100, 200]
        })
        self.extractor.extract_unique_only(
            df_initial, self.table_name, key_columns=["Site", "Date"]
        )
        
        # Check completely new data (different sites/dates)
        df_new = pd.DataFrame({
            "Site": ["Site C", "Site D"],
            "Date": ["2025-02-01", "2025-03-01"],
            "Energy": [300, 400]
        })
        
        has_dups, dups_in_input, dups_with_db, summary = self.extractor.check_for_duplicates(
            df_new, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] No duplicates check summary: {summary}")
        
        self.assertFalse(has_dups, "Should not flag unique data as duplicates")
        self.assertEqual(len(dups_in_input), 0)
        self.assertEqual(len(dups_with_db), 0)

    def test_future_data_appended(self):
        """Test that future (new) data is properly appended to the database."""
        # Initial data for January
        df_initial = pd.DataFrame({
            "Site": ["Site A", "Site B"],
            "Date": ["2025-01-01", "2025-01-01"],
            "Energy": [100, 200]
        })
        
        success, msg, stats = self.extractor.extract_unique_only(
            df_initial, self.table_name, key_columns=["Site", "Date"]
        )
        self.assertTrue(success)
        self.assertEqual(stats["new_rows_added"], 2)
        
        # Future data for February (new month)
        df_future = pd.DataFrame({
            "Site": ["Site A", "Site B", "Site C"],
            "Date": ["2025-02-01", "2025-02-01", "2025-02-01"],
            "Energy": [110, 210, 310]
        })
        
        success, msg, stats = self.extractor.extract_unique_only(
            df_future, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] Future data append result: {msg}")
        print(f"[INFO] Stats: {stats}")
        
        self.assertTrue(success)
        self.assertEqual(stats["new_rows_added"], 3, "All 3 future rows should be added")
        self.assertEqual(stats["already_in_db"], 0, "No conflicts with existing data")
        
        # Verify total rows in database
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        self.assertEqual(len(df_db), 5, "Should have 5 total rows (2 initial + 3 future)")

    def test_mixed_data_import(self):
        """Test importing data with a mix of new and duplicate entries."""
        # Initial data
        df_initial = pd.DataFrame({
            "Site": ["Site A", "Site B"],
            "Date": ["2025-01-01", "2025-01-01"],
            "Energy": [100, 200]
        })
        self.extractor.extract_unique_only(
            df_initial, self.table_name, key_columns=["Site", "Date"]
        )
        
        # Mixed data: 2 duplicates (Site A/Jan, Site B/Jan) and 2 new (Site A/Feb, Site C/Jan)
        df_mixed = pd.DataFrame({
            "Site": ["Site A", "Site B", "Site A", "Site C"],
            "Date": ["2025-01-01", "2025-01-01", "2025-02-01", "2025-01-01"],
            "Energy": [100, 250, 150, 300]
        })
        
        # First, check for duplicates (flag before adding)
        has_dups, dups_in_input, dups_with_db, summary = self.extractor.check_for_duplicates(
            df_mixed, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] Mixed data duplicate check: {summary}")
        
        self.assertTrue(has_dups)
        self.assertEqual(summary["duplicates_with_db_count"], 2, "2 rows conflict with DB")
        self.assertEqual(summary["new_rows_count"], 2, "2 rows are new")
        
        # Now import (duplicates should be skipped)
        success, msg, stats = self.extractor.extract_unique_only(
            df_mixed, self.table_name, key_columns=["Site", "Date"],
            update_existing=False
        )
        
        print(f"[INFO] Import result: {msg}")
        print(f"[INFO] Import stats: {stats}")
        
        self.assertTrue(success)
        self.assertEqual(stats["new_rows_added"], 2)
        self.assertEqual(stats["already_in_db"], 2)
        
        # Verify database content
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        self.assertEqual(len(df_db), 4, "Should have 4 total rows")

    def test_date_format_handling(self):
        """Test that various date formats are handled correctly."""
        # Test different date formats
        df = pd.DataFrame({
            "Site": ["Site A", "Site B", "Site C"],
            "Date": ["2025-01-15", "15/01/2025", "Jan-25"],  # Different formats
            "Energy": [100, 200, 300]
        })
        
        success, msg, stats = self.extractor.extract_unique_only(
            df, self.table_name, key_columns=["Site", "Date"]
        )
        
        print(f"\n[INFO] Date format handling result: {msg}")
        
        # All rows should be added (different dates after normalization)
        self.assertTrue(success)
        
        # Verify dates are normalized
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        print(f"[INFO] DB dates: {df_db['Date'].tolist()}")
        
        # All dates should now be in Mon-YY format
        for date_val in df_db["Date"].tolist():
            self.assertIsNotNone(date_val)
            # Should match Mon-YY pattern (e.g., "Jan-25")
            self.assertRegex(str(date_val), r'^[A-Z][a-z]{2}-\d{2}$')


class TestSafeConvertDates(unittest.TestCase):
    """Test the safe_convert_dates utility function."""
    
    def test_already_formatted_dates_preserved(self):
        """Dates already in Mon-YY format should be preserved."""
        series = pd.Series(["Jan-25", "Feb-25", "Mar-25"])
        result = safe_convert_dates(series)
        
        self.assertEqual(result.tolist(), ["Jan-25", "Feb-25", "Mar-25"])
    
    def test_iso_dates_converted(self):
        """ISO format dates (YYYY-MM-DD) should be converted."""
        series = pd.Series(["2025-01-15", "2025-02-20", "2025-03-10"])
        result = safe_convert_dates(series)
        
        self.assertEqual(result.tolist(), ["Jan-25", "Feb-25", "Mar-25"])
    
    def test_slash_dates_converted(self):
        """Slash format dates (DD/MM/YYYY) should be converted."""
        series = pd.Series(["15/01/2025", "20/02/2025", "10/03/2025"])
        result = safe_convert_dates(series)
        
        self.assertEqual(result.tolist(), ["Jan-25", "Feb-25", "Mar-25"])
    
    def test_empty_series_handled(self):
        """Empty series should be handled gracefully."""
        series = pd.Series([], dtype=str)
        result = safe_convert_dates(series)
        
        self.assertEqual(len(result), 0)
    
    def test_none_values_preserved(self):
        """None/NaN values should be handled gracefully."""
        series = pd.Series(["2025-01-15", None, "2025-03-10"])
        result = safe_convert_dates(series)
        
        self.assertEqual(result.iloc[0], "Jan-25")
        self.assertEqual(result.iloc[2], "Mar-25")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
