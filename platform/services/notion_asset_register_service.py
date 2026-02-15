"""Notion-backed asset register integration.

Fetches asset metadata from a Notion database and exposes lookup helpers
for matching records to plant UID / alias.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from services.config import Settings, get_settings
from services.logging import get_logger

logger = get_logger("services.notion_asset_register")

_NOTION_API_URL = "https://api.notion.com/v1/databases/{database_id}/query"
_NOTION_API_VERSION = "2022-06-28"


class NotionAssetRegisterService:
    """Read-through cached access to Notion asset register records."""

    def __init__(self, settings: Settings | Any | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache: list[dict[str, Any]] | None = None
        self._cache_ts: float = 0.0

    def is_enabled(self) -> bool:
        """Return True when Notion sync is configured and explicitly enabled."""
        return bool(
            getattr(self._settings, "notion_asset_sync_enabled", False)
            and str(getattr(self._settings, "notion_integration_token", "")).strip()
            and str(getattr(self._settings, "notion_asset_database_id", "")).strip()
        )

    def get_asset_register(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return flattened asset register records from Notion."""
        if not self.is_enabled():
            return []

        ttl = max(int(getattr(self._settings, "notion_asset_cache_ttl_seconds", 300) or 0), 0)
        now = time.monotonic()

        if (
            not force_refresh
            and self._cache is not None
            and ttl > 0
            and (now - self._cache_ts) < ttl
        ):
            return list(self._cache)

        rows = self._query_database()
        self._cache = rows
        self._cache_ts = now
        return list(rows)

    def get_asset_for_plant(self, plant_uid: str, alias: str | None = None) -> dict[str, Any] | None:
        """Return a single asset-register row that matches plant UID or alias."""
        rows = self.get_asset_register()
        uid_field = str(getattr(self._settings, "notion_asset_plant_uid_field", "Plant UID") or "Plant UID")
        alias_field = str(getattr(self._settings, "notion_asset_alias_field", "Alias") or "Alias")

        uid_key = _norm(plant_uid)
        if uid_key:
            for row in rows:
                if _norm(row.get(uid_field)) == uid_key:
                    return row

        alias_key = _norm(alias)
        if alias_key:
            for row in rows:
                if _norm(row.get(alias_field)) == alias_key:
                    return row

        return None

    # ── Internal helpers ──────────────────────────────────────────────

    def _query_database(self) -> list[dict[str, Any]]:
        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        database_id = str(getattr(self._settings, "notion_asset_database_id", "")).strip()

        if not token or not database_id:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": _NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        url = _NOTION_API_URL.format(database_id=database_id)

        rows: list[dict[str, Any]] = []
        cursor: str | None = None

        try:
            while True:
                payload: dict[str, Any] = {"page_size": 100}
                if cursor:
                    payload["start_cursor"] = cursor

                response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
                response.raise_for_status()
                body = response.json()

                for page in body.get("results", []):
                    parsed = _flatten_page(page)
                    if parsed:
                        rows.append(parsed)

                if not body.get("has_more"):
                    break
                cursor = body.get("next_cursor")
                if not cursor:
                    break

            logger.info("notion_asset_register_loaded", rows=len(rows))
            return rows
        except Exception as exc:
            logger.warning("notion_asset_register_load_failed", error=str(exc))
            return []


def _flatten_page(page: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "notion_page_id": page.get("id"),
        "notion_url": page.get("url"),
    }
    properties = page.get("properties", {})
    if not isinstance(properties, dict):
        return result

    for prop_name, prop_value in properties.items():
        if isinstance(prop_name, str) and isinstance(prop_value, dict):
            result[prop_name] = _extract_property_value(prop_value)

    return result


def _extract_property_value(prop: dict[str, Any]) -> Any:
    prop_type = prop.get("type")
    if not isinstance(prop_type, str):
        return None

    if prop_type == "title":
        return _join_rich_text(prop.get("title"))
    if prop_type == "rich_text":
        return _join_rich_text(prop.get("rich_text"))
    if prop_type == "number":
        return prop.get("number")
    if prop_type in {"select", "status"}:
        value = prop.get(prop_type)
        return value.get("name") if isinstance(value, dict) else None
    if prop_type == "multi_select":
        values = prop.get("multi_select") or []
        return [v.get("name") for v in values if isinstance(v, dict) and v.get("name")]
    if prop_type == "checkbox":
        return bool(prop.get("checkbox"))
    if prop_type == "date":
        value = prop.get("date")
        if not isinstance(value, dict):
            return None
        start = value.get("start")
        end = value.get("end")
        if end:
            return {"start": start, "end": end}
        return start
    if prop_type in {"url", "email", "phone_number"}:
        return prop.get(prop_type)
    if prop_type == "people":
        people = prop.get("people") or []
        names: list[str] = []
        for person in people:
            if not isinstance(person, dict):
                continue
            name = person.get("name") or person.get("id")
            if name:
                names.append(str(name))
        return names
    if prop_type == "relation":
        relations = prop.get("relation") or []
        return [r.get("id") for r in relations if isinstance(r, dict) and r.get("id")]
    if prop_type == "formula":
        formula = prop.get("formula")
        if isinstance(formula, dict):
            for key in ("string", "number", "boolean", "date"):
                if key in formula and formula.get(key) is not None:
                    return formula.get(key)
        return None
    if prop_type == "rollup":
        rollup = prop.get("rollup")
        if isinstance(rollup, dict):
            if rollup.get("type") == "array":
                return [
                    _extract_property_value(item)
                    for item in rollup.get("array", [])
                    if isinstance(item, dict)
                ]
            for key in ("number", "date"):
                if key in rollup and rollup.get(key) is not None:
                    return rollup.get(key)
        return None
    if prop_type in {"created_time", "last_edited_time"}:
        return prop.get(prop_type)
    if prop_type == "created_by":
        created_by = prop.get("created_by")
        if isinstance(created_by, dict):
            return created_by.get("name") or created_by.get("id")
        return None
    if prop_type == "last_edited_by":
        edited_by = prop.get("last_edited_by")
        if isinstance(edited_by, dict):
            return edited_by.get("name") or edited_by.get("id")
        return None

    # Unknown / unsupported property type: keep raw value for debugging.
    return prop.get(prop_type)


def _join_rich_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "".join(
        str(item.get("plain_text", ""))
        for item in values
        if isinstance(item, dict)
    ).strip()


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()

