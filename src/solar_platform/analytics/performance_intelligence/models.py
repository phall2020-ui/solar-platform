from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Site(BaseModel):
    id: str
    name: str
    expected_export_limit_kw: float
    data_quality_tier: int

class TelemetryReading(BaseModel):
    timestamp_utc: datetime
    site_id: str
    asset_id: str
    telemetry_point_id: str
    value: float
    quality_flag: Optional[str] = None
