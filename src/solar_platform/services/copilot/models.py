"""Shared constants, protocols, dataclasses, and Notion property builders for the copilot package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


SUPPORTED_SOURCES: tuple[str, ...] = (
    "juggle",
    "solaredge",
    "solis",
    "enphase",
    "huawei",
    "sma",
)

PAC_DATE_FIELD_CANDIDATES: tuple[str, ...] = (
    "PAC Date",
    "Pac Date",
    "PAC",
)

ASSET_NAME_FIELD_CANDIDATES: tuple[str, ...] = (
    "Alias",
    "Site",
    "Asset Name",
    "Name",
    "Project Name",
    "Title",
)

PLATFORM_FIELD_CANDIDATES: tuple[str, ...] = (
    "Platform",
    "Monitoring Platform",
    "Inverter Platform",
    "Data Source",
)

SOURCE_IDENTIFIER_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "juggle": ("Plant UID", "Juggle UID", "Juggle Plant UID"),
    "solaredge": ("SolarEdge Site ID", "SolarEdge ID", "SolarEdge Site"),
    "solis": ("Solis Station ID", "Solis Site ID", "Solis ID"),
    "enphase": ("Enphase System ID", "Enphase ID"),
    "huawei": ("Huawei Station ID", "Huawei Plant ID", "Huawei ID"),
    "sma": ("SMA Plant ID", "SMA Site ID", "SMA ID"),
}

DATA_SOURCE_MATCH_FIELD_CANDIDATES: tuple[str, ...] = ("Data Source Match",)

CAPACITY_FIELD_CANDIDATES: tuple[str, ...] = (
    "TIC kWp",
    "Installed Capacity",
    "Installed Capacity kWp",
    "Capacity kWp",
    "Capacity",
    "DC Size kWp",
    "kWp",
)

PPA_RATE_FIELD_CANDIDATES: tuple[str, ...] = (
    "PPA Rate",
    "PPA Rate (GBP/MWh)",
    "PPA Rate (£/MWh)",
    "PPA Rate (p/kWh)",
    "PPA Rate p/kWh",
    "PPA Tariff",
    "Tariff",
    "Tariff Rate",
    "Export Rate",
)

TARGET_PR_ASSUMPTION = 0.80

DEFAULT_DATA_SOURCE_MATCH_UPDATES: dict[str, str] = {
    "BAE Fylde": "Newfold Farm",
    "Bannatyne's Braintree": "PPA Bannatynes Braintree",
    "Bannatyne's Bury St Edmunds": "PPA Bannatynes Bury St Edmunds",
    "Bannatyne's Colchester Kingsford Park": "PPA Bannatynes Colchester Kingsford Park",
    "Bannatyne's Cookridge Hall": "PPA Bannatynes Cookridge Hall",
    "Bannatyne's Darlington": "PPA Bannatynes Darlington Head Office",
    "Bannatyne's Norwich": "PPA Bannatynes Norwich",
    "Bannatyne's Weybridge": "PPA Bannatynes Weybridge",
    "Bannatyne's Wildmoor": "PPA Bannatynes Wildmoor",
    "Blachford": "Blachford UK",
    "Dunham Forest Golf Club": "PPA Dunham Forest Golf Club",
    "Finlay Beverages": "Finlay Beverages",
    "I&N Fabrications": "PPA I&N Fabrications Ltd",
    "Panorama Kitchens": "PPA Panorama Kitchens",
    "Park Hall": "PPA Park Hall",
    "Shawton Engineering": "PPA Shawton Engineering Ltd",
    "Swift Dental Group": "PPA Swift Dental Group",
    "Uniroyal Global": "PPA Uniroyal Global",
    "Valley Hydraulics": "PPA Valley Hydraulics",
    "WALC Adult Learning Centre": "PPA WALC Adult Learning Centre",
    "WALC Leigh College": "PPA WALC Leigh College",
    "WALC Pagefield": "PPA WALC Pagefield",
    "Wienerberger Floplast": "FloPlast",
}

DEFAULT_CONFIRMED_SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "Newfold Farm": {"platform": "juggle", "site_id": "", "juggle_uid": "ERS:00001"},
    "FloPlast": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00032"},
    "Finlay Beverages": {
        "platform": "solis",
        "site_id": "1298491919450070492",
        "juggle_uid": "AMP:00031",
    },
    "Smithy's Mushrooms PH1": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00028"},
    "Smithy's Mushrooms PH2": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00033"},
    "Sofina Foods": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00029"},
    "Casepak (Sunningdale Road)": {"platform": "juggle", "site_id": "", "juggle_uid": "HARP:00024"},
    "Man City FC Training Ground": {"platform": "juggle", "site_id": "", "juggle_uid": "AMP:00019"},
    "Blachford UK": {
        "platform": "solaredge",
        "site_id": "4466155",
        "juggle_uid": "AMP:00024",
    },
    "PPA Park Hall": {"platform": "solaredge", "site_id": "4667531", "juggle_uid": "?"},
    "PPA Panorama Kitchens": {"platform": "solaredge", "site_id": "4519032", "juggle_uid": "?"},
    "PPA Shawton Engineering Ltd": {"platform": "solaredge", "site_id": "2798969", "juggle_uid": "?"},
    "PPA I&N Fabrications Ltd": {"platform": "solaredge", "site_id": "2688590", "juggle_uid": "?"},
    "PPA Swift Dental Group": {"platform": "solaredge", "site_id": "3656221", "juggle_uid": "?"},
    "PPA Uniroyal Global": {"platform": "solaredge", "site_id": "3933004", "juggle_uid": "?"},
    "PPA Valley Hydraulics": {"platform": "solaredge", "site_id": "2626861", "juggle_uid": "?"},
    "PPA WALC Adult Learning Centre": {"platform": "solaredge", "site_id": "3829329", "juggle_uid": "?"},
    "PPA WALC Leigh College": {"platform": "solaredge", "site_id": "3888537", "juggle_uid": "?"},
    "PPA WALC Pagefield": {"platform": "solaredge", "site_id": "3823337", "juggle_uid": "?"},
    "PPA Dunham Forest Golf Club": {"platform": "solaredge", "site_id": "3490228", "juggle_uid": "?"},
    "PPA Bannatynes Braintree": {"platform": "solaredge", "site_id": "4284090", "juggle_uid": "?"},
    "PPA Bannatynes Bury St Edmunds": {"platform": "solaredge", "site_id": "4309872", "juggle_uid": "?"},
    "PPA Bannatynes Colchester Kingsford Park": {"platform": "solaredge", "site_id": "4320553", "juggle_uid": "?"},
    "PPA Bannatynes Cookridge Hall": {"platform": "solaredge", "site_id": "4361798", "juggle_uid": "?"},
    "PPA Bannatynes Darlington Head Office": {"platform": "solaredge", "site_id": "4307544", "juggle_uid": "?"},
    "PPA Bannatynes Norwich": {"platform": "solaredge", "site_id": "4319038", "juggle_uid": "?"},
    "PPA Bannatynes Weybridge": {"platform": "solaredge", "site_id": "4283465", "juggle_uid": "?"},
    "PPA Bannatynes Wildmoor": {"platform": "solaredge", "site_id": "4338522", "juggle_uid": "?"},
}

TRIAGE_DATABASE_TITLE = "Solar Copilot Daily Triage"

DAILY_JSON_DATABASE_TITLE = "Daily JSON"
STARK_DAILY_DATABASE_TITLE = "Stark HH Daily Data"
STARK_FUSION_VARIANCE_THRESHOLD_PCT = 8.0
INVERTER_METER_ALERT_CRITICAL_PCT = 5.0
DEFAULT_PPA_RATE_GBP_MWH = 100.0
DEFAULT_PPA_RATE_SOURCE = "Backstop (10p/kWh)"
SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SOURCE_CREDENTIAL_REPORT_ORDER: tuple[str, ...] = (
    "juggle",
    "solaredge",
    "solis",
    "enphase",
    "huawei",
    "sma",
)

TRIAGE_DATABASE_PROPERTIES: dict[str, dict[str, Any]] = {
    "Asset": {"title": {}},
    "Row Key": {"rich_text": {}},
    "Target Date": {"date": {}},
    "Issue Type": {"rich_text": {}},
    "Severity": {"rich_text": {}},
    "Confidence": {"number": {"format": "number"}},
    "Source Coverage": {"rich_text": {}},
    "Evidence Summary": {"rich_text": {}},
    "Recommended Action": {"rich_text": {}},
    "AM Email Subject": {"rich_text": {}},
    "AM Email Draft": {"rich_text": {}},
    "AM Contact": {"rich_text": {}},
    "AM Contact Email": {"email": {}},
    "Project Name": {"rich_text": {}},
    "Customer": {"rich_text": {}},
    "SPV": {"rich_text": {}},
    "Priority": {"rich_text": {}},
    "Asset Register URL": {"url": {}},
    "Preferred Source": {"rich_text": {}},
    "Match Method": {"rich_text": {}},
    "Has Any Data": {"checkbox": {}},
}

DAILY_JSON_DATABASE_PROPERTIES: dict[str, dict[str, Any]] = {
    "Asset": {"title": {}},
    "Row Key": {"rich_text": {}},
    "Target Date": {"date": {}},
    "PAC Date": {"date": {}},
    "PAC Phase": {"rich_text": {}},
    "PAC In Past": {"checkbox": {}},
    "PAC Date Missing": {"checkbox": {}},
    "Has Any Data": {"checkbox": {}},
    "Sources With Data": {"rich_text": {}},
    "Preferred Source": {"rich_text": {}},
    "Checked Sources": {"rich_text": {}},
    "Match Name": {"rich_text": {}},
    "Match Method": {"rich_text": {}},
    "Match Confidence": {"number": {"format": "number"}},
    "Resolved Source Types": {"rich_text": {}},
    "Resolution Notes": {"rich_text": {}},
    "Project Name": {"rich_text": {}},
    "Customer": {"rich_text": {}},
    "SPV": {"rich_text": {}},
    "Priority": {"rich_text": {}},
    "Site Address": {"rich_text": {}},
    "AM Contact": {"rich_text": {}},
    "AM Contact Email": {"email": {}},
    "Notion Page ID": {"rich_text": {}},
    "Asset Register URL": {"url": {}},
    "Capacity kWp": {"number": {"format": "number"}},
    "PPA Rate (GBP/MWh)": {"number": {"format": "number"}},
    "PPA Rate Source": {"rich_text": {}},
    "Target PR Assumption (%)": {"number": {"format": "percent"}},
    "Target Gen Yesterday (kWh)": {"number": {"format": "number"}},
    "Target Revenue Yesterday (£)": {"number": {"format": "number"}},
    "Target Weather Yesterday": {"rich_text": {}},
    "Target Gen Today (kWh)": {"number": {"format": "number"}},
    "Target Revenue Today (£)": {"number": {"format": "number"}},
    "Target Weather Today": {"rich_text": {}},
    "Target Gen Week (kWh)": {"number": {"format": "number"}},
    "Target Revenue Week (£)": {"number": {"format": "number"}},
    "Target Weather Week": {"rich_text": {}},
    "Target Revenue Message": {"rich_text": {}},
    "Finding Types": {"rich_text": {}},
    "Actionable Finding Count": {"number": {"format": "number"}},
    "Highest Finding Severity": {"rich_text": {}},
    "Curtailment Event Type": {"rich_text": {}},
    "Curtailment Generation Loss (kWh)": {"number": {"format": "number"}},
    "Curtailment Revenue Loss (£)": {"number": {"format": "number"}},
    "Curtailment Confidence": {"number": {"format": "number"}},
    "Curtailment Message": {"rich_text": {}},
    "Irradiance Source": {"rich_text": {}},
    "Irradiance Device ID": {"rich_text": {}},
    "Irradiance Threshold W/m2": {"number": {"format": "number"}},
    "Daylight HH Periods": {"number": {"format": "number"}},
    "Available HH Periods": {"number": {"format": "number"}},
    "Availability (%)": {"number": {"format": "percent"}},
    "Actual Daylight (kWh)": {"number": {"format": "number"}},
    "Expected Daylight (kWh)": {"number": {"format": "number"}},
    "H POA Daylight (kWh/m2)": {"number": {"format": "number"}},
    "PR (%)": {"number": {"format": "percent"}},
    "Irradiance Message": {"rich_text": {}},
    "Inverter Count": {"number": {"format": "number"}},
    "Inverters Reporting": {"number": {"format": "number"}},
    "Best Inverter Availability (%)": {"number": {"format": "percent"}},
    "Worst Inverter Availability (%)": {"number": {"format": "percent"}},
    "Inverter Availability Summary": {"rich_text": {}},
    "Inverter Availability Breakdown": {"rich_text": {}},
    "Juggle Identifier": {"rich_text": {}},
    "Juggle Status": {"rich_text": {}},
    "Juggle Has Data": {"checkbox": {}},
    "Juggle Sample Count": {"number": {"format": "number"}},
    "Juggle Message": {"rich_text": {}},
    "SolarEdge Identifier": {"rich_text": {}},
    "SolarEdge Status": {"rich_text": {}},
    "SolarEdge Has Data": {"checkbox": {}},
    "SolarEdge Sample Count": {"number": {"format": "number"}},
    "SolarEdge Message": {"rich_text": {}},
    "Solis Identifier": {"rich_text": {}},
    "Solis Status": {"rich_text": {}},
    "Solis Has Data": {"checkbox": {}},
    "Solis Sample Count": {"number": {"format": "number"}},
    "Solis Message": {"rich_text": {}},
    "Enphase Identifier": {"rich_text": {}},
    "Enphase Status": {"rich_text": {}},
    "Enphase Has Data": {"checkbox": {}},
    "Enphase Sample Count": {"number": {"format": "number"}},
    "Enphase Message": {"rich_text": {}},
    "Huawei Identifier": {"rich_text": {}},
    "Huawei Status": {"rich_text": {}},
    "Huawei Has Data": {"checkbox": {}},
    "Huawei Sample Count": {"number": {"format": "number"}},
    "Huawei Message": {"rich_text": {}},
    "SMA Identifier": {"rich_text": {}},
    "SMA Status": {"rich_text": {}},
    "SMA Has Data": {"checkbox": {}},
    "SMA Sample Count": {"number": {"format": "number"}},
    "SMA Message": {"rich_text": {}},
    "Trend Days Available": {"number": {"format": "number"}},
    "Trend Gen Mean (kWh)": {"number": {"format": "number"}},
    "Trend Availability Mean (%)": {"number": {"format": "percent"}},
    "Daily JSON": {"rich_text": {}},
}

ASSET_CONTEXT_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "project_name": ("Project Name", "Alias", "Site"),
    "customer_name": ("Customer Registered Name", "Customer", "Customer Name"),
    "spv": ("SPV",),
    "priority": ("Priority",),
    "site_address": ("Site Address", "Billing Address"),
    "am_contact_name": (
        "Asset Manager",
        "AM",
        "AM Name",
        "REGO admin owner",
        "REGO Responsible",
        "Billing Contact",
        "O&M Contact",
        "Site Contact",
    ),
    "am_contact_email": (
        "AM Email",
        "Asset Manager Email",
        "Billing Contact Email",
        "Site Contact Email",
        "O&M Contact Email",
    ),
}


class DailyDataChecker(Protocol):
    async def check_day(self, identifier: str, target_date: date) -> "SourceCheckResult":
        ...


class CurtailmentFetcher(Protocol):
    def get_day_curtailment(
        self,
        plant_uid: str,
        target_date: date,
        ppa_rate_gbp_mwh: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        ...


@dataclass(slots=True)
class SourceCheckResult:
    source: str
    status: str
    identifier: str | None
    target_date: str
    has_data: bool
    sample_count: int = 0
    message: str = ""


@dataclass(slots=True)
class MatchResolution:
    match_name: str = ""
    match_method: str = "unresolved"
    match_confidence: float = 0.0
    resolution_notes: str = ""
    mapping: dict[str, Any] | None = None


@dataclass(slots=True)
class TriageAssessment:
    issue_type: str
    severity: str
    confidence: float
    recommended_action: str
    issue_summary: str
