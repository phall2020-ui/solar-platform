import pytest
from datetime import datetime
from src.solar_platform.analytics.performance_intelligence.models import Site, TelemetryReading

def test_telemetry_reading_creation():
    site = Site(id="site-1", name="Newfold Farm", expected_export_limit_kw=200.0, data_quality_tier=2)
    reading = TelemetryReading(
        timestamp_utc=datetime(2026, 3, 7, 12, 0),
        site_id=site.id,
        asset_id="inv-1",
        telemetry_point_id="export_power_kw",
        value=195.5
    )
    assert reading.value == 195.5
    assert site.name == "Newfold Farm"
