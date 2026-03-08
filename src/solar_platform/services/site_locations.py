from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CONFIG_PATH_DEFAULT = (
    Path(__file__).parent.parent.parent.parent / "config" / "site_locations.json"
)


@dataclass(frozen=True)
class SiteLocation:
    name: str
    platform: str
    site_id: str
    juggle_uid: str
    latitude: float
    longitude: float
    tilt_deg: float
    azimuth_deg: float
    timezone: str
    region: str
    coord_source: str  # strips leading _ from _coord_source in JSON


class SiteLocationService:
    """Service for loading and querying site location data from config/site_locations.json."""

    def __init__(self, config_path: Path | str = CONFIG_PATH_DEFAULT) -> None:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Site locations config not found at: {config_path}\n"
                "Run the geocoding tool to generate it: tools/geocode_sites.py"
            )

        with config_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        self._sites: dict[str, SiteLocation] = {}
        for entry in raw.get("sites", []):
            site = SiteLocation(
                name=entry["name"],
                platform=entry.get("platform", ""),
                site_id=entry.get("site_id") or "",
                juggle_uid=entry.get("juggle_uid") or "",
                latitude=float(entry["latitude"]),
                longitude=float(entry["longitude"]),
                tilt_deg=float(entry.get("tilt_deg", 20.0)),
                azimuth_deg=float(entry.get("azimuth_deg", 180.0)),
                timezone=entry.get("timezone", "Europe/London"),
                region=entry.get("region", ""),
                coord_source=entry.get("_coord_source", "").lstrip("_"),
            )
            self._sites[site.name] = site

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_sites(self) -> list[SiteLocation]:
        """Return all loaded sites as a list."""
        return list(self._sites.values())

    def get_site(self, name: str) -> Optional[SiteLocation]:
        """Return a SiteLocation by name, or None if not found."""
        return self._sites.get(name)

    def get_sites_by_region(self, region: str) -> list[SiteLocation]:
        """Return all sites whose region matches (case-sensitive)."""
        return [s for s in self._sites.values() if s.region == region]

    def get_sites_with_coords(self) -> list[SiteLocation]:
        """Return sites that have non-None latitude and longitude values."""
        return [
            s
            for s in self._sites.values()
            if s.latitude is not None and s.longitude is not None
        ]
