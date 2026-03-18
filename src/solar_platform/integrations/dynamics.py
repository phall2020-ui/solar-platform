"""Dynamics 365 CRM integration — Investment Pipeline.

Fetches investment opportunities from the Dynamics 365 / Dataverse API
and maps numeric option-set codes to human-readable labels.

Environment variables required:
    DYNAMICS_CLIENT_ID      – Azure AD app client ID
    DYNAMICS_CLIENT_SECRET  – Azure AD app client secret
    DYNAMICS_TENANT_ID      – Azure AD tenant ID
    DYNAMICS_RESOURCE_URL   – Dataverse environment URL
                              e.g. https://orgXXXXXX.crm11.dynamics.com

Entry point: DynamicsClient.get_opportunities()
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Code → Label mappings ─────────────────────────────────────────────

#: Opportunity status codes (statuscode option-set)
STATUSCODE_LABELS: dict[int, str] = {
    1: "Live",
    2: "On Hold",
    3: "Dead",
}

#: Solar technology type codes (scl_technologytype2 option-set)
TECHNOLOGY_TYPE_LABELS: dict[int, str] = {
    919160000: "Roof",
    919160001: "Ground Mount",
    919160002: "BESS",
    919160003: "Carport",
    919160004: "Wind",
}


def map_statuscode(code: int | None) -> str:
    """Return human-readable status label for a Dynamics statuscode value."""
    if code is None:
        return "Unknown"
    return STATUSCODE_LABELS.get(int(code), f"Unknown ({code})")


def map_technology_type(code: int | None) -> str:
    """Return human-readable technology type label for a scl_technologytype2 value."""
    if code is None:
        return "Unknown"
    return TECHNOLOGY_TYPE_LABELS.get(int(code), f"Unknown ({code})")


# ── Dynamics 365 client ───────────────────────────────────────────────


class DynamicsClient:
    """Lightweight Dynamics 365 Dataverse API client."""

    TOKEN_URL_TEMPLATE = (
        "https://login.microsoftonline.com/{tenant_id}/oauth2/token"
    )
    OPPORTUNITIES_ENTITY = "opportunities"
    OPPORTUNITY_FIELDS = [
        "name",
        "statuscode",
        "closeprobability",
        "estimatedclosedate",
        "scl_technologytype2",
        "scl_grosscapacityac",
        "modifiedon",
    ]

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        resource_url: str | None = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("DYNAMICS_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("DYNAMICS_CLIENT_SECRET", "")
        self.tenant_id = tenant_id or os.environ.get("DYNAMICS_TENANT_ID", "")
        self.resource_url = (resource_url or os.environ.get("DYNAMICS_RESOURCE_URL", "")).rstrip("/")
        self._token: str | None = None

    @property
    def _is_configured(self) -> bool:
        return all([self.client_id, self.client_secret, self.tenant_id, self.resource_url])

    def _get_token(self) -> str:
        """Obtain an OAuth 2.0 bearer token via client credentials flow."""
        url = self.TOKEN_URL_TEMPLATE.format(tenant_id=self.tenant_id)
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "resource": self.resource_url,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _api_get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """Make an authenticated GET request to the Dataverse Web API."""
        if self._token is None:
            self._token = self._get_token()

        url = f"{self.resource_url}/api/data/v9.2/{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Prefer": "odata.include-annotations=*",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 401:
            # Token may have expired — refresh once
            self._token = self._get_token()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = requests.get(url, headers=headers, params=params, timeout=30)

        resp.raise_for_status()
        return resp.json()

    def get_opportunities(self) -> list[dict[str, Any]]:
        """Fetch all opportunities and apply code → label mappings.

        Returns a list of dicts with the following keys:
            name, status, status_code, probability, forecast_close,
            technology_type, technology_type_code,
            gross_capacity_ac, gross_capacity_mw, modified_on
        """
        if not self._is_configured:
            raise RuntimeError(
                "Dynamics 365 credentials are not configured. "
                "Set DYNAMICS_CLIENT_ID, DYNAMICS_CLIENT_SECRET, "
                "DYNAMICS_TENANT_ID, and DYNAMICS_RESOURCE_URL."
            )

        select = ",".join(self.OPPORTUNITY_FIELDS)
        data = self._api_get(
            self.OPPORTUNITIES_ENTITY,
            params={"$select": select, "$orderby": "modifiedon desc"},
        )
        raw_rows: list[dict] = data.get("value", [])
        logger.info("Fetched %d opportunities from Dynamics 365", len(raw_rows))

        return [self._transform_row(row) for row in raw_rows]

    @staticmethod
    def _transform_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map raw Dataverse row to a clean dict with human-readable labels."""
        raw_status = row.get("statuscode")
        raw_tech = row.get("scl_technologytype2")
        raw_capacity_ac = row.get("scl_grosscapacityac") or 0

        return {
            "name": row.get("name", ""),
            "status": map_statuscode(raw_status),
            "status_code": raw_status,
            "probability": row.get("closeprobability"),
            "forecast_close": row.get("estimatedclosedate"),
            "technology_type": map_technology_type(raw_tech),
            "technology_type_code": raw_tech,
            "gross_capacity_ac": raw_capacity_ac,
            "gross_capacity_mw": raw_capacity_ac / 1000.0 if raw_capacity_ac else 0.0,
            "modified_on": row.get("modifiedon"),
        }
