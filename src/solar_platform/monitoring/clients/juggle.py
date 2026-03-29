"""
Juggle Energy API Monitoring Client
===================================

Fetches real-time status and telemetry for ADE monitoring plants.
"""

import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState
from solar_platform.core.clients.juggle import EMIG_BASE_URL, auth_headers

logger = logging.getLogger(__name__)


class JuggleClient(BaseInverterClient):
    """
    Client for the Juggle Energy REST API.
    Maps Juggle 'meters' and 'devices' to InverterStatus for compatibility.
    """

    PLATFORM_NAME = "Juggle"
    BASE_URL = EMIG_BASE_URL

    def authenticate(self) -> bool:
        """Juggle uses token-based auth in headers. Pre-auth is not required."""
        self._authenticated = True
        return True

    def _get_headers(self) -> Dict[str, str]:
        return auth_headers(self.config.get('api_key', ''))

    def get_sites(self) -> List[dict]:
        """List all plants accessible by the API key."""
        url = f"{self.BASE_URL}/plant-list"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            plants = resp.json()
            return [{"id": p['plantUID'], "name": p['name']} for p in plants]
        except Exception as e:
            logger.error(f"Juggle: Failed to fetch plant list: {e}")
            return []

    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get the current status of a specific site."""
        url = f"{self.BASE_URL}/plant/{site_id}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            plant_data = resp.json()
            
            site_name = plant_data.get('name', site_id)
            capacity = float(plant_data.get('installedCapacityWP', 0)) / 1000.0
            
            status = SiteStatus(
                site_id=site_id,
                site_name=site_name,
                platform=self.PLATFORM_NAME,
                installed_capacity_kw=capacity
            )
            
            # Map Juggle meters (inverters/generation meters) to InverterStatus
            for meter in plant_data.get('meters', []):
                emig_id = meter.get('emigId')
                dtype = meter.get('type')
                
                # Filter for generation-related devices if needed
                # For now, we include everything to ensure monitoring coverage
                
                meter_details = self._get_meter_details(emig_id)
                inv_status = self._map_meter_to_inverter_status(meter, meter_details)
                status.inverters.append(inv_status)
                
                if inv_status.state == InverterState.ONLINE:
                    status.total_power_kw += inv_status.power_kw
                    status.total_energy_today_kwh += inv_status.energy_today_kwh
            
            # Set last_data_time based on the most recent reading
            if status.inverters:
                latest_ts = max((inv.last_updated for inv in status.inverters if inv.last_updated), default=None)
                if latest_ts:
                    status.last_data_time = latest_ts.strftime('%Y-%m-%d %H:%M')
                    
            return status
            
        except Exception as e:
            logger.error(f"Juggle: Error fetching status for site {site_id}: {e}")
            raise

    def _get_meter_details(self, emig_id: str) -> Dict[str, Any]:
        """
        Fetch today's readings for a meter and return the latest one.

        The /meter/{id} endpoint returns 500; the correct endpoint is
        /meter/{id}/readings?startDate=YYYYMMDD&endDate=YYYYMMDD.
        Returns the latest reading dict from the readings array, or {} if empty.
        """
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        url = f"{self.BASE_URL}/meter/{emig_id}/readings?startDate={today}&endDate={today}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            readings = resp.json().get('readings', [])
            return readings[-1] if readings else {}
        except Exception as e:
            logger.warning(f"Juggle: Could not fetch readings for meter {emig_id}: {e}")
            return {}

    def _map_meter_to_inverter_status(self, meter_summary: dict, details: dict) -> InverterStatus:
        """Convert Juggle meter data to the standard InverterStatus format."""
        emig_id = meter_summary.get('emigId', 'unknown')
        name = meter_summary.get('description', emig_id)
        
        # Default values
        state = InverterState.UNKNOWN
        power_kw = 0.0
        energy_today_kwh = 0.0
        last_updated = None
        
        if details:
            # Reading is a dict from the /readings endpoint; keys are measurement names.
            # For INVERTER type meters: importActivePower is the inverter output (generation).
            # exportActivePower is used when available (e.g. grid export meters).
            power_field = (
                details.get('exportActivePower') or
                details.get('importActivePower') or
                {}
            )
            if power_field:
                # Negative importActivePower means the meter is exporting (solar generation).
                # Use abs() so both sign conventions report positive generation.
                power_kw = abs(float(power_field.get('value', 0))) / 1000.0

            # Timestamp is at the reading root as an ISO string
            ts_iso = details.get('ts', '')
            if ts_iso:
                try:
                    last_updated = datetime.fromisoformat(ts_iso.replace('Z', '+00:00'))
                except ValueError:
                    pass

            # Determine state based on last updated time
            if last_updated:
                delta = datetime.now(timezone.utc) - last_updated
                if delta.total_seconds() < 3600:  # data within last hour → online
                    state = InverterState.ONLINE
                else:
                    state = InverterState.OFFLINE
            else:
                state = InverterState.OFFLINE
                
        return InverterStatus(
            inverter_id=emig_id,
            name=name,
            state=state,
            power_kw=power_kw,
            energy_today_kwh=energy_today_kwh,
            last_updated=last_updated
        )

    def validate_config(self) -> tuple[bool, str]:
        if not self.config.get('api_key'):
            return False, "JUGGLE_API_KEY is missing in config"
        return True, ""
