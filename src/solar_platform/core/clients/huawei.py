"""
Huawei FusionSolar Northbound API authentication helpers.

Huawei uses session-based auth: POST to /thirdData/login returns an XSRF-TOKEN
cookie that must be sent as a header on all subsequent requests.

Regional base URLs are exposed so both sync (requests) and async (httpx) callers
can share the same endpoint constants.
"""

from __future__ import annotations

from typing import Optional

import requests

REGIONS: dict[str, str] = {
    "eu5":  "https://eu5.fusionsolar.huawei.com",
    "intl": "https://intl.fusionsolar.huawei.com",
    "cn":   "https://cn.fusionsolar.huawei.com",
    "ap2":  "https://au.fusionsolar.huawei.com",
    "la1":  "https://la1.fusionsolar.huawei.com",
}

DEFAULT_REGION = "intl"


def base_url(region: str = DEFAULT_REGION) -> str:
    """Return the base URL for a given region key (case-insensitive)."""
    return REGIONS.get(region.lower(), REGIONS[DEFAULT_REGION])


def login(
    base_url: str,
    username: str,
    system_code: str,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> Optional[str]:
    """
    Authenticate with the Huawei FusionSolar Northbound API.

    POSTs credentials to ``{base_url}/thirdData/login``, extracts the
    XSRF-TOKEN from the response cookies, and sets it as a session header.

    Args:
        base_url:    Regional base URL (e.g. 'https://eu5.fusionsolar.huawei.com').
        username:    FusionSolar account username.
        system_code: System code (not the user's login password).
        session:     An existing requests.Session to authenticate in-place.
                     A new session is created if None.
        timeout:     Request timeout in seconds.

    Returns:
        The XSRF-TOKEN string if login succeeded, or None on failure.
        The session (passed or created) will have the XSRF-TOKEN header set.
    """
    if session is None:
        session = requests.Session()

    response = session.post(
        f"{base_url}/thirdData/login",
        json={"userName": username, "systemCode": system_code},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    if not (data.get("success", False) or data.get("failCode") == 0):
        return None

    xsrf_token: Optional[str] = response.cookies.get("XSRF-TOKEN")
    if xsrf_token:
        session.headers.update({"XSRF-TOKEN": xsrf_token})

    return xsrf_token
