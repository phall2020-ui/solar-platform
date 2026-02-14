"""
Huawei FusionSolar Northbound API client.

Uses session-based authentication with XSRF token.
API Documentation: Available via Huawei upon request
"""

import requests
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState


class HuaweiClient(BaseInverterClient):
    """Client for Huawei FusionSolar Northbound API."""
    
    PLATFORM_NAME = "Huawei FusionSolar"
    
    # Regional endpoints
    REGIONS = {
        'eu5': 'https://eu5.fusionsolar.huawei.com',
        'intl': 'https://intl.fusionsolar.huawei.com',
        'cn': 'https://cn.fusionsolar.huawei.com',
        'ap2': 'https://au.fusionsolar.huawei.com',
        'la1': 'https://la1.fusionsolar.huawei.com',
    }
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        region = config.get('region', 'eu5').lower()
        self.base_url = self.REGIONS.get(region, self.REGIONS['eu5'])
        self.session = requests.Session()
        self._xsrf_token: Optional[str] = None
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.username:
            return False, "Huawei username is required"
        if not self.password:
            return False, "Huawei password is required"
        return True, ""
    
    def authenticate(self) -> bool:
        """Authenticate using the Northbound API login endpoint."""
        try:
            login_url = f"{self.base_url}/thirdData/login"
            payload = {
                'userName': self.username,
                'systemCode': self.password
            }
            
            response = self.session.post(
                login_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success', False) or data.get('failCode') == 0:
                # Get XSRF token from cookies
                self._xsrf_token = response.cookies.get('XSRF-TOKEN')
                if self._xsrf_token:
                    self.session.headers.update({'XSRF-TOKEN': self._xsrf_token})
                self._authenticated = True
                return True
            
            return False
        except Exception:
            return False
    
    def get_sites(self) -> List[dict]:
        """Get all power stations accessible by this account."""
        try:
            response = self.session.post(
                f"{self.base_url}/thirdData/getStationList",
                json={'pageNo': 1, 'pageSize': 100},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get('success', False) and data.get('failCode') != 0:
                raise RuntimeError(f"API error: {data.get('message', 'Unknown error')}")
            
            stations = data.get('data', [])
            if stations is None:
                stations = []
            
            return [
                {
                    'id': str(station.get('stationCode', '')),
                    'name': station.get('stationName', f"Station {station.get('stationCode', 'Unknown')}")
                }
                for station in stations
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get stations: {e}")
    
    def _get_device_list(self, station_code: str) -> List[dict]:
        """Get all devices (inverters) for a station."""
        response = self.session.post(
            f"{self.base_url}/thirdData/getDevList",
            json={'stationCodes': station_code},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        devices = data.get('data', [])
        # Filter for inverters (devTypeId = 1)
        return [d for d in devices if d.get('devTypeId') == 1]
    
    def _get_realtime_data(self, station_code: str, device_ids: List[str]) -> dict:
        """Get real-time data for devices."""
        if not device_ids:
            return {}
        
        response = self.session.post(
            f"{self.base_url}/thirdData/getDevRealKpi",
            json={
                'devIds': ','.join(device_ids),
                'devTypeId': 1  # Inverter type
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        result = {}
        for device_data in data.get('data', []):
            dev_id = str(device_data.get('devId', ''))
            result[dev_id] = device_data.get('dataItemMap', {})
        return result
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific station including all inverters."""
        try:
            # Get device list
            devices = self._get_device_list(site_id)
            device_ids = [str(d.get('id', d.get('devId', ''))) for d in devices]
            
            # Get real-time data
            realtime_data = self._get_realtime_data(site_id, device_ids) if device_ids else {}
            
            inverters = []
            total_power = 0.0
            total_energy = 0.0
            
            for device in devices:
                dev_id = str(device.get('id', device.get('devId', '')))
                dev_name = device.get('devName', f"Inverter {dev_id}")
                dev_status = device.get('devStatus', 0)
                
                # Status mapping: 0=Disconnected, 1=Normal, 2=Alarm
                if dev_status == 1:
                    state = InverterState.ONLINE
                elif dev_status == 2:
                    state = InverterState.WARNING
                elif dev_status == 0:
                    state = InverterState.OFFLINE
                else:
                    state = InverterState.UNKNOWN
                
                # Get power data
                dev_data = realtime_data.get(dev_id, {})
                power_kw = float(dev_data.get('active_power', 0)) / 1000  # W to kW
                energy_kwh = float(dev_data.get('day_cap', 0))  # Already in kWh
                
                total_power += power_kw
                total_energy += energy_kwh
                
                inverters.append(InverterStatus(
                    inverter_id=dev_id,
                    name=dev_name,
                    state=state,
                    power_kw=power_kw,
                    energy_today_kwh=energy_kwh,
                ))
            
            # Get station name from sites list
            sites = self.get_sites()
            site_name = site_id
            for site in sites:
                if site['id'] == site_id:
                    site_name = site['name']
                    break
            
            return SiteStatus(
                site_id=site_id,
                site_name=site_name,
                platform=self.PLATFORM_NAME,
                inverters=inverters,
                total_power_kw=total_power,
                total_energy_today_kwh=total_energy,
                checked_at=datetime.now(),
            )
            
        except Exception as e:
            return SiteStatus(
                site_id=site_id,
                site_name=f"Station {site_id}",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            )
