"""Unit tests for SiteLocationService."""
import pytest
from pathlib import Path

from solar_platform.services.site_locations import SiteLocationService, SiteLocation

REPO_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "site_locations.json"


@pytest.fixture
def service():
    return SiteLocationService(CONFIG_PATH)


def test_all_46_sites_loaded(service):
    assert len(service.get_all_sites()) == 46


def test_coords_are_valid_floats(service):
    for site in service.get_all_sites():
        assert -90 <= site.latitude <= 90
        assert -180 <= site.longitude <= 180


def test_get_site_by_name(service):
    site = service.get_site("Point Lane Solar Farm")
    assert site is not None
    assert site.latitude == pytest.approx(53.88, abs=0.5)  # Lancashire


def test_get_site_unknown_returns_none(service):
    assert service.get_site("Nonexistent Site XYZ") is None


def test_ppa_uniroyal_global_is_wales(service):
    site = service.get_site("PPA Uniroyal Global")
    assert site is not None
    assert site.region == "Wales"


def test_all_sites_have_coords(service):
    sites_with_coords = service.get_sites_with_coords()
    all_sites = service.get_all_sites()
    assert len(sites_with_coords) == len(all_sites)  # all 46 have valid coords


def test_get_sites_by_region(service):
    england = service.get_sites_by_region("England")
    wales = service.get_sites_by_region("Wales")
    assert len(england) > 0
    assert len(wales) >= 1  # at least PPA Uniroyal Global


def test_site_is_frozen_dataclass(service):
    site = service.get_all_sites()[0]
    assert isinstance(site, SiteLocation)
    with pytest.raises(Exception):
        site.name = "mutate attempt"  # type: ignore[misc]


def test_coord_source_strips_underscore(service):
    """_coord_source in JSON should be exposed without leading underscore."""
    for site in service.get_all_sites():
        assert not site.coord_source.startswith("_")


def test_file_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="nonexistent.json"):
        SiteLocationService(tmp_path / "nonexistent.json")
