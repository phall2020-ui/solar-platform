"""Tests for Site Onboarding -> O&M automation script logic."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "inverter-data-juggle"
    / "onboard_to_om.py"
)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("onboard_to_om", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import script at {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script()


def test_months_in_range_includes_all_touched_months(script: ModuleType) -> None:
    months = list(script.months_in_range(date(2026, 12, 15), date(2027, 2, 2)))
    assert months == [(2026, 12), (2027, 1), (2027, 2)]


def test_pro_rata_factor_handles_partial_first_and_last_month(script: ModuleType) -> None:
    start = date(2026, 3, 16)
    end = date(2026, 4, 10)
    march = script.pro_rata_factor(2026, 3, start, end)
    april = script.pro_rata_factor(2026, 4, start, end)
    assert march == 0.52
    assert april == 0.33


def test_build_contract_properties_maps_terms(script: ModuleType) -> None:
    site_props = {
        "Site Name": {"title": [{"plain_text": "Fylde Solar"}]},
        "System Size (kWp)": {"number": 30000},
        "Variable Rate (£/kWp)": {"number": 1.9},
        "CCTV Cost (£/yr)": {"number": 500.0},
        "Cleaning Cost (£/yr)": {"number": 250.0},
        "Onboard Date": {"date": {"start": "2026-01-05"}},
        "Contract Term": {"date": {"start": "2026-01-15", "end": "2026-12-31"}},
        "Contract Notes": {"rich_text": [{"type": "text", "text": {"content": "N/A"}}]},
        "SPV": {"select": {"name": "Fylde Solar Ltd"}},
        "PM Days": {"number": 3},
        "PM Day Rate (£)": {"number": 250},
        "Asset Register Link": {"relation": [{"id": "asset-1"}]},
    }

    properties, site_name, contract_start, contract_end, spv_short = script.build_contract_properties(site_props)

    assert site_name == "Fylde Solar"
    assert contract_start == "2026-01-15"
    assert contract_end == "2026-12-31"
    assert spv_short == "FS"
    assert properties["PM Cost (£/yr)"]["number"] == 750.0
    assert properties["SPV"]["select"]["name"] == "FS"
    assert properties["Asset Register Link"]["relation"] == [{"id": "asset-1"}]


def test_build_billing_properties_for_single_month(script: ModuleType) -> None:
    props = script.build_billing_properties(
        contract_page_id="contract-123",
        site_name="Fylde Solar",
        year=2026,
        month=2,
        contract_start=date(2026, 2, 1),
        contract_end=date(2026, 2, 28),
        spv_short="FS",
        provider_name="ClearSol",
        default_tier="Tier 2 (20-30MW)",
    )

    assert props["Billing Entry"]["title"][0]["text"]["content"] == "Fylde Solar - February 2026"
    assert props["O&M Contract"]["relation"] == [{"id": "contract-123"}]
    assert props["Pro-rata Factor"]["number"] == 1.0
    assert props["Billing Period"]["date"]["start"] == "2026-02-01"
    assert props["Billing Period"]["date"]["end"] == "2026-02-28"
    assert props["SPV"]["select"]["name"] == "FS"


def test_create_om_contract_defaults_term_end_to_start(script: ModuleType) -> None:
    site_props = {
        "Site Name": {"title": [{"plain_text": "Test Missing End"}]},
        "Contract Term": {"date": {"start": "2028-02-16"}},
    }

    _, _, contract_start, contract_end, _ = script.create_om_contract(
        notion=None,  # type: ignore[arg-type]
        om_contracts_db_id="dummy",
        site_props=site_props,
        provider_name="ClearSol",
        dry_run=True,
    )

    assert contract_start == "2028-02-16"
    assert contract_end == "2028-02-16"


def test_build_contract_properties_defaults_term_to_onboard_date(script: ModuleType) -> None:
    site_props = {
        "Site Name": {"title": [{"plain_text": "No Contract Term"}]},
        "Onboard Date": {"date": {"start": "2026-03-10"}},
    }

    _, _, contract_start, contract_end, _ = script.build_contract_properties(site_props)
    assert contract_start == "2026-03-10"
    assert contract_end == "2026-03-10"


def test_build_contract_properties_uses_term_years(script: ModuleType) -> None:
    site_props = {
        "Site Name": {"title": [{"plain_text": "Term Years Site"}]},
        "Onboard Date": {"date": {"start": "2026-02-16"}},
        "Contract Term (Years)": {"number": 2},
    }

    _, _, contract_start, contract_end, _ = script.build_contract_properties(site_props)
    assert contract_start == "2026-02-16"
    assert contract_end == "2028-02-16"


def test_set_onboarded_status_if_onboard_date(script: ModuleType) -> None:
    class DummyNotion:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def update_page(self, page_id: str, properties: object) -> None:
            self.calls.append((page_id, properties))

    notion = DummyNotion()
    site_props = {
        "Onboard Date": {"date": {"start": "2026-02-16"}},
        "Onboarding Status": {"status": {"name": "Draft"}},
    }

    script.set_onboarded_status_if_onboard_date(
        notion,
        site_id="site-123",
        site_props=site_props,
        dry_run=False,
    )

    assert len(notion.calls) == 1
    page_id, props = notion.calls[0]
    assert page_id == "site-123"
    assert props == {"Onboarding Status": {"status": {"name": "Onboarded"}}}
