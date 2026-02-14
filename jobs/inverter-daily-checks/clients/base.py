"""
Base client class and data structures for inverter monitoring.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class InverterState(Enum):
    """Possible states for an inverter."""
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    UNKNOWN = "unknown"


@dataclass
class InverterStatus:
    """Status of a single inverter."""
    inverter_id: str
    name: str
    state: InverterState
    power_kw: float = 0.0
    energy_today_kwh: float = 0.0
    last_updated: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def is_operational(self) -> bool:
        return self.state in (InverterState.ONLINE, InverterState.WARNING)
    
    def __post_init__(self):
        """Rule: Show as WARNING if 'ONLINE' but producing < 1kW."""
        if self.state == InverterState.ONLINE and 0.0 <= self.power_kw < 1.0:
            self.state = InverterState.WARNING
            if not self.error_message:
                self.error_message = f"Low power generation: {self.power_kw:.2f} kW"

    @property
    def status_icon(self) -> str:
        icons = {
            InverterState.ONLINE: "✅",
            InverterState.OFFLINE: "❌",
            InverterState.WARNING: "⚠️",
            InverterState.UNKNOWN: "❓",
        }
        return icons.get(self.state, "❓")


@dataclass
class SiteStatus:
    """Status of a site with one or more inverters."""
    site_id: str
    site_name: str
    platform: str
    inverters: List[InverterStatus] = field(default_factory=list)
    total_power_kw: float = 0.0
    total_energy_today_kwh: float = 0.0
    installed_capacity_kw: float = 0.0  # Total installed inverter capacity
    checked_at: datetime = field(default_factory=datetime.now)
    last_data_time: Optional[str] = None  # Last time data was received from inverters
    error_message: Optional[str] = None
    
    @property
    def inverter_count(self) -> int:
        return len(self.inverters)
    
    @property
    def online_count(self) -> int:
        return sum(1 for inv in self.inverters if inv.state == InverterState.ONLINE)
    
    @property
    def offline_count(self) -> int:
        return sum(1 for inv in self.inverters if inv.state == InverterState.OFFLINE)
    
    @property
    def is_fully_operational(self) -> bool:
        return all(inv.is_operational for inv in self.inverters)
    
    @property
    def status_summary(self) -> str:
        if self.error_message:
            return f"❌ ERROR: {self.error_message}"
        if not self.inverters:
            return "❓ No inverters found"
        capacity_str = f"{self.installed_capacity_kw:.1f} kWp" if self.installed_capacity_kw > 0 else f"{self.inverter_count} inverter{'s' if self.inverter_count > 1 else ''}"
        if self.is_fully_operational:
            return f"✅ ONLINE ({capacity_str})"
        return f"⚠️ PARTIAL ({self.online_count}/{self.inverter_count} online, {capacity_str})"


class BaseInverterClient(ABC):
    """
    Abstract base class for inverter platform clients.
    All platform-specific clients must implement these methods.
    """
    
    PLATFORM_NAME: str = "Unknown"
    
    def __init__(self, config: dict):
        """
        Initialize the client with platform-specific configuration.
        
        Args:
            config: Dictionary containing platform credentials and settings
        """
        self.config = config
        self._authenticated = False
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the platform API.
        
        Returns:
            True if authentication was successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_sites(self) -> List[dict]:
        """
        Get list of all sites/plants accessible by this account.
        
        Returns:
            List of dicts with at minimum 'id' and 'name' keys.
        """
        pass
    
    @abstractmethod
    def get_site_status(self, site_id: str) -> SiteStatus:
        """
        Get the current status of a specific site including all inverters.
        
        Args:
            site_id: The platform-specific site identifier
            
        Returns:
            SiteStatus object with current status information
        """
        pass
    
    def get_all_status(self) -> List[SiteStatus]:
        """
        Get status for all accessible sites.
        
        Returns:
            List of SiteStatus objects for all sites
        """
        statuses = []
        try:
            if not self._authenticated:
                if not self.authenticate():
                    return [SiteStatus(
                        site_id="auth_error",
                        site_name="Authentication Failed",
                        platform=self.PLATFORM_NAME,
                        error_message="Failed to authenticate with platform"
                    )]
            
            sites = self.get_sites()
            for site in sites:
                try:
                    status = self.get_site_status(site['id'])
                    statuses.append(status)
                except Exception as e:
                    statuses.append(SiteStatus(
                        site_id=site.get('id', 'unknown'),
                        site_name=site.get('name', 'Unknown Site'),
                        platform=self.PLATFORM_NAME,
                        error_message=str(e)
                    ))
        except Exception as e:
            statuses.append(SiteStatus(
                site_id="error",
                site_name="Error",
                platform=self.PLATFORM_NAME,
                error_message=str(e)
            ))
        
        return statuses
    
    def validate_config(self) -> tuple[bool, str]:
        """
        Validate that required configuration fields are present.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""
