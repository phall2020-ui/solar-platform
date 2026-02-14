
import unittest
import pandas as pd
import os
import sys

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_access import SolarDataExtractor

class TestUploadLogic(unittest.TestCase):
    def setUp(self):
        self.db_name = "test_upload.db"
        self.extractor = SolarDataExtractor(self.db_name)
        self.table_name = "solar_data"
        # Ensure clean state
        self.extractor.delete_table(self.table_name)

    def tearDown(self):
        # Clean up
        self.extractor.delete_table(self.table_name)
        if os.path.exists(self.db_name):
            try:
                os.remove(self.db_name)
            except:
                pass

    def test_upload_flow(self):
        print("\n--- Starting Upload Logic Test ---")

        # 1. Initial Upload
        print("\nStep 1: Initial Upload (2 rows)")
        df_initial = pd.DataFrame({
            "Site": ["Site A", "Site B"],
            "Date": ["2025-01-01", "2025-01-01"],
            "Energy": [100, 200]
        })
        
        # Convert dates to match app logic (though extract_unique_only handles it too)
        df_initial["Date"] = pd.to_datetime(df_initial["Date"]).dt.strftime("%b-%y")

        success, msg, stats = self.extractor.extract_unique_only(
            df_initial, 
            self.table_name, 
            key_columns=["Site", "Date"],
            update_existing=False
        )
        
        print(f"Result: {msg}")
        print(f"Stats: {stats}")

        self.assertTrue(success)
        self.assertEqual(stats["new_rows_added"], 2)
        self.assertEqual(stats["already_in_db"], 0)

        # Verify DB content
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        self.assertEqual(len(df_db), 2)
        print("\n[DEBUG] DB Content after Step 1:")
        print(df_db)

        # 2. Second Upload (Mixed: Duplicates + New Data)
        print("\nStep 2: Second Upload (2 Duplicates, 2 New)")
        df_new = pd.DataFrame({
            "Site": ["Site A", "Site B", "Site A", "Site C"],
            "Date": ["2025-01-01", "2025-01-01", "2025-02-01", "2025-01-01"],
            "Energy": [100, 250, 150, 300] # Site B has new value (250 vs 200)
        })
        df_new["Date"] = pd.to_datetime(df_new["Date"]).dt.strftime("%b-%y")
        
        print("\n[DEBUG] df_new content:")
        print(df_new)

        success, msg, stats = self.extractor.extract_unique_only(
            df_new, 
            self.table_name, 
            key_columns=["Site", "Date"],
            update_existing=False # Should SKIP duplicates
        )

        print(f"Result: {msg}")
        print(f"Stats: {stats}")

        self.assertTrue(success)
        self.assertEqual(stats["new_rows_added"], 2) # Site A/Feb, Site C/Jan
        self.assertEqual(stats["already_in_db"], 2) # Site A/Jan, Site B/Jan
        
        # Verify DB content
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        print(f"\nTotal rows in DB: {len(df_db)}")
        print(df_db)

        self.assertEqual(len(df_db), 4)
        
        # Verify Site B value is UNCHANGED (because update_existing=False)
        site_b_val = df_db[(df_db["Site"] == "Site B") & (df_db["Date"] == "Jan-25")]["Energy"].iloc[0]
        self.assertEqual(site_b_val, 200, "Existing value should be preserved when update_existing=False")

        # 3. Third Upload (Update Existing)
        print("\nStep 3: Third Upload (Update Site B)")
        df_update = pd.DataFrame({
            "Site": ["Site B"],
            "Date": ["2025-01-01"],
            "Energy": [999] # New value
        })
        df_update["Date"] = pd.to_datetime(df_update["Date"]).dt.strftime("%b-%y")

        success, msg, stats = self.extractor.extract_unique_only(
            df_update, 
            self.table_name, 
            key_columns=["Site", "Date"],
            update_existing=True # Should UPDATE
        )

        print(f"Result: {msg}")
        print(f"Stats: {stats}")

        self.assertTrue(success)
        self.assertEqual(stats["rows_updated"], 1)
        
        # Verify DB content
        _, df_db = self.extractor.query_data(f"SELECT * FROM {self.table_name}")
        site_b_val = df_db[(df_db["Site"] == "Site B") & (df_db["Date"] == "Jan-25")]["Energy"].iloc[0]
        self.assertEqual(site_b_val, 999, "Value should be updated when update_existing=True")

if __name__ == '__main__':
    unittest.main()
