def calculate_expected_power(irradiance_wm2: float, installed_dc_kwp: float, pr_baseline: float) -> float:
    """Calculate expected power using simple irradiance method A."""
    return (irradiance_wm2 * installed_dc_kwp * pr_baseline) / 1000.0
