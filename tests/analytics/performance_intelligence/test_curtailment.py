from src.solar_platform.analytics.performance_intelligence.curtailment import detect_curtailment_interval

def test_detect_curtailment_interval():
    # Scenario: Expected = 320kW, Actual Export = 200kW, Setpoint = 200kW
    event = detect_curtailment_interval(
        expected_power_kw=320.0,
        actual_export_kw=200.0,
        controller_active=True,
        interval_hours=0.25
    )
    assert event is not None
    assert event["lost_energy_kwh"] == (320.0 - 200.0) * 0.25
