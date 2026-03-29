"""
Juggle Energy API auth helpers.

Juggle uses Bearer token auth — no pre-auth step required.
"""

# The EMIG/Juggle monitoring API used by Solar-Monitoring.
# Note: solar-platform's ingestion adapter targets the newer Juggle platform
# API at https://api.juggle.energy/v1 — these are different endpoints.
EMIG_BASE_URL = "https://www.emig.co.uk/p/api"

# Newer Juggle platform API (used by solar-platform ingestion adapter)
JUGGLE_BASE_URL = "https://app.juggle.energy"


def auth_headers(api_key: str) -> dict:
    """Return the Authorization header for a Juggle API request."""
    return {"Authorization": f"token {api_key}"}
