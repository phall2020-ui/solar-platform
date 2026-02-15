"""Tests for Notion-backed asset register integration."""

from __future__ import annotations

from types import SimpleNamespace

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

    monkeypatch.setattr("solar_platform.services.notion_asset_register_service.httpx.post", fake_post)

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
