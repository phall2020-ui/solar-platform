from typing import Optional, Dict

def detect_curtailment_interval(expected_power_kw: float, actual_export_kw: float, controller_active: bool, interval_hours: float) -> Optional[Dict]:
    """Detects export limited curtailment and calculates loss for an interval."""
    if controller_active and expected_power_kw > actual_export_kw:
        lost_power = expected_power_kw - actual_export_kw
        return {
            "type": "export_limit_curtailment",
            "lost_energy_kwh": lost_power * interval_hours
        }
    return None
