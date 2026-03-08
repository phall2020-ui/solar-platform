"""Notion-backed asset register integration.

Fetches asset metadata from a Notion database and exposes lookup helpers
for matching records to plant UID / alias.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from solar_platform.config import Settings, get_settings
from solar_platform.services.logging import get_logger

logger = get_logger("services.notion_asset_register")

_NOTION_API_URL = "https://api.notion.com/v1/databases/{database_id}/query"
_NOTION_API_VERSION = "2022-06-28"
_NOTION_DATABASE_URL = "https://api.notion.com/v1/databases/{database_id}"
_NOTION_CREATE_DATABASE_URL = "https://api.notion.com/v1/databases"
_NOTION_DATA_SOURCE_URL = "https://api.notion.com/v1/data_sources/{data_source_id}/query"
_NOTION_RETRIEVE_DATA_SOURCE_URL = "https://api.notion.com/v1/data_sources/{data_source_id}"
_NOTION_UPDATE_DATA_SOURCE_URL = "https://api.notion.com/v1/data_sources/{data_source_id}"
_NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
_NOTION_CREATE_PAGE_URL = "https://api.notion.com/v1/pages"
_NOTION_SEARCH_URL = "https://api.notion.com/v1/search"
_NOTION_MULTI_SOURCE_API_VERSION = "2025-09-03"


class NotionAssetRegisterService:
    """Read-through cached access to Notion asset register records."""

    def __init__(self, settings: Settings | Any | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache: list[dict[str, Any]] | None = None
        self._cache_ts: float = 0.0
        self._data_source_id: str | None = None

    def ensure_rich_text_property(self, property_name: str) -> bool:
        """Ensure a rich-text property exists on the primary asset-register data source."""
        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        if not token or not property_name.strip():
            return False

        data_source_id = self._get_primary_data_source_id(token=token)
        if not data_source_id:
            return False

        headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        retrieve_url = _NOTION_RETRIEVE_DATA_SOURCE_URL.format(data_source_id=data_source_id)

        try:
            response = httpx.get(retrieve_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.warning("notion_asset_register_data_source_retrieve_failed", error=str(exc))
            return False

        properties = body.get("properties", {}) if isinstance(body, dict) else {}
        if property_name in properties:
            return True

        payload = {
            "properties": {
                property_name: {
                    "name": property_name,
                    "type": "rich_text",
                    "rich_text": {},
                }
            }
        }
        try:
            response = httpx.patch(
                _NOTION_UPDATE_DATA_SOURCE_URL.format(data_source_id=data_source_id),
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("notion_asset_register_data_source_update_failed", error=str(exc))
            return False

    def update_page_properties(self, page_id: str, properties: dict[str, Any]) -> bool:
        """Patch rich-text properties for a Notion page."""
        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        page_id = str(page_id).strip()
        if not token or not page_id or not properties:
            return False

        payload_properties: dict[str, Any] = {}
        for key, value in properties.items():
            name = str(key).strip()
            text = "" if value is None else str(value).strip()
            if not name:
                continue
            payload_properties[name] = {"rich_text": _build_rich_text_payload(text)}

        if not payload_properties:
            return False

        headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        try:
            response = httpx.patch(
                _NOTION_PAGE_URL.format(page_id=page_id),
                headers=headers,
                json={"properties": payload_properties},
                timeout=30.0,
            )
            response.raise_for_status()
            self._cache = None
            self._cache_ts = 0.0
            return True
        except Exception as exc:
            logger.warning("notion_asset_register_page_update_failed", error=str(exc), page_id=page_id)
            return False

    def find_database_by_title(self, title: str) -> str | None:
        """Return a database ID by exact title match."""
        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        title = str(title).strip()
        if not token or not title:
            return None

        headers = self._headers(version=_NOTION_API_VERSION, token=token)
        payload = {
            "query": title,
            "filter": {"value": "database", "property": "object"},
        }
        try:
            response = httpx.post(_NOTION_SEARCH_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.warning("notion_database_search_failed", error=str(exc), title=title)
            return None

        for result in body.get("results", []):
            if result.get("object") != "database":
                continue
            if _join_rich_text(result.get("title")) == title:
                return str(result.get("id", "")).strip() or None
        return None

    def ensure_database(
        self,
        title: str,
        properties: dict[str, Any],
        parent_page_id: str | None = None,
    ) -> str | None:
        """Find or create a Notion database under the configured parent page."""
        existing = self.find_database_by_title(title)
        if existing:
            return existing

        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        parent_id = str(parent_page_id or getattr(self._settings, "notion_page_id", "")).strip()
        if not parent_id:
            parent_id = self._get_database_parent_page_id(token=token)
        if not token or not parent_id:
            return None

        legacy_headers = self._headers(version=_NOTION_API_VERSION, token=token)
        legacy_payload = {
            "parent": {"type": "page_id", "page_id": parent_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        try:
            response = httpx.post(
                _NOTION_CREATE_DATABASE_URL,
                headers=legacy_headers,
                json=legacy_payload,
                timeout=30.0,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id", "")).strip() or None
        except Exception as exc:
            logger.warning("notion_database_create_legacy_failed", error=str(exc), title=title)

        modern_headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        modern_payload = {
            "parent": {"type": "workspace", "workspace": True},
            "title": [{"type": "text", "text": {"content": title}}],
            "initial_data_source": {"properties": properties},
        }
        try:
            response = httpx.post(
                _NOTION_CREATE_DATABASE_URL,
                headers=modern_headers,
                json=modern_payload,
                timeout=30.0,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id", "")).strip() or None
        except Exception as exc:
            logger.warning("notion_database_create_failed", error=str(exc), title=title)
            return None

    def upsert_database_page(
        self,
        database_id: str,
        match_field: str,
        match_value: str,
        properties: dict[str, Any],
    ) -> str | None:
        """Create or update a page in the given database by matching a flattened field value."""
        token = str(getattr(self._settings, "notion_integration_token", "")).strip()
        database_id = str(database_id).strip()
        if not token or not database_id or not match_field.strip() or not match_value.strip():
            return None

        existing_page_id = self._find_page_id_by_field(
            token=token,
            database_id=database_id,
            match_field=match_field,
            match_value=match_value,
        )
        headers = self._headers(version=_NOTION_API_VERSION, token=token)
        try:
            if existing_page_id:
                response = httpx.patch(
                    _NOTION_PAGE_URL.format(page_id=existing_page_id),
                    headers=headers,
                    json={"properties": properties},
                    timeout=30.0,
                )
            else:
                response = httpx.post(
                    _NOTION_CREATE_PAGE_URL,
                    headers=headers,
                    json={"parent": {"database_id": database_id}, "properties": properties},
                    timeout=30.0,
                )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id", "")).strip() or None
        except Exception as exc:
            logger.warning(
                "notion_database_page_upsert_failed",
                error=str(exc),
                database_id=database_id,
                match_field=match_field,
                match_value=match_value,
            )
            return None

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

        headers = self._headers(version=_NOTION_API_VERSION, token=token)
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
        except httpx.HTTPStatusError as exc:
            if self._should_retry_with_data_sources(exc):
                rows = self._query_via_data_sources(token=token, database_id=database_id)
                if rows:
                    logger.info("notion_asset_register_loaded", rows=len(rows), mode="data_sources")
                return rows
            logger.warning("notion_asset_register_load_failed", error=str(exc))
            return []
        except Exception as exc:
            logger.warning("notion_asset_register_load_failed", error=str(exc))
            return []

    def _query_via_data_sources(self, token: str, database_id: str) -> list[dict[str, Any]]:
        headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        data_source_id = self._get_primary_data_source_id(token=token, database_id=database_id)
        if not data_source_id:
            logger.warning("notion_asset_register_data_source_missing", database_id=database_id)
            return []

        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        url = _NOTION_DATA_SOURCE_URL.format(data_source_id=data_source_id)

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
        except Exception as exc:
            logger.warning("notion_asset_register_data_source_query_failed", error=str(exc))
            return []

        return rows

    def _should_retry_with_data_sources(self, exc: httpx.HTTPStatusError) -> bool:
        response = exc.response
        if response.status_code != 400:
            return False
        try:
            body = response.json()
        except Exception:
            return False
        additional = body.get("additional_data", {}) if isinstance(body, dict) else {}
        return additional.get("error_type") == "multiple_data_sources_for_database"

    def _get_primary_data_source_id(self, token: str, database_id: str | None = None) -> str:
        if self._data_source_id:
            return self._data_source_id

        database_id = str(database_id or getattr(self._settings, "notion_asset_database_id", "")).strip()
        if not token or not database_id:
            return ""

        headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        database_url = _NOTION_DATABASE_URL.format(database_id=database_id)

        try:
            response = httpx.get(database_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.warning("notion_asset_register_data_source_discovery_failed", error=str(exc))
            return ""

        database_title = _join_rich_text(body.get("title")) if isinstance(body, dict) else ""
        data_sources = body.get("data_sources", []) if isinstance(body, dict) else []

        candidates: list[dict[str, Any]] = [
            data_source for data_source in data_sources if isinstance(data_source, dict)
        ]
        preferred_name_key = _norm(database_title)
        if preferred_name_key:
            for data_source in candidates:
                if _norm(data_source.get("name")) == preferred_name_key:
                    self._data_source_id = str(data_source.get("id", "")).strip()
                    return self._data_source_id

        for data_source in candidates:
            data_source_id = str(data_source.get("id", "")).strip()
            if data_source_id:
                self._data_source_id = data_source_id
                return self._data_source_id

        return ""

    def _get_database_parent_page_id(self, token: str, database_id: str | None = None) -> str:
        database_id = str(database_id or getattr(self._settings, "notion_asset_database_id", "")).strip()
        if not token or not database_id:
            return ""

        headers = self._headers(version=_NOTION_MULTI_SOURCE_API_VERSION, token=token)
        database_url = _NOTION_DATABASE_URL.format(database_id=database_id)
        try:
            response = httpx.get(database_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.warning("notion_database_parent_lookup_failed", error=str(exc), database_id=database_id)
            return ""

        parent = body.get("parent", {}) if isinstance(body, dict) else {}
        if not isinstance(parent, dict):
            return ""
        for key in ("page_id", "block_id"):
            value = str(parent.get(key, "")).strip()
            if value:
                return value
        return ""

    def _find_page_id_by_field(
        self,
        token: str,
        database_id: str,
        match_field: str,
        match_value: str,
    ) -> str | None:
        headers = self._headers(version=_NOTION_API_VERSION, token=token)
        cursor: str | None = None
        while True:
            payload: dict[str, Any] = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            try:
                response = httpx.post(
                    _NOTION_API_URL.format(database_id=database_id),
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                body = response.json()
            except Exception as exc:
                logger.warning("notion_database_query_failed", error=str(exc), database_id=database_id)
                return None

            for page in body.get("results", []):
                flattened = _flatten_page(page)
                if _norm(flattened.get(match_field)) == _norm(match_value):
                    return str(page.get("id", "")).strip() or None

            if not body.get("has_more"):
                break
            cursor = body.get("next_cursor")
            if not cursor:
                break

        return None

    @staticmethod
    def _headers(version: str, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        }


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


def _build_rich_text_payload(value: str) -> list[dict[str, Any]]:
    if not value:
        return []
    return [{"type": "text", "text": {"content": value}}]


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()
