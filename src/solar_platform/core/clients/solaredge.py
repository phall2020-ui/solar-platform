"""
SolarEdge Monitoring API auth helpers.

SolarEdge uses API key authentication passed as a query parameter.
No session or signature needed.
"""

BASE_URL = "https://monitoringapi.solaredge.com"

# Unit conversion constants shared across adapters and clients
WATTS_TO_KW = 1000
WH_TO_KWH = 1000


def auth_params(api_key: str) -> dict:
    """Return the query parameters dict required for SolarEdge API auth."""
    return {"api_key": api_key}
