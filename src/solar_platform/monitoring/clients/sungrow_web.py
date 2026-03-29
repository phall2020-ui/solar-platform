"""
Sungrow iSolarCloud Web Scraper client.

Uses requests to log in via the web portal and scrape inverter data.
This is an alternative to the API approach when you don't have developer API keys.
"""

import requests
import hashlib
import json
import time
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState


class SungrowWebClient(BaseInverterClient):
    """Client for Sungrow iSolarCloud via web login (scraper approach)."""
    
    PLATFORM_NAME = "Sungrow"
    
    # Known appkeys that work with the web portal
    # These are extracted from the iSolarCloud web app
    APPKEY = "B0455FBE7AA0328DB57B59AA729F05D8"
    
    # Regional endpoints
    GATEWAYS = {
        'eu': 'https://gateway.isolarcloud.eu',
        'com': 'https://gateway.isolarcloud.com', 
        'hk': 'https://gateway.isolarcloud.com.hk',
        'au': 'https://augateway.isolarcloud.com',
    }
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        region = config.get('region', 'eu').lower()
        self.base_url = self.GATEWAYS.get(region, self.GATEWAYS['eu'])
        
        self.session = requests.Session()
        self._token: Optional[str] = None
        self._user_id: Optional[str] = None
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.username:
            return False, "Sungrow username/email is required"
        if not self.password:
            return False, "Sungrow password is required"
        return True, ""
    
    def _encrypt_password(self, password: str) -> str:
        """
        Encrypt password using RSA with iSolarCloud's public key.
        Falls back to MD5 if encryption not available.
        """
        # Default iSolarCloud RSA public key (extracted from web app)
        RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCy/rxSeH1Jn3RjmLJWl3WZJk7v
O9ZPjIC/eZ8yJIB63tX9FXlKX2qkMgvGnQzSlqQ+jwmq/6tDz3wOYNtKgLxQhZrV
u1XfzPFMmNA7z3rgQR+9mffQg9vWgpg4EhGnC3yJfH3nB0yvP5v0unQUzJh0bq6z
O8vDC1vJB+5kFFGbrwIDAQAB
-----END PUBLIC KEY-----"""
        
        try:
            from Crypto.PublicKey import RSA
            from Crypto.Cipher import PKCS1_v1_5
            import base64
            
            key = RSA.import_key(RSA_PUBLIC_KEY)
            cipher = PKCS1_v1_5.new(key)
            encrypted = cipher.encrypt(password.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except ImportError:
            # Fallback to MD5 if pycryptodome not available
            return hashlib.md5(password.encode('utf-8')).hexdigest()
        except Exception as e:
            print(f"RSA encryption failed, using MD5: {e}")
            return hashlib.md5(password.encode('utf-8')).hexdigest()
    
    def _api_request(self, endpoint: str, data: dict = None, need_auth: bool = True) -> dict:
        """Make an API request to the iSolarCloud gateway."""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'Content-Type': 'application/json',
            'x-access-key': self.APPKEY,
        }
        
        if need_auth and self._token:
            headers['x-access-token'] = self._token
        
        payload = {
            'appkey': self.APPKEY,
            'sys_code': '901',
            'lang': '_en_US',
            **(data or {})
        }
        
        if self._token and need_auth:
            payload['token'] = self._token
        
        response = self.session.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        # Check for errors
        result_code = result.get('result_code')
        if result_code not in [None, '1', 1, 'E10000']:
            error_msg = result.get('result_msg', result.get('msg', 'Unknown error'))
            raise RuntimeError(f"API error ({result_code}): {error_msg}")
        
        return result
    
    def authenticate(self) -> bool:
        """Authenticate using web portal login endpoint."""
        try:
            # Encrypt the password using RSA
            encrypted_password = self._encrypt_password(self.password)
            
            result = self._api_request(
                '/v1/userService/login',
                {
                    'user_account': self.username,
                    'user_password': encrypted_password,
                },
                need_auth=False
            )
            
            # Extract token from response
            data = result.get('result_data', {})
            self._token = data.get('token')
            self._user_id = data.get('user_id')
            
            if self._token:
                self._authenticated = True
                return True
            
            return False
            
        except Exception as e:
            print(f"Sungrow auth error: {e}")
            return False
    
    def get_sites(self) -> List[dict]:
        """Get all power plants accessible by this account."""
        try:
            result = self._api_request('/v1/powerStationService/getPowerStationList', {
                'page_no': 1,
                'page_size': 100,
                'is_get_ps_remarks': '0',
            })
            
            plants = result.get('result_data', {}).get('pageList', [])
            if not plants:
                plants = result.get('result_data', {}).get('list', [])
            
            return [
                {
                    'id': str(plant.get('ps_id', '')),
                    'name': plant.get('ps_name', f"Plant {plant.get('ps_id', 'Unknown')}"),
                    'capacity': float(plant.get('installed_power_map', {}).get('value', 0) or 0),
                    'status': plant.get('ps_status', 0),
                    'dataTimestamp': plant.get('data_last_time', ''),
                }
                for plant in plants
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get plants: {e}")
    
    def _get_device_list(self, plant_id: str) -> List[dict]:
        """Get all devices (inverters) for a plant."""
        try:
            result = self._api_request('/v1/devService/getDeviceList', {
                'ps_id': plant_id,
            })
            
            devices = result.get('result_data', {}).get('pageList', [])
            if not devices:
                devices = result.get('result_data', {}).get('list', [])
            
            # Filter for inverters (device_type typically 1 or 'inverter')
            inverters = [d for d in devices if d.get('device_type', 0) in [1, '1', 11, '11', 'inverter']]
            
            # If no specific inverters found, return all devices
            return inverters if inverters else devices
        except Exception:
            return []
    
    def _get_plant_realtime(self, plant_id: str) -> dict:
        """Get real-time data for a plant."""
        try:
            result = self._api_request('/v1/powerStationService/getPsDetail', {
                'ps_id': plant_id,
            })
            return result.get('result_data', {})
        except Exception:
            return {}
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific plant including all inverters."""
        try:
            # Get device list
            devices = self._get_device_list(site_id)
            
            # Get plant real-time data
            realtime = self._get_plant_realtime(site_id)
            
            inverters = []
            total_power = 0.0
            total_energy = 0.0
            
            for device in devices:
                dev_sn = str(device.get('device_sn', device.get('sn', device.get('dev_id', ''))))
                dev_name = device.get('device_name', device.get('dev_name', dev_sn))
                dev_status = device.get('device_status', device.get('status', 0))
                
                # Status mapping
                if dev_status in [1, '1', 'normal', 'online', 'running']:
                    state = InverterState.ONLINE
                elif dev_status in [2, '2', 'alarm', 'warning', 'fault']:
                    state = InverterState.WARNING
                elif dev_status in [0, '0', 'offline', 'disconnect', 'standby']:
                    state = InverterState.OFFLINE
                else:
                    state = InverterState.UNKNOWN
                
                # Power data from device
                power_kw = float(device.get('p_ac', device.get('power', 0)) or 0) / 1000
                energy_kwh = float(device.get('e_today', device.get('today_energy', 0)) or 0)
                
                total_power += power_kw
                total_energy += energy_kwh
                
                inverters.append(InverterStatus(
                    inverter_id=dev_sn,
                    name=dev_name,
                    state=state,
                    power_kw=power_kw,
                    energy_today_kwh=energy_kwh,
                ))
            
            # If no device power data, use plant-level data
            if total_power == 0 and realtime:
                total_power = float(realtime.get('curr_power', realtime.get('p_ac', 0)) or 0)
                total_energy = float(realtime.get('today_energy', realtime.get('e_today', 0)) or 0)
            
            # Get plant info
            sites = self.get_sites()
            site_name = f"Plant {site_id}"
            installed_capacity = 0.0
            data_timestamp = None
            for site in sites:
                if site['id'] == site_id:
                    site_name = site['name']
                    installed_capacity = site.get('capacity', 0.0)
                    data_timestamp = site.get('dataTimestamp')
                    break
            
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
            )
            
        except Exception as e:
            return SiteStatus(
                site_id=site_id,
                site_name=f"Plant {site_id}",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            )
