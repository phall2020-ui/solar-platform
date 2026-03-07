from src.solar_platform.analytics.performance_intelligence.expected_generation import calculate_expected_power

def test_calculate_expected_power():
    # Irradiance (W/m2), installed DC (kWp), PR baseline
    result = calculate_expected_power(irradiance_wm2=800, installed_dc_kwp=500, pr_baseline=0.80)
    # Expected: 800 * 500 * 0.8 / 1000 = 320 kW
    assert result == 320.0
