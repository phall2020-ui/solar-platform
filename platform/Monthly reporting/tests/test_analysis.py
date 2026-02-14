import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import SolarDataAnalyzer

class TestSolarDataAnalyzer(unittest.TestCase):
    def setUp(self):
        self.colmap = {
            "actual_gen": "Actual Gen",
            "wab": "WAB",
            "budget_gen": "Budget",
            "pr_actual": "PR Actual",
            "pr_budget": "PR Budget",
            "availability": "Availability",
            "capacity": "Capacity"
        }
        
        self.data = pd.DataFrame({
            "Actual Gen": [100.0],
            "WAB": [110.0],
            "Budget": [120.0],
            "PR Actual": [80.0],
            "PR Budget": [85.0],
            "Availability": [98.0],
            "Capacity": [10.0]
        })

    def test_compute_losses(self):
        analyzer = SolarDataAnalyzer(self.data, self.colmap)
        result = analyzer.compute_losses()
        
        # Check Loss_Total_Tech_kWh = WAB - Actual = 110 - 100 = 10
        self.assertAlmostEqual(result["Loss_Total_Tech_kWh"].iloc[0], 10.0)
        
        # Check Var_Weather_kWh = WAB - Budget = 110 - 120 = -10
        self.assertAlmostEqual(result["Var_Weather_kWh"].iloc[0], -10.0)
        
        # Check Loss_PR_kWh = WAB * (PR_budget - PR_actual)
        # PRs are normalized: 0.85 - 0.80 = 0.05
        # 110 * 0.05 = 5.5
        self.assertAlmostEqual(result["Loss_PR_kWh"].iloc[0], 5.5)
        
        # Check Loss_Avail_kWh = WAB * (0.99 - Availability)
        # Avail normalized: 0.99 - 0.98 = 0.01
        # 110 * 0.01 = 1.1
        self.assertAlmostEqual(result["Loss_Avail_kWh"].iloc[0], 1.1)

if __name__ == '__main__':
    unittest.main()
