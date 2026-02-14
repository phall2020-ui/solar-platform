"""
SolarEdge Monitoring API client.

This is the simplest client - just uses an API key as a query parameter.
API Documentation: https://monitoring.solaredge.com/solaredge-web/p/api
"""

import requests
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState

# Unit conversion constants
WATTS_TO_KW = 1000
WH_TO_KWH = 1000


class SolarEdgeClient(BaseInverterClient):
    """Client for SolarEdge Monitoring API."""
    
    PLATFORM_NAME = "SolarEdge"
    BASE_URL = "https://monitoringapi.solaredge.com"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        self.site_ids = config.get('site_ids', [])
        self._sites_cache: Optional[List[dict]] = None
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "SolarEdge API key is required"
        return True, ""
    
    def authenticate(self) -> bool:
        """
        SolarEdge uses API key authentication - no explicit auth step needed.
        We validate by making a test request.
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/sites/list",
                params={'api_key': self.api_key},
                timeout=30
            )
            if response.status_code == 200:
                self._authenticated = True
                return True
            return False
        except Exception:
            return False
    
    def get_sites(self) -> List[dict]:
        """Get all sites accessible by this API key."""
        if self._sites_cache:
            return self._sites_cache
        
        # If specific site IDs are configured, use those
        if self.site_ids:
            self._sites_cache = [{'id': str(sid), 'name': f'Site {sid}'} for sid in self.site_ids]
            # Fetch actual names
            for site in self._sites_cache:
                try:
                    details = self._get_site_details(site['id'])
                    site['name'] = details.get('name', site['name'])
                except Exception:
                    pass
            return self._sites_cache
        
        # Otherwise discover all sites
        try:
            response = requests.get(
                f"{self.BASE_URL}/sites/list",
                params={'api_key': self.api_key},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            sites = data.get('sites', {}).get('site', [])
            if isinstance(sites, dict):
                sites = [sites]
            
            self._sites_cache = [
                {'id': str(site['id']), 'name': site.get('name', f"Site {site['id']}")}
                for site in sites
            ]
            return self._sites_cache
        except Exception as e:
            raise RuntimeError(f"Failed to get sites: {e}")
    
    def _get_site_details(self, site_id: str) -> dict:
        """Get detailed information about a site."""
        response = requests.get(
            f"{self.BASE_URL}/site/{site_id}/details",
            params={'api_key': self.api_key},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get('details', {})
    
    def _get_site_overview(self, site_id: str) -> dict:
        """Get current power and energy overview for a site."""
        response = requests.get(
            f"{self.BASE_URL}/site/{site_id}/overview",
            params={'api_key': self.api_key},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get('overview', {})
    
    def _get_inventory(self, site_id: str) -> dict:
        """Get equipment inventory (inverters, meters, etc.)."""
        response = requests.get(
            f"{self.BASE_URL}/site/{site_id}/inventory",
            params={'api_key': self.api_key},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get('Inventory', {})
    
    def _get_equipment_data(self, site_id: str, serial_number: str) -> dict:
        """Get telemetry data for a specific piece of equipment (inverter)."""
        # Get data for today
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/equipment/{site_id}/{serial_number}/data",
                params={
                    'api_key': self.api_key,
                    'startTime': f"{today} 00:00:00",
                    'endTime': f"{today} 23:59:59"
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json().get('data', {})
        except Exception:
            # If individual equipment data fails, return empty dict
            return {}
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific site including all inverters."""
        try:
            # Get site overview for power data
            overview = self._get_site_overview(site_id)
            current_power = overview.get('currentPower', {}).get('power', 0)
            energy_today = overview.get('lastDayData', {}).get('energy', 0) / WH_TO_KWH
            
            # Get site details
            details = self._get_site_details(site_id)
            site_name = details.get('name', f'Site {site_id}')
            site_status_str = details.get('status', 'Unknown')
            
            # Get inverter inventory
            inventory = self._get_inventory(site_id)
            inverters_data = inventory.get('inverters', [])
            num_inverters = max(len(inverters_data), 1)
            
            inverters = []
            total_inv_power = 0.0
            total_inv_energy = 0.0
            got_telemetry_data = False
            
            for inv in inverters_data:
                serial_number = inv.get('SN', inv.get('serialNumber', 'unknown'))
                inv_name = inv.get('name', inv.get('model', 'Inverter'))
                
                # Try to get individual inverter data
                inv_data = self._get_equipment_data(site_id, serial_number)
                telemetries = inv_data.get('telemetries', [])
                
                # Extract latest power and energy from telemetries
                inv_power_kw = 0.0
                inv_energy_kwh = 0.0
                
                if telemetries:
                    # Get the most recent telemetry data
                    got_telemetry_data = True
                    latest = telemetries[-1]
                    inv_power_kw = latest.get('totalActivePower', 0) / WATTS_TO_KW
                    inv_energy_kwh = latest.get('totalEnergy', 0) / WH_TO_KWH
                    # Note: We use the telemetry data as is, even if power is 0 at night
                else:
                    # No telemetry data available, fall back to site-level split
                    inv_power_kw = current_power / WATTS_TO_KW / num_inverters
                    inv_energy_kwh = energy_today / num_inverters
                
                total_inv_power += inv_power_kw
                total_inv_energy += inv_energy_kwh
                
                # Determine inverter state based on site status and power
                if site_status_str.lower() == 'active':
                    state = InverterState.ONLINE
                elif site_status_str.lower() == 'pending':
                    state = InverterState.WARNING
                else:
                    state = InverterState.OFFLINE
                
                inverters.append(InverterStatus(
                    inverter_id=serial_number,
                    name=inv_name,
                    state=state,
                    power_kw=inv_power_kw,
                    energy_today_kwh=inv_energy_kwh,
                ))
            
            # Use individual inverter data if we got telemetry, otherwise use site-level
            final_power = total_inv_power if got_telemetry_data else current_power / WATTS_TO_KW
            final_energy = total_inv_energy if got_telemetry_data else energy_today
            
            return SiteStatus(
                site_id=site_id,
                site_name=site_name,
                platform=self.PLATFORM_NAME,
                inverters=inverters,
                total_power_kw=final_power,
                total_energy_today_kwh=final_energy,
                checked_at=datetime.now(),
            )
            
        except Exception as e:
            return SiteStatus(
                site_id=site_id,
                site_name=f"Site {site_id}",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            )
