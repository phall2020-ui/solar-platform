
import pandas as pd
import numpy as np
from modules.thermal_loss import add_cell_temperature, calculate_thermal_losses

def test_thermal_loss_calculation():
    print("Testing Thermal Loss Calculation...")
    
    # Create mock data
    # 24 hours of data
    timestamps = pd.date_range("2024-01-01", periods=24, freq="h")
    
    data = {
        "timestamp": timestamps,
        "poa": [0]*6 + [200, 400, 600, 800, 1000, 1000, 800, 600, 400, 200] + [0]*8,
        "t_amb": [10]*24, # Constant ambient temp for simplicity
        "p_dc": [0]*6 + [20, 40, 60, 80, 100, 100, 80, 60, 40, 20] + [0]*8 # Mock power output
    }
    
    df = pd.DataFrame(data)
    
    # 1. Test Cell Temp Estimation
    # T_cell = T_amb + (POA / 800) * (NOCT - 20)
    # At POA=800, T_amb=10, NOCT=45: T_cell = 10 + (800/800)*(25) = 35
    df = add_cell_temperature(df, poa_col="poa", tamb_col="t_amb", noct=45.0, out_col="t_cell")
    
    row_800 = df[df["poa"] == 800].iloc[0]
    expected_t_cell = 10 + (800/800) * (45 - 20)
    print(f"At POA=800, T_amb=10: Calculated T_cell={row_800['t_cell']:.2f}, Expected={expected_t_cell:.2f}")
    assert np.isclose(row_800['t_cell'], expected_t_cell), "Cell temp calculation mismatch"
    
    # 2. Test Thermal Losses
    # Gamma = -0.4% / C = -0.004
    # Factor = 1 + (-0.004 * (T_cell - 25))
    # At T_cell=35: Factor = 1 + (-0.004 * 10) = 1 - 0.04 = 0.96
    # p_stc_equiv = p_dc / factor = 80 / 0.96 = 83.333
    # loss = 83.333 - 80 = 3.333
    
    df, loss_pct = calculate_thermal_losses(df, power_col="p_dc", t_cell_col="t_cell", gamma_per_deg=-0.004, ts_col="timestamp")
    
    row_800_res = df[df["poa"] == 800].iloc[0]
    expected_factor = 1.0 + (-0.004) * (35.0 - 25.0)
    expected_p_stc = 80.0 / expected_factor
    expected_loss = expected_p_stc - 80.0
    
    print(f"At T_cell=35: Calculated Factor={row_800_res['temp_factor']:.4f}, Expected={expected_factor:.4f}")
    print(f"At P_dc=80: Calculated Loss kW={row_800_res['thermal_loss_kw']:.4f}, Expected={expected_loss:.4f}")
    
    assert np.isclose(row_800_res['temp_factor'], expected_factor), "Temp factor mismatch"
    assert np.isclose(row_800_res['thermal_loss_kw'], expected_loss), "Loss kW mismatch"
    
    print(f"Total Period Loss %: {loss_pct:.2f}%")
    print("SUCCESS: Logic Verification Successful!")

if __name__ == "__main__":
    try:
        test_thermal_loss_calculation()
    except Exception as e:
        print(f"FAILED: Verification Failed: {e}")
