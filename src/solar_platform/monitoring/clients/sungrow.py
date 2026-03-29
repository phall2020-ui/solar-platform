"""
Sungrow iSolarCloud API client.

Uses OAuth2 with RSA encryption for credentials.
API Documentation: https://developer.isolarcloud.com
"""

import requests
import hashlib
import json
import time
from datetime import datetime
from typing import List, Optional
from .base import BaseInverterClient, SiteStatus, InverterStatus, InverterState

# Optional: RSA encryption for password (requires pycryptodome)
try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    import base64
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class SungrowClient(BaseInverterClient):
    """Client for Sungrow iSolarCloud API."""
    
    PLATFORM_NAME = "Sungrow"
    BASE_URL = "https://gateway.isolarcloud.com"
    
    # API version and constants
    API_VERSION = "1.0"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.appkey = config.get('appkey', '')
        self.secret = config.get('secret', '')
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.rsa_public_key = config.get('rsa_public_key', '')
        
        self._access_token: Optional[str] = None
        self._user_id: Optional[str] = None
    
    def validate_config(self) -> tuple[bool, str]:
        if not self.appkey:
            return False, "Sungrow AppKey is required"
        if not self.secret:
            return False, "Sungrow Secret is required"
        if not self.username:
            return False, "Sungrow username is required"
        if not self.password:
            return False, "Sungrow password is required"
        return True, ""
    
    def _encrypt_password(self, password: str) -> str:
        """Encrypt password using RSA public key if available."""
        if not HAS_CRYPTO or not self.rsa_public_key:
            # Fallback: return MD5 hash if no RSA key
            return hashlib.md5(password.encode('utf-8')).hexdigest()
        
        try:
            key = RSA.import_key(self.rsa_public_key)
            cipher = PKCS1_v1_5.new(key)
            encrypted = cipher.encrypt(password.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception:
            # Fallback to MD5
            return hashlib.md5(password.encode('utf-8')).hexdigest()
    
    def _generate_sign(self, params: dict) -> str:
        """Generate API signature."""
        # Sort parameters and create signature string
        sorted_params = sorted(params.items())
        sign_string = ''.join(f"{k}{v}" for k, v in sorted_params)
        sign_string += self.secret
        
        return hashlib.md5(sign_string.encode('utf-8')).hexdigest()
    
    def _api_request(self, endpoint: str, params: dict = None, need_auth: bool = True) -> dict:
        """Make an authenticated API request."""
        if params is None:
            params = {}
        
        # Common parameters
        request_params = {
            'appkey': self.appkey,
            'timestamp': str(int(time.time() * 1000)),
            'v': self.API_VERSION,
            **params
        }
        
        if need_auth and self._access_token:
            request_params['token'] = self._access_token
        
        # Generate signature
        request_params['sign'] = self._generate_sign(request_params)
        
        response = requests.post(
            f"{self.BASE_URL}{endpoint}",
            json=request_params,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('result_code') != '1' and result.get('result_code') != 1:
            error_msg = result.get('result_msg', result.get('msg', 'Unknown error'))
            raise RuntimeError(f"API error: {error_msg}")
        
        return result
    
    def authenticate(self) -> bool:
        """Authenticate and obtain access token."""
        try:
            encrypted_password = self._encrypt_password(self.password)
            
            result = self._api_request(
                '/openapi/login',
                {
                    'user_account': self.username,
                    'user_password': encrypted_password,
                },
                need_auth=False
            )
            
            data = result.get('result_data', {})
            self._access_token = data.get('token', data.get('access_token'))
            self._user_id = data.get('user_id')
            
            if self._access_token:
                self._authenticated = True
                return True
            return False
            
        except Exception:
            return False
    
    def get_sites(self) -> List[dict]:
        """Get all power plants accessible by this account."""
        try:
            result = self._api_request('/openapi/getPlantList', {
                'page_no': 1,
                'page_size': 100
            })
            
            plants = result.get('result_data', {}).get('plant_list', [])
            if not plants:
                plants = result.get('result_data', {}).get('pageList', [])
            
            return [
                {
                    'id': str(plant.get('ps_id', plant.get('plant_id', ''))),
                    'name': plant.get('ps_name', plant.get('plant_name', f"Plant"))
                }
                for plant in plants
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to get plants: {e}")
    
    def _get_device_list(self, plant_id: str) -> List[dict]:
        """Get all devices (inverters) for a plant."""
        result = self._api_request('/openapi/getDeviceList', {
            'ps_id': plant_id,
            'device_type': '1'  # Inverter
        })
        
        devices = result.get('result_data', {}).get('device_list', [])
        if not devices:
            devices = result.get('result_data', {}).get('pageList', [])
        
        return devices
    
    def _get_device_realtime(self, device_sn: str) -> dict:
        """Get real-time data for a device."""
        try:
            result = self._api_request('/openapi/getDeviceRealTimeData', {
                'device_sn': device_sn
            })
            return result.get('result_data', {})
        except Exception:
            return {}
    
    def get_site_status(self, site_id: str) -> SiteStatus:
        """Get status of a specific plant including all inverters."""
        try:
            # Get device list
            devices = self._get_device_list(site_id)
            
            inverters = []
            total_power = 0.0
            total_energy = 0.0
            
            for device in devices:
                dev_sn = device.get('device_sn', device.get('sn', ''))
                dev_name = device.get('device_name', dev_sn)
                dev_status = device.get('device_status', device.get('status', 0))
                
                # Status mapping
                if dev_status in [1, '1', 'normal', 'online']:
                    state = InverterState.ONLINE
                elif dev_status in [2, '2', 'alarm', 'warning']:
                    state = InverterState.WARNING
                elif dev_status in [0, '0', 'offline', 'disconnect']:
                    state = InverterState.OFFLINE
                else:
                    state = InverterState.UNKNOWN
                
                # Get real-time data
                realtime = self._get_device_realtime(dev_sn)
                power_kw = float(realtime.get('p_ac', realtime.get('active_power', 0))) / 1000
                energy_kwh = float(realtime.get('e_today', realtime.get('today_energy', 0)))
                
                total_power += power_kw
                total_energy += energy_kwh
                
                inverters.append(InverterStatus(
                    inverter_id=dev_sn,
                    name=dev_name,
                    state=state,
                    power_kw=power_kw,
                    energy_today_kwh=energy_kwh,
                ))
            
            # Get plant name
            sites = self.get_sites()
            site_name = f"Plant {site_id}"
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
                site_name=f"Plant {site_id}",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            )
