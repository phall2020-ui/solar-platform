"""
Solis / SolisCloud API client.

Uses HMAC-SHA1 signature-based authentication.
API Documentation: https://www.soliscloud.com/doc
"""

import json
import requests
from datetime import datetime
from typing import List

from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState
from solar_platform.core.clients.solis import build_auth_headers_from_dict, BASE_URL as SOLIS_BASE_URL


class SolisClient(BaseInverterClient):
    """Client for Solis/SolisCloud API."""

    PLATFORM_NAME = "Solis"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_id = config.get('api_id', '')
        self.api_secret = config.get('api_secret', '')
        self.api_url = config.get('api_url', SOLIS_BASE_URL)
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.api_id:
            return False, "Solis API ID is required"
        if not self.api_secret:
            return False, "Solis API Secret is required"
        return True, ""
    
    def _api_request(self, path: str, data: dict) -> dict:
        """Make an authenticated API request."""
        body = json.dumps(data)
        headers = build_auth_headers_from_dict(self.api_id, self.api_secret, data, path)
        
        response = requests.post(
            f"{self.api_url}{path}",
            data=body,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('code') != '0' and result.get('success') is not True:
            raise RuntimeError(f"API error: {result.get('msg', 'Unknown error')}")
        
        return result
    
    def authenticate(self) -> bool:
        """Test authentication by fetching station list."""
        try:
            self._api_request('/v1/api/userStationList', {'pageNo': 1, 'pageSize': 1})
            self._authenticated = True
            return True
        except Exception:
            return False
    
    def get_sites(self) -> List[dict]:
        """Get all stations accessible by this account."""
        try:
            result = self._api_request('/v1/api/userStationList', {'pageNo': 1, 'pageSize': 100})
            
            stations = result.get('data', {}).get('page', {}).get('records', [])
            if not stations:
                stations = result.get('data', {}).get('stationList', [])
            
            return [
                {
                    'id': str(station.get('id', station.get('stationId', ''))),
                    # Prefer stationName, fall back to sno or ID
                    'name': station.get('stationName') or station.get('sno') or f"Station {station.get('id', 'Unknown')}",
                    'dataTimestamp': station.get('dataTimestamp', station.get('updateTime', '')),
                    # Installed capacity in kW (API returns kW or kWp)
                    'capacity': float(station.get('capacity', station.get('installedCapacity', 0)) or 0)
                }
                for station in stations
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get stations: {e}")
    
    def _get_inverter_list(self, station_id: str) -> List[dict]:
        """Get all inverters for a station."""
        result = self._api_request('/v1/api/inverterList', {
            'pageNo': 1,
            'pageSize': 100,
            'stationId': station_id
        })
        
        inverters = result.get('data', {}).get('page', {}).get('records', [])
        if not inverters:
            inverters = result.get('data', {}).get('inverterList', [])
        
        return inverters
    
    def _get_inverter_detail(self, inverter_id: str, inverter_sn: str) -> dict:
        """Get detailed status for an inverter."""
        try:
            result = self._api_request('/v1/api/inverterDetail', {
                'id': inverter_id,
                'sn': inverter_sn
            })
            return result.get('data', {})
        except Exception:
            return {}

    def _get_station_detail(self, station_id: str) -> dict:
        """
        Get station-level detail including meter (grid) data.

        Returns fields such as:
          eToday                    — total generation today (kWh)
          gridSellTodayEnergy       — energy exported/sold to grid today (kWh)
          gridPurchasedTodayEnergy  — energy imported/bought from grid today (kWh)
        """
        try:
            result = self._api_request('/v1/api/stationDetail', {'id': station_id})
            return result.get('data', {})
        except Exception:
            return {}
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific station including all inverters."""
        try:
            # Get inverter list
            inverters_data = self._get_inverter_list(site_id)
            
            inverters = []
            total_power = 0.0
            total_energy = 0.0
            
            for inv in inverters_data:
                inv_id = str(inv.get('id', ''))
                inv_sn = inv.get('sn', inv.get('inverterSn', ''))
                inv_name = inv.get('stationName', inv_sn)
                
                # Get detailed status
                detail = self._get_inverter_detail(inv_id, inv_sn)
                
                # Status mapping: 1=Online, 2=Alarm, 3=Offline
                status_code = inv.get('state', detail.get('state', 0))
                if status_code == 1:
                    state = InverterState.ONLINE
                elif status_code == 2:
                    state = InverterState.WARNING
                elif status_code == 3:
                    state = InverterState.OFFLINE
                else:
                    state = InverterState.UNKNOWN
                
                # Power and energy
                power_kw = float(inv.get('pac', detail.get('pac', 0)))  # Already in kW
                energy_kwh = float(inv.get('eToday', detail.get('eToday', 0)))  # Already in kWh
                
                total_power += power_kw
                total_energy += energy_kwh
                
                inverters.append(InverterStatus(
                    inverter_id=inv_sn,
                    name=inv_name,
                    state=state,
                    power_kw=power_kw,
                    energy_today_kwh=energy_kwh,
                ))
            
            # Get station name, data timestamp, and capacity
            sites = self.get_sites()
            site_name = f"Station {site_id}"
            data_timestamp = None
            installed_capacity = 0.0
            for site in sites:
                if site['id'] == site_id:
                    site_name = site['name']
                    data_timestamp = site.get('dataTimestamp')
                    installed_capacity = site.get('capacity', 0.0)
                    break

            # Fetch station-level meter data (grid export/import)
            station_detail = self._get_station_detail(site_id)
            meter_export = None
            meter_import = None
            if station_detail:
                raw_export = station_detail.get('gridSellTodayEnergy')
                raw_import = station_detail.get('gridPurchasedTodayEnergy')
                if raw_export is not None:
                    try:
                        meter_export = float(raw_export)
                    except (TypeError, ValueError):
                        pass
                if raw_import is not None:
                    try:
                        meter_import = float(raw_import)
                    except (TypeError, ValueError):
                        pass

            return SiteStatus(
                site_id=site_id,
                site_name=site_name,
                platform=self.PLATFORM_NAME,
                inverters=inverters,
                total_power_kw=total_power,
                total_energy_today_kwh=total_energy,
                installed_capacity_kw=installed_capacity,
                checked_at=datetime.now(),
                last_data_time=data_timestamp,
                meter_export_kwh=meter_export,
                meter_import_kwh=meter_import,
            )
            
        except Exception as e:
            return SiteStatus(
                site_id=site_id,
                site_name=f"Station {site_id}",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            )
