"""
notion_status_sync.py — Sync solar monitoring status to Notion databases.

After each monitoring run, upserts:
  • Site Monitoring Status  — one row per site (OK / Fault / No Comms)
  • Equipment Status        — one row per inverter, related to its site row

Page IDs are cached in .notion_sync_state.json to avoid re-querying Notion
on every run.

Config (top-level notion: block in config.yaml):

  notion:
    enabled: true
    token: <Notion integration token>
    site_status_database_id: 2f2bec4b302246feb916381c991b632c
    equipment_status_database_id: 9f716d0562ca42538de284c6c972c09e
    # Required only for --seed-notion
    asset_register_database_id: 2d01773a96c0807bb964ce1aff762997
"""

import json
import logging
import requests
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .clients.base import InverterState, SiteStatus
from solar_platform.core import site_registry

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
SYNC_STATE_FILE = ".notion_sync_state.json"

# Maps Inverter Make values (Asset Register) → Platform select option
_MAKE_TO_PLATFORM = {
    "SolarEdge":      "SolarEdge",
    "Huawei":         "Huawei",
    "Solis":          "Solis",
    "Ginlong (Solis)":"Solis",
    "Sungrow":        "Sungrow",
    "SMA":            "SMA",
    "Fronius":        "Other",
    "GoodWe":         "Other",
    "Enphase":        "Other",
    "SolaX":          "Other",
    "Other":          "Other",
}

# Maps monitoring PLATFORM_NAME values → Platform select option
_PLATFORM_NORMALISE = {
    "SolarEdge":   "SolarEdge",
    "Huawei":      "Huawei",
    "FusionSolar": "Huawei",
    "Solis":       "Solis",
    "SolisCloud":  "Solis",
    "Sungrow":     "Sungrow",
    "iSolarCloud": "Sungrow",
    "Juggle":      "Juggle",
    "SMA":         "SMA",
}


class NotionStatusSync:
    """
    Keeps Site Monitoring Status and Equipment Status databases in sync
    with live monitoring data.
    """

    def __init__(self, config: dict):
        notion_cfg = config.get("notion", {})
        self.notion_cfg       = notion_cfg
        self.enabled          = notion_cfg.get("enabled", False)
        self.token            = notion_cfg.get("token", "").strip()
        self.site_db_id       = notion_cfg.get("site_status_database_id", "").strip()
        self.equipment_db_id  = notion_cfg.get("equipment_status_database_id", "").strip()
        self.asset_reg_db_id  = notion_cfg.get("asset_register_database_id", "").strip()
        self.state_file       = Path(notion_cfg.get("sync_state_file", SYNC_STATE_FILE))
        self.logger           = logging.getLogger(__name__)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def sync(self, all_statuses: List[SiteStatus], comm_fails: list) -> None:
        """
        Upsert all site and equipment rows from a completed monitoring run.
        comm_fails: list of (SiteStatus, last_contact_str) tuples.
        Silently skips if notion is not enabled or not fully configured.
        """
        if not self._ready():
            return

        state = self._load_state()
        self._bootstrap_site_cache(state)
        now = datetime.now()
        comm_fail_ids = {s.site_id for s, _ in comm_fails}

        synced_sites = 0
        synced_equipment = 0

        # Group statuses by canonical site name so multi-source sites share one row.
        by_canonical: dict[str, list] = defaultdict(list)
        for site_status in all_statuses:
            # Skip bare platform errors with no useful data
            if site_status.error_message and not site_status.inverters:
                continue
            canonical = (
                site_registry.resolve(site_status.platform, site_status.site_id, site_status.site_name)
                or site_status.site_name
            )
            by_canonical[canonical].append(site_status)

        _STATUS_PRIORITY = {"No Comms": 0, "Fault": 1, "Unknown": 2, "OK": 3}

        for canonical_name, sources in by_canonical.items():
            source_statuses = [self._site_status(s, comm_fail_ids) for s in sources]

            if "OK" in source_statuses:
                combined_status = "OK"
                failing = [
                    s.platform for s, sv in zip(sources, source_statuses) if sv != "OK"
                ]
                notes = f"Source not reporting: {', '.join(failing)}" if failing else None
            else:
                # All sources failing — use the worst status (lowest priority)
                combined_status = min(source_statuses, key=lambda sv: _STATUS_PRIORITY.get(sv, 99))
                notes = None

            # Primary source: prefer the OK one for power/capacity figures
            primary = next(
                (s for s, sv in zip(sources, source_statuses) if sv == "OK"),
                sources[0],
            )

            site_page_id = self._upsert_site(
                primary, canonical_name, combined_status, notes, now, state
            )
            if site_page_id:
                synced_sites += 1

            # Upsert equipment rows for all sources into the same site page
            for site_status in sources:
                for inv in site_status.inverters:
                    inv_status_val = self._inv_status(inv, site_status.site_id, comm_fail_ids)
                    if site_page_id:
                        eq_id = self._upsert_equipment(
                            inv, site_status, site_page_id, inv_status_val, now, state
                        )
                        if eq_id:
                            synced_equipment += 1

        self._save_state(state)
        self.logger.info(
            f"Notion sync: {synced_sites} site(s), {synced_equipment} equipment row(s) updated."
        )

    def seed_from_asset_register(self) -> int:
        """
        Pre-populate Site Monitoring Status with every Operational/Energised site
        from the AMPYR Asset Register. Already-seeded sites are skipped.
        Returns the number of rows created.
        """
        if not self._ready(require_asset_register=True):
            self.logger.warning(
                "Notion seed skipped — ensure notion.enabled, token, all database IDs "
                "and asset_register_database_id are set in config.yaml."
            )
            return 0

        state = self._load_state()
        sites = self._query_asset_register()
        created = 0

        for site in sites:
            name = (site.get("Project Name") or "").strip()
            if not name:
                continue
            cache_key = f"seed_{self._key(name)}"
            if cache_key in state.get("site_pages", {}):
                continue
            page_id = self._create_site_from_asset_register(site)
            if page_id:
                state.setdefault("site_pages", {})[cache_key] = page_id
                created += 1

        self._save_state(state)
        self.logger.info(f"Notion seed: {created} site row(s) created.")
        return created

    # -----------------------------------------------------------------------
    # Status helpers
    # -----------------------------------------------------------------------

    def _site_status(self, site: SiteStatus, comm_fail_ids: set) -> str:
        if site.error_message or site.site_id in comm_fail_ids:
            return "No Comms"
        if site.inverter_count == 0:
            return "Unknown"
        return "OK" if site.is_fully_operational else "Fault"

    def _inv_status(self, inv, site_id: str, comm_fail_ids: set) -> str:
        if site_id in comm_fail_ids:
            return "No Comms"
        if inv.state == InverterState.ONLINE:
            return "OK"
        if inv.state in (InverterState.OFFLINE, InverterState.WARNING):
            return "Fault"
        return "No Comms"

    def _normalise_platform(self, platform: str) -> str:
        return _PLATFORM_NORMALISE.get(platform, "Other")

    def _key(self, text: str) -> str:
        """Stable lowercase cache key from any string."""
        return text.lower().replace(" ", "_").replace("/", "_")[:60]

    # -----------------------------------------------------------------------
    # Upsert: site rows
    # -----------------------------------------------------------------------

    def _upsert_site(
        self,
        site: SiteStatus,
        canonical_name: str,
        status_val: str,
        notes: Optional[str],
        now: datetime,
        state: dict,
    ) -> Optional[str]:
        platform = self._normalise_platform(site.platform)
        cache_key = f"site_{self._key(canonical_name)}"
        pages = state.setdefault("site_pages", {})

        update_props = {
            "Status":             {"select": {"name": status_val}},
            "Platform":           {"select": {"name": platform}},
            "Current Power (kW)": {"number": round(site.total_power_kw, 2)},
            "Last Updated":       {"date":   {"start": now.strftime("%Y-%m-%dT%H:%M:%S")}},
        }
        if site.installed_capacity_kw > 0:
            update_props["Capacity (kWp)"] = {"number": round(site.installed_capacity_kw, 2)}
        if notes:
            update_props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}

        if cache_key in pages:
            self._update_page(pages[cache_key], update_props)
            return pages[cache_key]

        # Not in cache — search Notion for an existing seeded page before creating.
        existing_id = self._search_site_page(canonical_name)
        if existing_id:
            pages[cache_key] = existing_id
            self._update_page(existing_id, update_props)
            return existing_id

        # Genuinely new site — create it.
        create_props = {
            "Site Name": {"title": [{"text": {"content": canonical_name}}]},
            **update_props,
        }
        page_id = self._create_page(self.site_db_id, create_props)
        if page_id:
            pages[cache_key] = page_id
        return page_id

    def _bootstrap_site_cache(self, state: dict) -> None:
        """
        On first run (empty site_pages cache), fetch all existing pages from the
        Site Monitoring Status database and populate the cache keyed by canonical
        name. This ensures monitoring updates land on seeded rows rather than
        creating duplicates.
        Skips if the cache already has entries.
        """
        pages = state.setdefault("site_pages", {})
        if pages:
            return  # already populated

        self.logger.info("Notion: bootstrapping site cache from existing database rows...")
        cursor = None
        loaded = 0
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            try:
                resp = requests.post(
                    f"{NOTION_API}/databases/{self.site_db_id}/query",
                    headers=self._headers(),
                    json=body,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                for page in data.get("results", []):
                    props = page.get("properties", {})
                    title_parts = props.get("Site Name", {}).get("title", [])
                    name = "".join(t.get("plain_text", "") for t in title_parts).strip()
                    if name:
                        cache_key = f"site_{self._key(name)}"
                        if cache_key not in pages:
                            pages[cache_key] = page["id"]
                            loaded += 1
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
            except Exception as e:
                self.logger.warning(f"Notion cache bootstrap failed: {e}")
                break
        self.logger.info(f"Notion: bootstrapped {loaded} site(s) into cache.")

    def _search_site_page(self, site_name: str) -> Optional[str]:
        """Search the Site Monitoring Status database for a page by exact title."""
        try:
            resp = requests.post(
                f"{NOTION_API}/databases/{self.site_db_id}/query",
                headers=self._headers(),
                json={
                    "filter": {
                        "property": "Site Name",
                        "title": {"equals": site_name},
                    },
                    "page_size": 1,
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0]["id"] if results else None
        except Exception as e:
            self.logger.debug(f"Notion site search failed for '{site_name}': {e}")
            return None

    # -----------------------------------------------------------------------
    # Upsert: equipment rows
    # -----------------------------------------------------------------------

    def _upsert_equipment(
        self,
        inv,
        site: SiteStatus,
        site_page_id: str,
        status_val: str,
        now: datetime,
        state: dict,
    ) -> Optional[str]:
        cache_key = f"equip_{self._key(site.site_id)}_{self._key(inv.inverter_id)}"
        pages = state.setdefault("equipment_pages", {})

        update_props = {
            "Status":      {"select": {"name": status_val}},
            "Power (kW)":  {"number": round(inv.power_kw, 2)},
            "Last Updated":{"date":   {"start": now.strftime("%Y-%m-%dT%H:%M:%S")}},
        }
        if inv.error_message:
            update_props["Notes"] = {
                "rich_text": [{"text": {"content": inv.error_message[:200]}}]
            }

        if cache_key in pages:
            self._update_page(pages[cache_key], update_props)
            return pages[cache_key]

        create_props = {
            "Equipment Name": {"title": [{"text": {"content": inv.name or inv.inverter_id}}]},
            "Site":           {"relation": [{"id": site_page_id}]},
            "Type":           {"select": {"name": "Inverter"}},
            "Platform ID":    {"rich_text": [{"text": {"content": inv.inverter_id}}]},
            **update_props,
        }
        page_id = self._create_page(self.equipment_db_id, create_props)
        if page_id:
            pages[cache_key] = page_id
        return page_id

    # -----------------------------------------------------------------------
    # Asset Register seeding
    # -----------------------------------------------------------------------

    def _query_asset_register(self) -> list:
        # The Asset Register uses multiple data sources which the standard
        # /databases/{id}/query endpoint cannot handle (returns 400).
        # Work around by querying each child data source directly.
        child_ids = self.notion_cfg.get(
            "asset_register_data_source_ids",
            ["2d01773a-96c0-8032-aa8e-000be7d21637", "2e31773a-96c0-8027-b16c-000bb6594d33"],
        )
        results = []
        for ds_id in child_ids:
            cursor = None
            while True:
                body = {
                    "filter": {
                        "or": [
                            {"property": "Status", "select": {"equals": "Operational"}},
                            {"property": "Status", "select": {"equals": "Energised"}},
                        ]
                    },
                    "page_size": 100,
                }
                if cursor:
                    body["start_cursor"] = cursor
                try:
                    resp = requests.post(
                        f"{NOTION_API}/databases/{ds_id}/query",
                        headers=self._headers(),
                        json=body,
                        timeout=30,
                    )
                    if resp.status_code == 404:
                        # This child source not accessible — skip silently
                        break
                    resp.raise_for_status()
                    data = resp.json()
                    for page in data.get("results", []):
                        p = page.get("properties", {})
                        results.append({
                            "page_id":       page["id"],
                            "Project Name":  self._get_title(p.get("Project Name", {})),
                            "Country":       self._get_select(p.get("Country", {})),
                            "TIC kWp":       self._get_number(p.get("TIC kWp", {})),
                            "Inverter Make": self._get_multi_select(p.get("Inverter Make", {})),
                            "O&M Contractor":self._get_select(p.get("O&M Contractor", {})),
                        })
                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")
                except Exception as e:
                    self.logger.error(f"Asset Register query failed (source {ds_id}): {e}")
                    break
        return results

    def _create_site_from_asset_register(self, site: dict) -> Optional[str]:
        name       = site.get("Project Name", "")
        country    = site.get("Country") or ""
        capacity   = site.get("TIC kWp") or 0
        contractor = site.get("O&M Contractor") or ""
        page_id    = site.get("page_id", "")

        makes    = site.get("Inverter Make") or []
        platform = next(
            (_MAKE_TO_PLATFORM[m] for m in makes if m in _MAKE_TO_PLATFORM), "Other"
        )

        props: dict = {
            "Site Name": {"title": [{"text": {"content": name}}]},
            "Status":    {"select": {"name": "Unknown"}},
        }
        if country:
            props["Country"]        = {"rich_text": [{"text": {"content": country}}]}
        if contractor:
            props["O&M Contractor"] = {"rich_text": [{"text": {"content": contractor}}]}
        if capacity:
            props["Capacity (kWp)"] = {"number": float(capacity)}
        if platform != "Other":
            props["Platform"]       = {"select": {"name": platform}}
        if page_id:
            props["Asset Register"] = {"relation": [{"id": page_id}]}

        return self._create_page(self.site_db_id, props)

    # -----------------------------------------------------------------------
    # Notion API helpers
    # -----------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization":  f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type":   "application/json",
        }

    def _create_page(self, database_id: str, properties: dict) -> Optional[str]:
        try:
            resp = requests.post(
                f"{NOTION_API}/pages",
                headers=self._headers(),
                json={"parent": {"database_id": database_id}, "properties": properties},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["id"]
        except Exception as e:
            self.logger.warning(f"Notion create page failed: {e}")
            return None

    def _update_page(self, page_id: str, properties: dict) -> None:
        try:
            resp = requests.patch(
                f"{NOTION_API}/pages/{page_id}",
                headers=self._headers(),
                json={"properties": properties},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            self.logger.warning(f"Notion update page {page_id} failed: {e}")

    # -----------------------------------------------------------------------
    # Property extraction helpers (Notion API response format)
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_title(prop: dict) -> str:
        return "".join(p.get("plain_text", "") for p in prop.get("title", []))

    @staticmethod
    def _get_select(prop: dict) -> str:
        sel = prop.get("select") or {}
        return sel.get("name", "")

    @staticmethod
    def _get_number(prop: dict) -> Optional[float]:
        return prop.get("number")

    @staticmethod
    def _get_multi_select(prop: dict) -> list:
        return [o.get("name", "") for o in prop.get("multi_select", [])]

    # -----------------------------------------------------------------------
    # State
    # -----------------------------------------------------------------------

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"site_pages": {}, "equipment_pages": {}}

    def _save_state(self, state: dict) -> None:
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save Notion sync state: {e}")

    def _ready(self, require_asset_register: bool = False) -> bool:
        if not self.enabled:
            return False
        if not self.token:
            self.logger.warning("notion.token not configured.")
            return False
        if not self.site_db_id or not self.equipment_db_id:
            self.logger.warning(
                "notion.site_status_database_id or equipment_status_database_id not configured."
            )
            return False
        if require_asset_register and not self.asset_reg_db_id:
            return False
        return True
