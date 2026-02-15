"""Tests for PlantService + Notion asset register enrichment."""

from __future__ import annotations

import pandas as pd
import pytest


def test_get_plant_includes_asset_register(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plant detail should expose Notion asset metadata when available."""
    from solar_platform.services import plant as plant_service_module

    class FakePlantRepository:
        def get_by_uid(self, plant_uid: str):
            assert plant_uid == "uid-001"
            return {"plant_uid": "uid-001", "alias": "Sunny Acres", "dc_size_kw": 5000}

        def get_all(self):
            return pd.DataFrame([{"plant_uid": "uid-001", "alias": "Sunny Acres"}])

    class FakeReadingsRepository:
        def get_readings(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return pd.DataFrame()

    class FakeNotionAssetRegisterService:
        def get_asset_for_plant(self, plant_uid: str, alias: str | None = None):  # noqa: ARG002
            assert plant_uid == "uid-001"
            return {"Owner": "Ampyr", "EPC": "Example EPC"}

    monkeypatch.setattr(plant_service_module, "PlantRepository", lambda: FakePlantRepository())
    monkeypatch.setattr(plant_service_module, "ReadingsRepository", lambda: FakeReadingsRepository())
    monkeypatch.setattr(
        plant_service_module,
        "NotionAssetRegisterService",
        lambda: FakeNotionAssetRegisterService(),
    )
    monkeypatch.setattr(
        plant_service_module.PlantService,
        "_get_pr",
        lambda self, uid, start, end: 82.1,  # noqa: ARG005
    )

    service = plant_service_module.PlantService()
    plant = service.get_plant("uid-001")

    assert plant is not None
    assert plant["current_pr"] == 82.1
    assert plant["asset_register"]["Owner"] == "Ampyr"
    assert plant["asset_register"]["EPC"] == "Example EPC"


def test_get_all_plants_includes_asset_register(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plant list should include matched asset-register rows."""
    from solar_platform.services import plant as plant_service_module

    class FakePlantRepository:
        def get_by_uid(self, plant_uid: str):  # noqa: ARG002
            return None

        def get_all(self):
            return pd.DataFrame(
                [
                    {"plant_uid": "uid-001", "alias": "Sunny Acres"},
                    {"plant_uid": "uid-002", "alias": "No Match"},
                ]
            )

    class FakeReadingsRepository:
        def get_readings(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return pd.DataFrame()

    class FakeNotionAssetRegisterService:
        def get_asset_for_plant(self, plant_uid: str, alias: str | None = None):  # noqa: ARG002
            if plant_uid == "uid-001":
                return {"Owner": "Ampyr"}
            return None

    monkeypatch.setattr(plant_service_module, "PlantRepository", lambda: FakePlantRepository())
    monkeypatch.setattr(plant_service_module, "ReadingsRepository", lambda: FakeReadingsRepository())
    monkeypatch.setattr(
        plant_service_module,
        "NotionAssetRegisterService",
        lambda: FakeNotionAssetRegisterService(),
    )

    service = plant_service_module.PlantService()
    rows = service.get_all_plants()

    assert len(rows) == 2
    assert rows[0]["asset_register"]["Owner"] == "Ampyr"
    assert "asset_register" not in rows[1]
