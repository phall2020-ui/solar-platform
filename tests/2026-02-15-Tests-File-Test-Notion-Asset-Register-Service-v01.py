"""Tests for Notion-backed asset register integration."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest


def test_get_asset_register_returns_empty_when_disabled() -> None:
    """No outbound request should be attempted when integration is disabled."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="",
        notion_asset_database_id="",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=False,
    )

    service = NotionAssetRegisterService(settings=settings)
    assert service.get_asset_register(force_refresh=True) == []


def test_get_asset_register_parses_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Service should map Notion property payloads to plain Python values."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    payload = {
        "results": [
            {
                "id": "page_1",
                "url": "https://www.notion.so/page_1",
                "properties": {
                    "Plant UID": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "uid-001"}],
                    },
                    "Alias": {
                        "type": "title",
                        "title": [{"plain_text": "Sunny Acres"}],
                    },
                    "Owner": {
                        "type": "select",
                        "select": {"name": "Ampyr"},
                    },
                    "Capacity kW": {
                        "type": "number",
                        "number": 5000,
                    },
                    "Tags": {
                        "type": "multi_select",
                        "multi_select": [{"name": "UK"}, {"name": "Utility"}],
                    },
                },
            }
        ],
        "has_more": False,
        "next_cursor": None,
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        return FakeResponse()

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.post", fake_post)

    service = NotionAssetRegisterService(settings=settings)
    rows = service.get_asset_register(force_refresh=True)

    assert len(rows) == 1
    assert rows[0]["Plant UID"] == "uid-001"
    assert rows[0]["Alias"] == "Sunny Acres"
    assert rows[0]["Owner"] == "Ampyr"
    assert rows[0]["Capacity kW"] == 5000
    assert rows[0]["Tags"] == ["UK", "Utility"]
    assert rows[0]["notion_page_id"] == "page_1"


def test_get_asset_for_plant_matches_uid_then_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lookup should prefer plant UID and fallback to alias."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    service = NotionAssetRegisterService(settings=settings)
    monkeypatch.setattr(
        service,
        "get_asset_register",
        lambda force_refresh=False: [  # noqa: ARG005
            {"Plant UID": "uid-001", "Alias": "Sunny Acres", "Owner": "Ampyr"},
            {"Plant UID": "", "Alias": "Fallback Plant", "Owner": "GridCo"},
        ],
    )

    by_uid = service.get_asset_for_plant("uid-001", "Wrong Alias")
    by_alias = service.get_asset_for_plant("uid-missing", "Fallback Plant")
    missing = service.get_asset_for_plant("uid-missing", "Missing Plant")

    assert by_uid is not None and by_uid["Owner"] == "Ampyr"
    assert by_alias is not None and by_alias["Owner"] == "GridCo"
    assert missing is None


def test_get_asset_register_falls_back_to_data_source_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multi-source Notion databases should be queried via the data-sources API."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    class FakeErrorResponse:
        status_code = 400

        def json(self) -> dict:
            return {
                "additional_data": {
                    "error_type": "multiple_data_sources_for_database",
                }
            }

    database_payload = {
        "data_sources": [
            {"id": "ds_123", "name": "AMPYR Asset Register"},
        ]
    }
    query_payload = {
        "results": [
            {
                "id": "page_1",
                "url": "https://www.notion.so/page_1",
                "properties": {
                    "Plant UID": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "uid-001"}],
                    },
                    "Alias": {
                        "type": "title",
                        "title": [{"plain_text": "Sunny Acres"}],
                    },
                    "PAC Date": {
                        "type": "date",
                        "date": {"start": "2026-03-01"},
                    },
                },
            }
        ],
        "has_more": False,
        "next_cursor": None,
    }

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        if url.endswith("/v1/databases/db_123/query"):
            raise httpx.HTTPStatusError("bad request", request=None, response=FakeErrorResponse())
        assert url.endswith("/v1/data_sources/ds_123/query")
        assert headers["Notion-Version"] == "2025-09-03"
        return FakeResponse(query_payload)

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001, ANN201
        assert url.endswith("/v1/databases/db_123")
        assert headers["Notion-Version"] == "2025-09-03"
        return FakeResponse(database_payload)

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.post", fake_post)
    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.get", fake_get)

    service = NotionAssetRegisterService(settings=settings)
    rows = service.get_asset_register(force_refresh=True)

    assert len(rows) == 1
    assert rows[0]["Plant UID"] == "uid-001"
    assert rows[0]["PAC Date"] == "2026-03-01"


def test_ensure_data_source_match_property_creates_missing_rich_text_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service should add the canonical override field to the primary data source."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    database_payload = {
        "title": [{"plain_text": "AMPYR Asset Register"}],
        "data_sources": [
            {"id": "ds_primary", "name": "AMPYR Asset Register"},
            {"id": "ds_other", "name": "New data source"},
        ],
    }
    data_source_payload = {
        "id": "ds_primary",
        "properties": {
            "Alias": {"id": "title", "name": "Alias", "type": "title"},
        },
    }
    patch_calls: list[tuple[str, dict, dict]] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001, ANN201
        if url.endswith("/v1/databases/db_123"):
            return FakeResponse(database_payload)
        assert url.endswith("/v1/data_sources/ds_primary")
        assert headers["Notion-Version"] == "2025-09-03"
        return FakeResponse(data_source_payload)

    def fake_patch(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        patch_calls.append((url, headers, json))
        return FakeResponse({"id": "ds_primary"})

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.get", fake_get)
    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.patch", fake_patch)

    service = NotionAssetRegisterService(settings=settings)
    result = service.ensure_rich_text_property("Data Source Match")

    assert result is True
    assert len(patch_calls) == 1
    url, headers, payload = patch_calls[0]
    assert url.endswith("/v1/data_sources/ds_primary")
    assert headers["Notion-Version"] == "2025-09-03"
    assert payload == {
        "properties": {
            "Data Source Match": {
                "name": "Data Source Match",
                "type": "rich_text",
                "rich_text": {},
            }
        }
    }


def test_update_page_properties_patches_rich_text_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Page updates should encode plain strings as Notion rich_text payloads."""
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    patch_calls: list[tuple[str, dict, dict]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "page_1"}

    def fake_patch(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        patch_calls.append((url, headers, json))
        return FakeResponse()

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.patch", fake_patch)

    service = NotionAssetRegisterService(settings=settings)
    result = service.update_page_properties(
        "page_1",
        {
            "Data Source Match": "Newfold Farm",
            "Notes": "Confirmed manually",
        },
    )

    assert result is True
    assert len(patch_calls) == 1
    url, headers, payload = patch_calls[0]
    assert url.endswith("/v1/pages/page_1")
    assert headers["Notion-Version"] == "2025-09-03"
    assert payload == {
        "properties": {
            "Data Source Match": {
                "rich_text": [{"type": "text", "text": {"content": "Newfold Farm"}}]
            },
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": "Confirmed manually"}}]
            },
        }
    }


def test_ensure_database_creates_when_title_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_page_id="parent_page_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    post_calls: list[tuple[str, dict, dict]] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        post_calls.append((url, headers, json))
        if url.endswith("/v1/search"):
            return FakeResponse({"results": []})
        assert url.endswith("/v1/databases")
        return FakeResponse({"id": "db_new"})

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.post", fake_post)

    service = NotionAssetRegisterService(settings=settings)
    database_id = service.ensure_database(
        "Solar Copilot Daily Triage",
        {"Asset": {"title": {}}},
    )

    assert database_id == "db_new"
    assert len(post_calls) == 2
    assert post_calls[1][2] == {
        "parent": {"type": "page_id", "page_id": "parent_page_123"},
        "title": [{"type": "text", "text": {"content": "Solar Copilot Daily Triage"}}],
        "properties": {"Asset": {"title": {}}},
    }


def test_upsert_database_page_updates_existing_row_by_match_field(monkeypatch: pytest.MonkeyPatch) -> None:
    from solar_platform.integrations.notion_assets import NotionAssetRegisterService

    settings = SimpleNamespace(
        notion_integration_token="secret_test_token",
        notion_asset_database_id="db_123",
        notion_asset_cache_ttl_seconds=300,
        notion_asset_plant_uid_field="Plant UID",
        notion_asset_alias_field="Alias",
        notion_asset_sync_enabled=True,
    )

    query_payload = {
        "results": [
            {
                "id": "page_existing",
                "url": "https://www.notion.so/page_existing",
                "properties": {
                    "Row Key": {
                        "type": "rich_text",
                        "rich_text": [{"plain_text": "2026-03-07|BAE Fylde|source_unconfigured"}],
                    }
                },
            }
        ],
        "has_more": False,
        "next_cursor": None,
    }
    patch_calls: list[tuple[str, dict, dict]] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        assert url.endswith("/v1/databases/db_triage/query")
        return FakeResponse(query_payload)

    def fake_patch(url, headers=None, json=None, timeout=None):  # noqa: ANN001, ANN201
        patch_calls.append((url, headers, json))
        return FakeResponse({"id": "page_existing"})

    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.post", fake_post)
    monkeypatch.setattr("solar_platform.integrations.notion_assets.httpx.patch", fake_patch)

    service = NotionAssetRegisterService(settings=settings)
    page_id = service.upsert_database_page(
        database_id="db_triage",
        match_field="Row Key",
        match_value="2026-03-07|BAE Fylde|source_unconfigured",
        properties={"Asset": {"title": [{"text": {"content": "BAE Fylde"}}]}},
    )

    assert page_id == "page_existing"
    assert patch_calls == [
        (
            "https://api.notion.com/v1/pages/page_existing",
            {
                "Authorization": "Bearer secret_test_token",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            {"properties": {"Asset": {"title": [{"text": {"content": "BAE Fylde"}}]}}},
        )
    ]
