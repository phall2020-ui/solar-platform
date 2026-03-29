"""
Inverter monitoring clients for multiple solar platforms.
"""

from .base import BaseInverterClient, InverterStatus, SiteStatus, InverterState
from .solaredge import SolarEdgeClient
from .solaredge_browser import SolarEdgeBrowserClient
from .huawei import HuaweiClient
from .solis import SolisClient
from .sungrow import SungrowClient
from .sungrow_web import SungrowWebClient
from .sungrow_browser import SungrowBrowserClient
from .juggle import JuggleClient

__all__ = [
    'BaseInverterClient',
    'InverterStatus',
    'InverterState',
    'SiteStatus',
    'SolarEdgeClient',
    'SolarEdgeBrowserClient',
    'HuaweiClient',
    'SolisClient',
    'SungrowClient',
    'SungrowWebClient',
    'SungrowBrowserClient',
    'JuggleClient',
]
