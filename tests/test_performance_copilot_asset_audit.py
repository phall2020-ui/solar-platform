from __future__ import annotations

import asyncio
from datetime import date, timedelta
import json
from types import SimpleNamespace

import pandas as pd
import pytest


class FakeNotionAssetRegisterService:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def get_asset_register(self, force_refresh: bool = False) -> list[dict[str, object]]:  # noqa: ARG002
        return list(self._rows)


class FakeWritableNotionAssetRegisterService(FakeNotionAssetRegisterService):
    def __init__(self, rows: list[dict[str, object]], ensure_property: bool = True) -> None:
        super().__init__(rows)
        self.ensure_property = ensure_property
        self.updated_pages: list[tuple[str, dict[str, object]]] = []
        self.database_ensures: list[tuple[str, dict[str, object], str | None]] = []
        self.database_property_ensures: list[tuple[str, dict[str, object]]] = []
        self.database_upserts: list[tuple[str, str, str, dict[str, object]]] = []
        self.database_creates: list[tuple[str, dict[str, object]]] = []
        self.database_title_queries: list[str] = []
        self.database_rows_by_id: dict[str, list[dict[str, object]]] = {}
        self.database_rows_by_title: dict[str, list[dict[str, object]]] = {}

    def ensure_rich_text_property(self, property_name: str) -> bool:
        return self.ensure_property and property_name == "Data Source Match"

    def update_page_properties(self, page_id: str, properties: dict[str, object]) -> bool:
        self.updated_pages.append((page_id, properties))
        return True

    def ensure_database(
        self,
        title: str,
        properties: dict[str, object],
        parent_page_id: str | None = None,
    ) -> str | None:
        self.database_ensures.append((title, properties, parent_page_id))
        return "db_triage"

    def ensure_database_properties(self, database_id: str, properties: dict[str, object]) -> bool:
        self.database_property_ensures.append((database_id, properties))
        return True

    def upsert_database_page(
        self,
        database_id: str,
        match_field: str,
        match_value: str,
        properties: dict[str, object],
    ) -> str | None:
        self.database_upserts.append((database_id, match_field, match_value, properties))
        return "page_triage"

    def create_database_page(
        self,
        database_id: str,
        properties: dict[str, object],
    ) -> str | None:
        self.database_creates.append((database_id, properties))
        return "page_daily"

    def find_database_by_title(self, title: str) -> str | None:
        self.database_title_queries.append(title)
        return title if title in self.database_rows_by_title else None

    def query_database_rows(self, database_id: str, filter_payload: dict[str, object] | None = None) -> list[dict[str, object]]:  # noqa: ARG002
        return list(self.database_rows_by_id.get(database_id, []))


class FakeChecker:
    def __init__(self, source: str, has_data: bool, status: str = "ok") -> None:
        self.source = source
        self.has_data = has_data
        self.status = status
        self.calls: list[tuple[str, date]] = []

    async def check_day(self, identifier: str, target_date: date):
        from solar_platform.services.performance_copilot_asset_audit import SourceCheckResult

        self.calls.append((identifier, target_date))
        return SourceCheckResult(
            source=self.source,
            status=self.status,
            identifier=identifier,
            target_date=target_date.isoformat(),
            has_data=self.has_data,
            sample_count=96 if self.has_data else 0,
        )


class FakeDaylightMetricsFetcher:
    def __init__(
        self,
        metrics: dict[str, object] | None = None,
        target_metrics: dict[str, object] | None = None,
    ) -> None:
        self.metrics = metrics or {}
        self.target_metrics = target_metrics or {}
        self.calls: list[tuple[str, date, float | None, dict[str, object]]] = []
        self.target_calls: list[dict[str, object]] = []

    def get_day_metrics(  # noqa: ANN001
        self,
        plant_uid: str,
        target_date: date,
        capacity_kwp: float | None = None,
        **kwargs,
    ):
        self.calls.append((plant_uid, target_date, capacity_kwp, dict(kwargs)))
        return dict(self.metrics)

    async def get_target_metrics(self, **kwargs):  # noqa: ANN003
        self.target_calls.append(dict(kwargs))
        return dict(self.target_metrics)


class FakeCurtailmentFetcher:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.result = result
        self.calls: list[tuple[str, date, float | None, dict[str, object]]] = []

    def get_day_curtailment(  # noqa: ANN001
        self,
        plant_uid: str,
        target_date: date,
        ppa_rate_gbp_mwh: float | None = None,
        **kwargs,
    ):
        self.calls.append((plant_uid, target_date, ppa_rate_gbp_mwh, dict(kwargs)))
        return None if self.result is None else dict(self.result)


class FakePlantRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def get_by_alias(self, alias: str):  # noqa: ANN001
        for row in self._rows:
            if row.get("alias") == alias:
                return dict(row)
        return None

    def get_all(self) -> pd.DataFrame:
        return pd.DataFrame(self._rows)


class FakePlantRepositoryRaising:
    def __init__(self, error: str) -> None:
        self.error = error

    def get_by_alias(self, alias: str):  # noqa: ANN001
        raise RuntimeError(self.error)

    def get_all(self) -> pd.DataFrame:
        raise RuntimeError(self.error)


class FakeReadingsRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, str | None]] = []

    def get_readings(self, plant_uid: str, start=None, end=None, device_id: str | None = None, limit=None):  # noqa: ANN001
        self.calls.append((plant_uid, device_id))
        df = pd.DataFrame(self._rows)
        if not df.empty and device_id is not None and "emig_id" in df.columns:
            df = df[df["emig_id"] == device_id].copy()
        return df


class FakeReadingsRepositoryRaising:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[tuple[str, str | None]] = []

    def get_readings(self, plant_uid: str, start=None, end=None, device_id: str | None = None, limit=None):  # noqa: ANN001
        self.calls.append((plant_uid, device_id))
        raise RuntimeError(self.message)


class FakeArchiveIrradianceFetcher:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def fetch_half_hourly(self, **kwargs):
        self.calls.append(dict(kwargs))
        return pd.DataFrame(self.rows)


class FakeArchiveIrradianceFetcherByDate:
    def __init__(self, rows_by_date: dict[date, list[dict[str, object]]]) -> None:
        self.rows_by_date = rows_by_date
        self.calls: list[dict[str, object]] = []

    def fetch_half_hourly(self, **kwargs):
        self.calls.append(dict(kwargs))
        return pd.DataFrame(self.rows_by_date.get(kwargs["target_date"], []))


class FakeArchiveIrradianceFetcherRaising:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[dict[str, object]] = []

    def fetch_half_hourly(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise RuntimeError(self.message)


class FakeForecastIrradianceFetcher:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def fetch_half_hourly(self, **kwargs):
        self.calls.append(dict(kwargs))
        return pd.DataFrame(self.rows)


def test_get_assets_with_past_pac_date_filters_future_and_missing_dates(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {"Alias": "Live Asset", "PAC Date": "2026-03-01", "Plant UID": "AMP:1"},
            {"Alias": "Future Asset", "PAC Date": "2026-03-20", "Plant UID": "AMP:2"},
            {"Alias": "Missing Pac", "Plant UID": "AMP:3"},
            {"Alias": "Dict Pac", "PAC Date": {"start": "2026-03-07"}, "Plant UID": "AMP:4"},
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    rows = service.get_assets_with_past_pac_date(as_of_date=date(2026, 3, 8))

    assert [row["Alias"] for row in rows] == ["Live Asset", "Dict Pac"]

    filtered_rows = service.get_assets_with_past_pac_date(
        as_of_date=date(2026, 3, 8),
        asset_filter="dict",
    )

    assert [row["Alias"] for row in filtered_rows] == ["Dict Pac"]


def test_get_assets_for_daily_audit_includes_all_rows_and_labels_pac_phase(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {"Alias": "Post PAC", "PAC Date": "2026-03-01", "Plant UID": "AMP:1"},
            {"Alias": "Pre PAC", "PAC Date": "2026-03-20", "Plant UID": "AMP:2"},
            {"Alias": "Unknown PAC", "Plant UID": "AMP:3"},
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    rows = service.get_assets_for_daily_audit(as_of_date=date(2026, 3, 8))

    assert [row["Alias"] for row in rows] == ["Post PAC", "Pre PAC", "Unknown PAC"]
    assert [row["_pac_phase"] for row in rows] == ["post_pac", "pre_pac", "unknown"]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_normalises_ppa_rate_to_gbp_per_mwh(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Cromwell Tools",
                "PAC Date": "2026-03-01",
                "PPA Rate (p/kWh)": "8.5",
                "TIC kWp": "500",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": FakeChecker("juggle", has_data=False, status="no_data")},
        daylight_metrics_fetcher=FakeDaylightMetricsFetcher(),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))
    row = dataset[0]

    assert row["ppa_rate_gbp_mwh"] == pytest.approx(85.0)
    assert row["ppa_rate_source"] == "PPA Rate (p/kWh)"


@pytest.mark.asyncio
async def test_build_yesterday_dataset_uses_backstop_ppa_rate_when_missing(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    class RevenueEchoFetcher(FakeDaylightMetricsFetcher):
        async def get_target_metrics(self, **kwargs):  # noqa: ANN003
            self.target_calls.append(dict(kwargs))
            rate = kwargs["ppa_rate_gbp_mwh"]
            return {
                "target_gen_yesterday_kwh": 10.0,
                "target_revenue_yesterday_gbp": (10.0 / 1000.0) * rate,
                "target_weather_yesterday": "archive",
                "target_gen_today_kwh": 12.0,
                "target_revenue_today_gbp": (12.0 / 1000.0) * rate,
                "target_weather_today": "forecast",
                "target_gen_week_kwh": 70.0,
                "target_revenue_week_gbp": (70.0 / 1000.0) * rate,
                "target_weather_week": "archive+forecast",
                "target_revenue_message": "",
            }

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Finlay Beverages",
                "PAC Date": "2026-03-01",
                "TIC kWp": "500",
            },
        ]
    )

    fetcher = RevenueEchoFetcher()
    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": FakeChecker("juggle", has_data=False, status="no_data")},
        daylight_metrics_fetcher=fetcher,
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))
    row = dataset[0]

    assert row["ppa_rate_gbp_mwh"] == pytest.approx(100.0)
    assert row["ppa_rate_source"] == "Backstop (10p/kWh)"
    assert row["target_revenue_yesterday_gbp"] == pytest.approx(1.0)
    assert row["target_revenue_today_gbp"] == pytest.approx(1.2)
    assert row["target_revenue_week_gbp"] == pytest.approx(7.0)
    assert "Using Backstop (10p/kWh)" in row["target_revenue_message"]


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_builds_target_generation_and_revenue() -> None:
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    archive_rows_by_date = {
        date(2026, 3, 2): [{"hh_ts": "2026-03-02T12:00:00Z", "poa_interval_kwh_m2": 0.10, "poa_wm2": 200.0}],
        date(2026, 3, 3): [{"hh_ts": "2026-03-03T12:00:00Z", "poa_interval_kwh_m2": 0.10, "poa_wm2": 200.0}],
        date(2026, 3, 4): [{"hh_ts": "2026-03-04T12:00:00Z", "poa_interval_kwh_m2": 0.10, "poa_wm2": 200.0}],
        date(2026, 3, 5): [{"hh_ts": "2026-03-05T12:00:00Z", "poa_interval_kwh_m2": 0.10, "poa_wm2": 200.0}],
        date(2026, 3, 6): [{"hh_ts": "2026-03-06T12:00:00Z", "poa_interval_kwh_m2": 0.10, "poa_wm2": 200.0}],
        date(2026, 3, 7): [{"hh_ts": "2026-03-07T12:00:00Z", "poa_interval_kwh_m2": 0.15, "poa_wm2": 300.0}],
    }
    forecast_rows = [
        {"hh_ts": "2026-03-08T12:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 400.0},
        {"hh_ts": "2026-03-09T12:00:00Z", "poa_interval_kwh_m2": 0.25, "poa_wm2": 500.0},
    ]

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=FakePlantRepository([]),
        readings_repository=FakeReadingsRepository([]),
        site_location_service=SimpleNamespace(
            get_site=lambda name: SimpleNamespace(
                name=name,
                latitude=53.0,
                longitude=-2.0,
                tilt_deg=20.0,
                azimuth_deg=180.0,
                timezone="Europe/London",
            ),
            get_all_sites=lambda: [],
        ),
        archive_irradiance_fetcher=FakeArchiveIrradianceFetcherByDate(archive_rows_by_date),
        forecast_irradiance_fetcher=FakeForecastIrradianceFetcher(forecast_rows),
        runtime_today=date(2026, 3, 8),
    )

    metrics = await fetcher.get_target_metrics(
        reference_date=date(2026, 3, 8),
        capacity_kwp=100.0,
        ppa_rate_gbp_mwh=90.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
    )

    assert metrics["target_pr_assumption_ratio"] == pytest.approx(0.8)
    assert metrics["target_gen_yesterday_kwh"] == pytest.approx(12.0)
    assert metrics["target_revenue_yesterday_gbp"] == pytest.approx(1.08)
    assert metrics["target_weather_yesterday"] == "archive"
    assert metrics["target_gen_today_kwh"] == pytest.approx(16.0)
    assert metrics["target_revenue_today_gbp"] == pytest.approx(1.44)
    assert metrics["target_weather_today"] == "forecast"
    assert metrics["target_gen_week_kwh"] == pytest.approx(68.0)
    assert metrics["target_revenue_week_gbp"] == pytest.approx(6.12)
    assert metrics["target_weather_week"] == "archive+forecast"


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_degrades_gracefully_when_archive_weather_times_out() -> None:
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=FakePlantRepository([]),
        readings_repository=FakeReadingsRepository([]),
        site_location_service=SimpleNamespace(
            get_site=lambda name: SimpleNamespace(
                name=name,
                latitude=53.0,
                longitude=-2.0,
                tilt_deg=20.0,
                azimuth_deg=180.0,
                timezone="Europe/London",
            ),
            get_all_sites=lambda: [],
        ),
        archive_irradiance_fetcher=FakeArchiveIrradianceFetcherRaising("Request timed out"),
        forecast_irradiance_fetcher=FakeForecastIrradianceFetcher(
            [{"hh_ts": "2026-03-08T12:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 400.0}]
        ),
        runtime_today=date(2026, 3, 8),
    )

    metrics = await fetcher.get_target_metrics(
        reference_date=date(2026, 3, 8),
        capacity_kwp=100.0,
        ppa_rate_gbp_mwh=90.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
    )

    assert metrics["target_gen_yesterday_kwh"] is None
    assert metrics["target_revenue_yesterday_gbp"] is None
    assert metrics["target_gen_today_kwh"] == pytest.approx(16.0)
    assert metrics["target_revenue_today_gbp"] == pytest.approx(1.44)
    assert metrics["target_gen_week_kwh"] == pytest.approx(16.0)
    assert metrics["target_revenue_week_gbp"] == pytest.approx(1.44)
    assert metrics["target_weather_today"] == "forecast"
    assert "Archive weather fetch failed for 2026-03-07: Request timed out" in metrics["target_revenue_message"]


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_falls_back_to_archive_when_repo_poa_lookup_fails() -> None:
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    archive_rows = [
        {"hh_ts": "2026-03-07T10:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 200.0},
        {"hh_ts": "2026-03-07T11:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 200.0},
    ]
    generation_rows = SimpleNamespace(
        readings=[
            SimpleNamespace(timestamp="2026-03-07T10:00:00Z", device_id="INV:1", power_kw=0.5),
            SimpleNamespace(timestamp="2026-03-07T11:00:00Z", device_id="INV:1", power_kw=0.5),
        ]
    )

    async def fake_batch_fetcher(source, identifier, target_date):  # noqa: ANN001
        return generation_rows

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=FakePlantRepository([{"alias": "Newfold Farm", "plant_uid": "ERS:00001"}]),
        readings_repository=FakeReadingsRepositoryRaising("database does not exist"),
        site_location_service=SimpleNamespace(
            get_site=lambda name: SimpleNamespace(
                name=name,
                latitude=53.0,
                longitude=-2.0,
                tilt_deg=20.0,
                azimuth_deg=180.0,
                timezone="Europe/London",
            ),
            get_all_sites=lambda: [],
        ),
        archive_irradiance_fetcher=FakeArchiveIrradianceFetcher(archive_rows),
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "ERS:00001",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="BAE Fylde",
        match_name="Newfold Farm",
        source="juggle",
    )

    assert metrics["irradiance_source"] == "openmeteo_archive_gti"
    assert metrics["irradiance_device_id"] == "Newfold Farm"
    assert metrics["availability_ratio"] == pytest.approx(1.0)
    assert "Repo POA lookup failed: database does not exist" not in metrics["irradiance_message"]


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_degrades_gracefully_when_plant_registry_lookup_fails() -> None:
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    archive_rows = [
        {"hh_ts": "2026-03-07T10:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 200.0},
        {"hh_ts": "2026-03-07T11:00:00Z", "poa_interval_kwh_m2": 0.20, "poa_wm2": 200.0},
    ]
    generation_rows = SimpleNamespace(
        readings=[
            SimpleNamespace(timestamp="2026-03-07T10:00:00Z", device_id="INV:1", power_kw=0.5),
            SimpleNamespace(timestamp="2026-03-07T11:00:00Z", device_id="INV:1", power_kw=0.5),
        ]
    )

    async def fake_batch_fetcher(source, identifier, target_date):  # noqa: ANN001
        return generation_rows

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=FakePlantRepositoryRaising("database does not exist"),
        readings_repository=FakeReadingsRepository([]),
        site_location_service=SimpleNamespace(
            get_site=lambda name: SimpleNamespace(
                name=name,
                latitude=53.0,
                longitude=-2.0,
                tilt_deg=20.0,
                azimuth_deg=180.0,
                timezone="Europe/London",
            ),
            get_all_sites=lambda: [],
        ),
        archive_irradiance_fetcher=FakeArchiveIrradianceFetcher(archive_rows),
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "4667531",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="BAE Fylde",
        match_name="Newfold Farm",
        source="solaredge",
    )

    assert metrics["irradiance_source"] == "openmeteo_archive_gti"
    assert metrics["irradiance_device_id"] == "Newfold Farm"
    assert metrics["availability_ratio"] == pytest.approx(1.0)
    assert "plant registry lookup failed" not in metrics["irradiance_message"].lower()

@pytest.mark.asyncio
async def test_build_yesterday_dataset_uses_mapping_and_check_results(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Blachford UK": {
            "platform": "solaredge",
            "site_id": "4466155",
            "juggle_uid": "AMP:00024"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {"Alias": "Blachford UK", "PAC Date": "2026-03-01"},
        ]
    )
    juggle_checker = FakeChecker("juggle", has_data=True)
    solaredge_checker = FakeChecker("solaredge", has_data=False, status="no_data")

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={
            "juggle": juggle_checker,
            "solaredge": solaredge_checker,
        },
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    assert len(dataset) == 1
    row = dataset[0]
    assert row["asset_name"] == "Blachford UK"
    assert row["target_date"] == "2026-03-07"
    assert row["pac_date"] == "2026-03-01"
    assert row["pac_phase"] == "post_pac"
    assert row["pac_in_past"] is True
    assert row["pac_date_missing"] is False
    assert row["match_name"] == "Blachford UK"
    assert row["match_method"] == "exact_registry"
    assert row["match_confidence"] == pytest.approx(1.0)
    assert row["juggle_identifier"] == "AMP:00024"
    assert row["solaredge_identifier"] == "4466155"
    assert row["resolved_source_types"] == "juggle,solaredge"
    assert row["juggle_has_data"] is True
    assert row["solaredge_has_data"] is False
    assert row["has_any_data"] is True
    assert row["preferred_source"] == "juggle"
    assert juggle_checker.calls == [("AMP:00024", date(2026, 3, 7))]
    assert solaredge_checker.calls == [("4466155", date(2026, 3, 7))]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_includes_unknown_pac_assets_with_data(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Cromwell Tools": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "AMP:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService([{"Alias": "Cromwell Tools"}])
    juggle_checker = FakeChecker("juggle", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": juggle_checker},
        supported_sources=("juggle",),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    assert len(dataset) == 1
    row = dataset[0]
    assert row["asset_name"] == "Cromwell Tools"
    assert row["pac_phase"] == "unknown"
    assert row["pac_date_missing"] is True
    assert row["has_any_data"] is True
    assert row["sources_with_data"] == "juggle"


@pytest.mark.asyncio
async def test_build_yesterday_dataset_attaches_juggle_daylight_metrics(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "BAE Fylde",
                "PAC Date": "2026-03-01",
                "Data Source Match": "Newfold Farm",
                "TIC kWp": 9630,
            }
        ]
    )
    juggle_checker = FakeChecker("juggle", has_data=True)
    metrics_fetcher = FakeDaylightMetricsFetcher(
        {
            "capacity_kwp": 9630.0,
            "irradiance_source": "juggle_weather_station",
            "irradiance_device_id": "WETH:000274",
            "irradiance_threshold_wm2": 75.0,
            "daylight_hh_periods": 20,
            "available_hh_periods": 18,
            "availability_ratio": 0.9,
            "actual_daylight_kwh": 5120.5,
            "expected_daylight_kwh": 6400.0,
            "h_poa_daylight_kwh_m2": 0.6646,
            "performance_ratio": 0.800078125,
            "irradiance_message": "",
        }
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": juggle_checker},
        supported_sources=("juggle",),
        juggle_daylight_metrics_fetcher=metrics_fetcher,
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["availability_ratio"] == pytest.approx(0.9)
    assert row["performance_ratio"] == pytest.approx(0.800078125)
    assert row["actual_daylight_kwh"] == pytest.approx(5120.5)
    assert row["daylight_hh_periods"] == 20
    assert row["available_hh_periods"] == 18
    assert row["irradiance_device_id"] == "WETH:000274"
    assert metrics_fetcher.calls == [
        (
            "ERS:00001",
            date(2026, 3, 7),
            9630.0,
            {
                "asset_name": "BAE Fylde",
                "match_name": "Newfold Farm",
                "source": "juggle",
            },
        )
    ]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_does_not_infer_curtailment_from_daylight_gap_without_export_limit_signal(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Newfold Farm",
                "PAC Date": "2026-03-01",
                "PPA Rate (GBP/MWh)": "85",
                "TIC kWp": 500,
            }
        ]
    )
    juggle_checker = FakeChecker("juggle", has_data=True)
    metrics_fetcher = FakeDaylightMetricsFetcher(
        metrics={
            "capacity_kwp": 500.0,
            "irradiance_source": "juggle_weather_station",
            "irradiance_device_id": "WETH:000274",
            "irradiance_threshold_wm2": 75.0,
            "daylight_hh_periods": 20,
            "available_hh_periods": 18,
            "availability_ratio": 0.9,
            "actual_daylight_kwh": 100.0,
            "expected_daylight_kwh": 120.0,
            "h_poa_daylight_kwh_m2": 0.3,
            "performance_ratio": 0.8333333333,
            "irradiance_message": "",
        }
    )
    curtailment_fetcher = FakeCurtailmentFetcher(result=None)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": juggle_checker},
        supported_sources=("juggle",),
        daylight_metrics_fetcher=metrics_fetcher,
        curtailment_fetcher=curtailment_fetcher,
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["curtailment_event_type"] == ""
    assert row["curtailment_generation_loss_kwh"] is None
    assert row["curtailment_revenue_loss_gbp"] is None
    assert curtailment_fetcher.calls == [
        (
            "ERS:00001",
            date(2026, 3, 7),
            85.0,
            {
                "asset_name": "Newfold Farm",
                "match_name": "Newfold Farm",
                "preferred_source": "juggle",
                "expected_daylight_kwh": 120.0,
                "actual_daylight_kwh": 100.0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_populates_curtailment_from_export_limit_summary(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Newfold Farm",
                "PAC Date": "2026-03-01",
                "PPA Rate (GBP/MWh)": "85",
                "TIC kWp": 500,
            }
        ]
    )
    juggle_checker = FakeChecker("juggle", has_data=True)
    metrics_fetcher = FakeDaylightMetricsFetcher(
        metrics={
            "capacity_kwp": 500.0,
            "irradiance_source": "juggle_weather_station",
            "irradiance_device_id": "WETH:000274",
            "irradiance_threshold_wm2": 75.0,
            "daylight_hh_periods": 20,
            "available_hh_periods": 18,
            "availability_ratio": 0.9,
            "actual_daylight_kwh": 100.0,
            "expected_daylight_kwh": 120.0,
            "h_poa_daylight_kwh_m2": 0.3,
            "performance_ratio": 0.8333333333,
            "irradiance_message": "",
        }
    )
    curtailment_fetcher = FakeCurtailmentFetcher(
        result={
            "curtailment_event_type": "export_limit_curtailment",
            "curtailment_generation_loss_kwh": 12.5,
            "curtailment_revenue_loss_gbp": 1.0625,
            "curtailment_confidence": 0.95,
            "curtailment_message": "Detected from export-limit telemetry with 8 curtailed intervals.",
        }
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": juggle_checker},
        supported_sources=("juggle",),
        daylight_metrics_fetcher=metrics_fetcher,
        curtailment_fetcher=curtailment_fetcher,
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["curtailment_event_type"] == "export_limit_curtailment"
    assert row["curtailment_generation_loss_kwh"] == pytest.approx(12.5)
    assert row["curtailment_revenue_loss_gbp"] == pytest.approx(1.0625)
    assert row["curtailment_confidence"] == pytest.approx(0.95)
    assert row["curtailment_message"] == "Detected from export-limit telemetry with 8 curtailed intervals."


@pytest.mark.asyncio
async def test_build_yesterday_dataset_keeps_export_limit_curtailment_even_without_source_checker_data(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Newfold Farm",
                "PAC Date": "2026-03-01",
                "PPA Rate (GBP/MWh)": "85",
                "TIC kWp": 500,
            }
        ]
    )
    metrics_fetcher = FakeDaylightMetricsFetcher(
        metrics={
            "capacity_kwp": 500.0,
            "actual_daylight_kwh": 100.0,
            "expected_daylight_kwh": 120.0,
        }
    )
    curtailment_fetcher = FakeCurtailmentFetcher(
        result={
            "curtailment_event_type": "export_limit_curtailment",
            "curtailment_generation_loss_kwh": 20.0,
            "curtailment_revenue_loss_gbp": 1.7,
            "curtailment_confidence": 0.95,
            "curtailment_message": "Detected from export-limit history with 2 curtailed intervals.",
        }
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": FakeChecker("juggle", has_data=False, status="no_data")},
        supported_sources=("juggle",),
        daylight_metrics_fetcher=metrics_fetcher,
        curtailment_fetcher=curtailment_fetcher,
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["has_any_data"] is False
    assert row["curtailment_event_type"] == "export_limit_curtailment"
    assert row["curtailment_generation_loss_kwh"] == pytest.approx(20.0)
    assert row["curtailment_revenue_loss_gbp"] == pytest.approx(1.7)


def test_export_limit_curtailment_fetcher_uses_historical_signal_to_gate_daylight_gap(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import ExportLimitCurtailmentFetcher

    export_limit_dir = tmp_path / "export_limits"
    export_limit_dir.mkdir()
    history_path = export_limit_dir / "export_limits_20250101_20260105.csv"
    history_path.write_text(
        "\n".join(
            [
                "plant_uid,plant_name,timestamp,export_limit_pct,is_curtailed",
                "ERS:00001,Newfold Farm,2026-03-07T10:00:00Z,55.0,True",
                "ERS:00001,Newfold Farm,2026-03-07T10:30:00Z,55.0,True",
                "ERS:00001,Newfold Farm,2026-03-07T11:00:00Z,100.0,False",
            ]
        ),
        encoding="utf-8",
    )

    fetcher = ExportLimitCurtailmentFetcher(
        curtailment_engine=SimpleNamespace(run=lambda plant_uid, start, end: SimpleNamespace(summary={})),
        export_limit_history_dir=export_limit_dir,
    )

    result = fetcher.get_day_curtailment(
        "ERS:00001",
        date(2026, 3, 7),
        ppa_rate_gbp_mwh=85.0,
        expected_daylight_kwh=120.0,
        actual_daylight_kwh=100.0,
    )

    assert result == {
        "curtailment_event_type": "export_limit_curtailment",
        "curtailment_generation_loss_kwh": 20.0,
        "curtailment_revenue_loss_gbp": pytest.approx(1.7),
        "curtailment_confidence": 0.95,
        "curtailment_message": "Detected from export-limit history with 2 curtailed intervals. Min observed limit was 55.00%.",
    }


def test_export_limit_curtailment_fetcher_falls_back_to_csv_when_parquet_is_unreadable(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import ExportLimitCurtailmentFetcher

    export_limit_dir = tmp_path / "export_limits"
    export_limit_dir.mkdir()
    (export_limit_dir / "export_limits_20250101_20260105.parquet").write_text("not a parquet file", encoding="utf-8")
    (export_limit_dir / "export_limits_20250101_20260105.csv").write_text(
        "\n".join(
            [
                "plant_uid,plant_name,timestamp,export_limit_pct,is_curtailed",
                "ERS:00001,Newfold Farm,2026-03-07T10:00:00Z,55.0,True",
                "ERS:00001,Newfold Farm,2026-03-07T10:30:00Z,55.0,True",
            ]
        ),
        encoding="utf-8",
    )

    fetcher = ExportLimitCurtailmentFetcher(
        curtailment_engine=SimpleNamespace(run=lambda plant_uid, start, end: SimpleNamespace(summary={})),
        export_limit_history_dir=export_limit_dir,
    )

    result = fetcher.get_day_curtailment(
        "ERS:00001",
        date(2026, 3, 7),
        ppa_rate_gbp_mwh=85.0,
        expected_daylight_kwh=120.0,
        actual_daylight_kwh=100.0,
    )

    assert result is not None
    assert result["curtailment_event_type"] == "export_limit_curtailment"
    assert result["curtailment_generation_loss_kwh"] == pytest.approx(20.0)


def test_export_limit_curtailment_fetcher_prefers_live_api_signal_when_available(monkeypatch, tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import ExportLimitCurtailmentFetcher

    fetcher = ExportLimitCurtailmentFetcher(
        curtailment_engine=SimpleNamespace(run=lambda plant_uid, start, end: SimpleNamespace(summary={})),
        export_limit_history_dir=tmp_path / "missing",
    )
    monkeypatch.setattr(
        fetcher,
        "_lookup_export_limit_api_signal",
        lambda plant_uid, target_date: {"curtailed_records": 3, "min_limit_pct": 60.0},
    )

    result = fetcher.get_day_curtailment(
        "AMP:00029",
        date(2026, 3, 8),
        ppa_rate_gbp_mwh=100.0,
        expected_daylight_kwh=90.0,
        actual_daylight_kwh=50.0,
    )

    assert result == {
        "curtailment_event_type": "export_limit_curtailment",
        "curtailment_generation_loss_kwh": 40.0,
        "curtailment_revenue_loss_gbp": pytest.approx(4.0),
        "curtailment_confidence": 0.95,
        "curtailment_message": "Detected from live export-limit telemetry with 3 curtailed intervals. Min observed limit was 60.00%.",
    }


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_uses_repo_poa_and_any_kwh_availability() -> None:
    from solar_platform.ingestion.base import Reading, ReadingBatch, ReadingQuality
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    plant_repo = FakePlantRepository(
        [
            {"alias": "PPA Park Hall", "plant_uid": "PLANT:00001"},
        ]
    )
    readings_repo = FakeReadingsRepository(
        [
            {"ts": "2026-03-07T09:00:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.03},
            {"ts": "2026-03-07T09:30:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.05},
            {"ts": "2026-03-07T10:00:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.01},
        ]
    )

    async def fake_batch_fetcher(source: str, identifier: str, target_date: date) -> ReadingBatch:
        assert source == "solaredge"
        assert identifier == "4667531"
        assert target_date == date(2026, 3, 7)
        return ReadingBatch(
            source=source,
            plant_uid=identifier,
            readings=[
                Reading(
                    timestamp="2026-03-07T09:00:00Z",
                    plant_uid=identifier,
                    device_id="site",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:15:00Z",
                    plant_uid=identifier,
                    device_id="site",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:30:00Z",
                    plant_uid=identifier,
                    device_id="site",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:45:00Z",
                    plant_uid=identifier,
                    device_id="site",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
            ],
        ).finalize()

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=plant_repo,
        readings_repository=readings_repo,
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "4667531",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
        source="solaredge",
    )

    assert readings_repo.calls == [("PLANT:00001", "POA:SOLARGIS:WEIGHTED")]
    assert metrics["irradiance_source"] == "repo_solargis_weighted_poa"
    assert metrics["irradiance_device_id"] == "POA:SOLARGIS:WEIGHTED"
    assert metrics["irradiance_threshold_wm2"] == pytest.approx(75.0)
    assert metrics["daylight_hh_periods"] == 1
    assert metrics["available_hh_periods"] == 1
    assert metrics["availability_ratio"] == pytest.approx(1.0)
    assert metrics["actual_daylight_kwh"] == pytest.approx(5.0)
    assert metrics["h_poa_daylight_kwh_m2"] == pytest.approx(0.05)
    assert metrics["expected_daylight_kwh"] == pytest.approx(5.0)
    assert metrics["performance_ratio"] == pytest.approx(1.0)
    assert metrics["inverter_count"] == 1
    assert metrics["inverters_reporting"] == 1
    assert metrics["best_inverter_availability_ratio"] == pytest.approx(1.0)
    assert metrics["worst_inverter_availability_ratio"] == pytest.approx(1.0)
    assert metrics["inverter_availability_breakdown"] == [
        {
            "device_id": "site",
            "daylight_hh_periods": 1,
            "available_hh_periods": 1,
            "availability_ratio": 1.0,
            "actual_daylight_kwh": pytest.approx(5.0),
        }
    ]


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_falls_back_to_archive_gti() -> None:
    from solar_platform.ingestion.base import ReadingBatch
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    plant_repo = FakePlantRepository([{"alias": "PPA Park Hall", "plant_uid": "PLANT:00001"}])
    readings_repo = FakeReadingsRepository([])
    archive_fetcher = FakeArchiveIrradianceFetcher(
        [
            {
                "hh_ts": pd.Timestamp("2026-03-07T09:00:00"),
                "poa_interval_kwh_m2": 0.03,
                "poa_wm2": 60.0,
            },
            {
                "hh_ts": pd.Timestamp("2026-03-07T09:30:00"),
                "poa_interval_kwh_m2": 0.04,
                "poa_wm2": 80.0,
            },
        ]
    )
    site_locations = SimpleNamespace(
        get_site=lambda name: None,
        get_all_sites=lambda: [
            SimpleNamespace(
                name="PPA Park Hall",
                latitude=53.082483,
                longitude=-2.24856,
                tilt_deg=10.0,
                azimuth_deg=180.0,
                timezone="Europe/London",
            )
        ],
    )

    async def fake_batch_fetcher(source: str, identifier: str, target_date: date) -> ReadingBatch:
        return ReadingBatch(source=source, plant_uid=identifier, readings=[]).finalize()

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=plant_repo,
        readings_repository=readings_repo,
        site_location_service=site_locations,
        archive_irradiance_fetcher=archive_fetcher,
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "4667531",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
        source="solaredge",
    )

    assert metrics["irradiance_source"] == "openmeteo_archive_gti"
    assert metrics["irradiance_device_id"] == "PPA Park Hall"
    assert metrics["daylight_hh_periods"] == 1
    assert metrics["available_hh_periods"] == 0
    assert metrics["h_poa_daylight_kwh_m2"] == pytest.approx(0.04)
    assert metrics["expected_daylight_kwh"] == pytest.approx(4.0)
    assert metrics["performance_ratio"] == pytest.approx(0.0)
    assert archive_fetcher.calls[0]["target_date"] == date(2026, 3, 7)


def test_repository_daylight_metrics_fetcher_derives_energy_from_cumulative_import_energy() -> None:
    from solar_platform.ingestion.base import Reading, ReadingBatch, ReadingQuality
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    batch = ReadingBatch(
        source="juggle",
        plant_uid="AMP:00032",
        readings=[
            Reading(
                timestamp="2026-03-07T07:00:00Z",
                plant_uid="AMP:00032",
                device_id="INVERT:003287",
                source="juggle",
                power_kw=0.0,
                interval_seconds=900,
                quality=ReadingQuality.MEASURED,
                raw_payload={"importEnergy": {"value": 22543301, "unit": "Wh"}},
            ),
            Reading(
                timestamp="2026-03-07T07:15:00Z",
                plant_uid="AMP:00032",
                device_id="INVERT:003287",
                source="juggle",
                power_kw=0.0,
                interval_seconds=900,
                quality=ReadingQuality.MEASURED,
                raw_payload={"importEnergy": {"value": 22543400, "unit": "Wh"}},
            ),
            Reading(
                timestamp="2026-03-07T07:30:00Z",
                plant_uid="AMP:00032",
                device_id="INVERT:003287",
                source="juggle",
                power_kw=0.0,
                interval_seconds=900,
                quality=ReadingQuality.MEASURED,
                raw_payload={"importEnergy": {"value": 22543801, "unit": "Wh"}},
            ),
        ],
    ).finalize()

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=FakePlantRepository([]),
        readings_repository=FakeReadingsRepository([]),
    )

    df = fetcher._summarise_generation_batch(batch)

    assert len(df) == 2
    assert df["energy_kwh"].sum() == pytest.approx(0.5)
    assert df.iloc[0]["energy_kwh"] == pytest.approx(0.099)
    assert df.iloc[1]["energy_kwh"] == pytest.approx(0.401)


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_breaks_availability_down_by_inverter() -> None:
    from solar_platform.ingestion.base import Reading, ReadingBatch, ReadingQuality
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    plant_repo = FakePlantRepository(
        [
            {"alias": "PPA Park Hall", "plant_uid": "PLANT:00001"},
        ]
    )
    readings_repo = FakeReadingsRepository(
        [
            {"ts": "2026-03-07T09:00:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.05},
            {"ts": "2026-03-07T09:30:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.05},
        ]
    )

    async def fake_batch_fetcher(source: str, identifier: str, target_date: date) -> ReadingBatch:
        return ReadingBatch(
            source=source,
            plant_uid=identifier,
            readings=[
                Reading(
                    timestamp="2026-03-07T09:00:00Z",
                    plant_uid=identifier,
                    device_id="INV:A",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:15:00Z",
                    plant_uid=identifier,
                    device_id="INV:A",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:30:00Z",
                    plant_uid=identifier,
                    device_id="INV:A",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:45:00Z",
                    plant_uid=identifier,
                    device_id="INV:A",
                    source=source,
                    power_kw=10.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:00:00Z",
                    plant_uid=identifier,
                    device_id="INV:B",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:15:00Z",
                    plant_uid=identifier,
                    device_id="INV:B",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:30:00Z",
                    plant_uid=identifier,
                    device_id="INV:B",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
                Reading(
                    timestamp="2026-03-07T09:45:00Z",
                    plant_uid=identifier,
                    device_id="INV:B",
                    source=source,
                    power_kw=0.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
            ],
        ).finalize()

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=plant_repo,
        readings_repository=readings_repo,
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "4667531",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
        source="solaredge",
    )

    assert metrics["inverter_count"] == 2
    assert metrics["inverters_reporting"] == 1
    assert metrics["best_inverter_availability_ratio"] == pytest.approx(1.0)
    assert metrics["worst_inverter_availability_ratio"] == pytest.approx(0.0)
    assert metrics["inverter_availability_summary"] == "INV:A 100.0% (1/1); INV:B 0.0% (0/1)"
    assert metrics["inverter_availability_breakdown"] == [
        {
            "device_id": "INV:A",
            "daylight_hh_periods": 1,
            "available_hh_periods": 1,
            "availability_ratio": 1.0,
            "actual_daylight_kwh": pytest.approx(10.0),
        },
        {
            "device_id": "INV:B",
            "daylight_hh_periods": 1,
            "available_hh_periods": 0,
            "availability_ratio": 0.0,
            "actual_daylight_kwh": 0.0,
        },
    ]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_ignores_placeholder_juggle_identifier_when_solaredge_exists(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "PPA Park Hall": {
            "platform": "solaredge",
            "site_id": "4667531",
            "juggle_uid": "?"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Park Hall",
                "PAC Date": "2026-03-01",
                "Data Source Match": "PPA Park Hall",
            },
        ]
    )
    solaredge_checker = FakeChecker("solaredge", has_data=True)
    juggle_checker = FakeChecker("juggle", has_data=False, status="error")

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={
            "juggle": juggle_checker,
            "solaredge": solaredge_checker,
        },
        supported_sources=("juggle", "solaredge"),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["juggle_identifier"] == ""
    assert row["juggle_status"] == "unconfigured"
    assert row["solaredge_identifier"] == "4667531"
    assert row["solaredge_has_data"] is True
    assert row["checked_sources"] == "solaredge"
    assert row["has_any_data"] is True
    assert juggle_checker.calls == []
    assert solaredge_checker.calls == [("4667531", date(2026, 3, 7))]


@pytest.mark.asyncio
async def test_repository_daylight_metrics_fetcher_rolls_site_availability_up_to_hourly_basis() -> None:
    from solar_platform.ingestion.base import Reading, ReadingBatch, ReadingQuality
    from solar_platform.services.performance_copilot_asset_audit import RepositoryDaylightMetricsFetcher

    plant_repo = FakePlantRepository([{"alias": "PPA Park Hall", "plant_uid": "PLANT:00001"}])
    readings_repo = FakeReadingsRepository(
        [
            {"ts": "2026-03-07T09:00:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.04},
            {"ts": "2026-03-07T09:30:00Z", "emig_id": "POA:SOLARGIS:WEIGHTED", "poaIrradiance_value": 0.04},
        ]
    )

    async def fake_batch_fetcher(source: str, identifier: str, target_date: date) -> ReadingBatch:
        return ReadingBatch(
            source=source,
            plant_uid=identifier,
            readings=[
                Reading(
                    timestamp="2026-03-07T09:15:00Z",
                    plant_uid=identifier,
                    device_id="site",
                    source=source,
                    power_kw=20.0,
                    interval_seconds=900,
                    quality=ReadingQuality.MEASURED,
                ),
            ],
        ).finalize()

    fetcher = RepositoryDaylightMetricsFetcher(
        plant_repository=plant_repo,
        readings_repository=readings_repo,
        batch_fetcher=fake_batch_fetcher,
    )

    metrics = await fetcher.get_day_metrics(
        "4667531",
        date(2026, 3, 7),
        capacity_kwp=100.0,
        asset_name="Park Hall",
        match_name="PPA Park Hall",
        source="solaredge",
    )

    assert metrics["daylight_hh_periods"] == 1
    assert metrics["available_hh_periods"] == 1
    assert metrics["availability_ratio"] == pytest.approx(1.0)
    assert metrics["actual_daylight_kwh"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_build_yesterday_dataset_fuzzy_matches_legacy_mapping_names(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "PPA Bannatynes Braintree": {
            "platform": "solaredge",
            "site_id": "4284090",
            "juggle_uid": "?"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {"Alias": "Bannatyne's Braintree", "PAC Date": "2026-03-01"},
        ]
    )
    solaredge_checker = FakeChecker("solaredge", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"solaredge": solaredge_checker},
        supported_sources=("juggle", "solaredge"),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["match_name"] == "PPA Bannatynes Braintree"
    assert row["match_method"] == "fuzzy_registry"
    assert row["match_confidence"] == pytest.approx(1.0)
    assert row["solaredge_identifier"] == "4284090"
    assert row["solaredge_has_data"] is True
    assert row["preferred_source"] == "solaredge"
    assert solaredge_checker.calls == [("4284090", date(2026, 3, 7))]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_marks_missing_identifier_and_unconfigured(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {"Alias": "Unknown Site", "PAC Date": "2026-03-01"},
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": FakeChecker("juggle", has_data=False, status="no_data")},
        supported_sources=("juggle", "solaredge"),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["match_name"] == ""
    assert row["match_method"] == "unresolved"
    assert row["match_confidence"] == 0.0
    assert row["juggle_status"] == "missing_identifier"
    assert row["solaredge_status"] == "unconfigured"
    assert row["has_any_data"] is False


@pytest.mark.asyncio
async def test_build_yesterday_dataset_populates_findings_and_rollups(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "BAE Fylde",
                "PAC Date": "2026-03-01",
                "Data Source Match": "Newfold Farm",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
        supported_sources=("juggle",),
        daylight_metrics_fetcher=FakeDaylightMetricsFetcher(),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["finding_types"] == ["source_unconfigured"]
    assert row["actionable_finding_count"] == 1
    assert row["highest_finding_severity"] == "medium"
    assert row["findings"] == [
        {
            "finding_type": "source_unconfigured",
            "severity": "medium",
            "confidence": pytest.approx(0.8),
            "summary": "The mapped source juggle could not be checked because credentials are missing.",
            "recommended_action": "Configure credentials for juggle in the local environment or GitHub Actions and rerun the audit.",
            "source": "juggle",
            "context": {
                "checked_sources": "juggle",
                "match_method": "notion_override",
            },
        }
    ]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_adds_point_lane_stark_fusion_variance_finding(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService(
        [
            {
                "Alias": "Point Lane Solar Farm",
                "PAC Date": "2026-03-01",
                "Huawei Station ID": "HUAWEI:POINT-LANE",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(notion_stark_daily_database_id="db_stark"),
        legacy_mapping_path=mapping_path,
        checkers={"huawei": FakeChecker("huawei", has_data=True)},
        supported_sources=("huawei",),
        daylight_metrics_fetcher=FakeDaylightMetricsFetcher(
            {
                "actual_daylight_kwh": 120.0,
                "available_hh_periods": 10,
                "daylight_hh_periods": 10,
            }
        ),
    )
    notion.database_rows_by_id["db_stark"] = [
        {
            "Date": "2026-03-07",
            "Total kWh": 100.0,
        }
    ]

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    finding = next(item for item in row["findings"] if item["finding_type"] == "stark_fusion_variance")
    assert finding["severity"] == "high"
    assert finding["metrics"] == {
        "fusion_kwh": pytest.approx(120.0),
        "stark_kwh": pytest.approx(100.0),
        "diff_kwh": pytest.approx(20.0),
        "diff_pct": pytest.approx(20.0 / 120.0 * 100.0),
    }


@pytest.mark.asyncio
async def test_build_triage_records_emits_one_row_per_finding(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService(
        [
            {
                "Alias": "Point Lane Solar Farm",
                "PAC Date": "2026-03-01",
                "Huawei Station ID": "HUAWEI:POINT-LANE",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(notion_stark_daily_database_id="db_stark"),
        legacy_mapping_path=mapping_path,
        checkers={},
        supported_sources=("huawei",),
        daylight_metrics_fetcher=FakeDaylightMetricsFetcher(
            {
                "actual_daylight_kwh": 120.0,
                "available_hh_periods": 10,
                "daylight_hh_periods": 10,
            }
        ),
    )
    notion.database_rows_by_id["db_stark"] = [
        {
            "Date": "2026-03-07",
            "Total kWh": 100.0,
        }
    ]

    triage_records = await service.build_triage_records(reference_date=date(2026, 3, 8))

    assert len(triage_records) == 2
    finding_types = sorted(record["finding_type"] for record in triage_records)
    assert finding_types == ["source_unconfigured", "stark_fusion_variance"]
    for record in triage_records:
        assert record["issue_type"] == record["finding_type"]
        assert record["finding_summary"]
        assert record["row_key"] == f"2026-03-07|Point Lane Solar Farm|{record['finding_type']}"


@pytest.mark.asyncio
async def test_build_yesterday_dataset_prefers_notion_override_before_fuzzy_match(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "site_id": "",
            "juggle_uid": "ERS:00001"
          },
          "BAE Fylde Legacy Guess": {
            "platform": "solaredge",
            "site_id": "9999999"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "BAE Fylde",
                "PAC Date": "2026-03-01",
                "Data Source Match": "Newfold Farm",
            },
        ]
    )
    juggle_checker = FakeChecker("juggle", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": juggle_checker},
        supported_sources=("juggle", "solaredge"),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["match_name"] == "Newfold Farm"
    assert row["match_method"] == "notion_override"
    assert row["match_confidence"] == pytest.approx(1.0)
    assert row["juggle_identifier"] == "ERS:00001"
    assert row["juggle_has_data"] is True
    assert row["solaredge_identifier"] == ""
    assert juggle_checker.calls == [("ERS:00001", date(2026, 3, 7))]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_resolves_known_limitation_override_to_juggle_uid(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Smithy's Mushrooms (Ph1)",
                "PAC Date": "2025-01-01",
                "Data Source Match": "Smithy's Mushrooms PH1",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"juggle": FakeChecker("juggle", has_data=False, status="no_data")},
        supported_sources=("juggle",),
        daylight_metrics_fetcher=FakeDaylightMetricsFetcher(),
        curtailment_fetcher=FakeCurtailmentFetcher(),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2025, 12, 3))

    row = dataset[0]
    assert row["match_name"] == "Smithy's Mushrooms PH1"
    assert row["match_method"] == "notion_override"
    assert row["juggle_identifier"] == "AMP:00028"


@pytest.mark.asyncio
async def test_build_yesterday_dataset_uses_builtin_confirmed_registry_when_file_missing(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    missing_mapping_path = tmp_path / "missing.json"
    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Park Hall",
                "PAC Date": "2026-03-01",
                "Data Source Match": "PPA Park Hall",
            },
        ]
    )
    solaredge_checker = FakeChecker("solaredge", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=missing_mapping_path,
        checkers={"solaredge": solaredge_checker},
        supported_sources=("juggle", "solaredge"),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["match_name"] == "PPA Park Hall"
    assert row["match_method"] == "notion_override"
    assert row["solaredge_identifier"] == "4667531"
    assert row["checked_sources"] == "solaredge"
    assert row["solaredge_has_data"] is True
    assert solaredge_checker.calls == [("4667531", date(2026, 3, 7))]


@pytest.mark.asyncio
async def test_build_yesterday_dataset_uses_explicit_identifiers_before_registry(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Park Hall": {
            "platform": "solaredge",
            "site_id": "4667531"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Custom Park Hall Name",
                "PAC Date": "2026-03-01",
                "SolarEdge Site ID": "SE-EXPLICIT-1",
            },
        ]
    )
    solaredge_checker = FakeChecker("solaredge", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"solaredge": solaredge_checker},
        supported_sources=("solaredge",),
    )

    dataset = await service.build_yesterday_dataset(reference_date=date(2026, 3, 8))

    row = dataset[0]
    assert row["match_name"] == "Custom Park Hall Name"
    assert row["match_method"] == "explicit_identifiers"
    assert row["match_confidence"] == pytest.approx(1.0)
    assert row["solaredge_identifier"] == "SE-EXPLICIT-1"
    assert row["resolved_source_types"] == "solaredge"
    assert solaredge_checker.calls == [("SE-EXPLICIT-1", date(2026, 3, 7))]


def test_backfill_confirmed_data_source_matches_updates_only_changed_pages(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService(
        [
            {"Alias": "BAE Fylde", "notion_page_id": "page_1"},
            {
                "Alias": "Finlay Beverages",
                "notion_page_id": "page_2",
                "Data Source Match": "Finlay Beverages",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    result = service.backfill_confirmed_data_source_matches(
        updates={
            "BAE Fylde": "Newfold Farm",
            "Finlay Beverages": "Finlay Beverages",
            "Missing Asset": "Somewhere",
        }
    )

    assert result["updated"] == ["BAE Fylde"]
    assert result["unchanged"] == ["Finlay Beverages"]
    assert result["missing_assets"] == ["Missing Asset"]
    assert notion.updated_pages == [
        ("page_1", {"Data Source Match": "Newfold Farm"}),
    ]


@pytest.mark.asyncio
async def test_build_triage_records_creates_actionable_issue_and_email_draft(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "Newfold Farm": {
            "platform": "juggle",
            "juggle_uid": "ERS:00001"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeWritableNotionAssetRegisterService(
        [
            {
                "Alias": "BAE Fylde",
                "PAC Date": "2026-03-01",
                "Data Source Match": "Newfold Farm",
                "Project Name": "BAE Fylde",
                "Customer Registered Name": "BAE Systems",
                "SPV": "Ampyr Solar Europe",
                "Priority": "High",
                "Billing Contact": "Alice Manager",
                "Billing Contact Email": "alice@example.com",
            },
        ]
    )

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
        supported_sources=("juggle",),
    )

    triage_records = await service.build_triage_records(reference_date=date(2026, 3, 8))

    assert len(triage_records) == 1
    record = triage_records[0]
    assert record["issue_type"] == "source_unconfigured"
    assert record["finding_type"] == "source_unconfigured"
    assert record["severity"] == "medium"
    assert record["am_contact_name"] == "Alice Manager"
    assert record["am_contact_email"] == "alice@example.com"
    assert "BAE Fylde" in record["email_subject"]
    assert "Alice Manager" in record["email_draft"]
    assert "Newfold Farm" in record["evidence_summary"]
    assert record["row_key"] == "2026-03-07|BAE Fylde|source_unconfigured"


@pytest.mark.asyncio
async def test_build_triage_records_skips_pre_pac_assets(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        """
        {
          "PPA Park Hall": {
            "platform": "solaredge",
            "site_id": "4667531",
            "juggle_uid": "?"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    notion = FakeNotionAssetRegisterService(
        [
            {
                "Alias": "Park Hall",
                "PAC Date": "2026-03-20",
                "Data Source Match": "PPA Park Hall",
            },
        ]
    )
    solaredge_checker = FakeChecker("solaredge", has_data=True)

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={"solaredge": solaredge_checker},
        supported_sources=("solaredge",),
    )

    triage_records = await service.build_triage_records(reference_date=date(2026, 3, 8))

    assert triage_records == []


@pytest.mark.asyncio
async def test_publish_triage_records_to_notion_ensures_database_and_upserts_rows(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService([])
    settings = SimpleNamespace(notion_page_id="parent_page_123")

    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=settings,
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    result = service.publish_triage_records_to_notion(
        [
            {
                "row_key": "2026-03-07|BAE Fylde|source_unconfigured",
                "asset_name": "BAE Fylde",
                "project_name": "BAE Fylde",
                "customer_name": "BAE Systems",
                "spv": "Ampyr Solar Europe",
                "priority": "High",
                "target_date": "2026-03-07",
                "issue_type": "source_unconfigured",
                "severity": "medium",
                "confidence": 0.75,
                "source_coverage": "juggle",
                "evidence_summary": "Juggle credentials missing.",
                "recommended_action": "Configure credentials and rerun.",
                "email_subject": "BAE Fylde: source_unconfigured for 2026-03-07",
                "email_draft": "Draft body",
                "am_contact_name": "Alice Manager",
                "am_contact_email": "alice@example.com",
                "asset_register_url": "https://www.notion.so/asset",
                "preferred_source": "",
                "match_method": "notion_override",
                "has_any_data": False,
            }
        ]
    )

    assert result["database_id"] == "db_triage"
    assert result["published"] == 1
    assert notion.database_ensures[0][0] == "Solar Copilot Daily Triage"
    assert notion.database_ensures[0][2] == "parent_page_123"
    assert len(notion.database_upserts) == 1
    database_id, match_field, match_value, properties = notion.database_upserts[0]
    assert database_id == "db_triage"
    assert match_field == "Row Key"
    assert match_value == "2026-03-07|BAE Fylde|source_unconfigured"
    assert properties["Asset"] == {"title": [{"text": {"content": "BAE Fylde"}}]}
    assert properties["AM Email Draft"] == {"rich_text": [{"text": {"content": "Draft body"}}]}


def test_publish_daily_dataset_to_notion_uses_parent_page_and_appends_rows(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService([])
    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    result = service.publish_daily_dataset_to_notion(
        [
            {
                "asset_name": "Cromwell Tools",
                "target_date": "2026-03-07",
                "pac_date": "",
                "pac_phase": "unknown",
                "pac_in_past": False,
                "pac_date_missing": True,
                "has_any_data": True,
                "sources_with_data": "juggle",
                "preferred_source": "juggle",
                "checked_sources": "juggle",
                "match_name": "Cromwell Tools",
                "match_method": "notion_override",
                "match_confidence": 1.0,
                "resolved_source_types": "juggle",
                "resolution_notes": "Used Data Source Match override from Notion.",
                "project_name": "Cromwell Tools",
                "customer_name": "Cromwell",
                "spv": "",
                "priority": "",
                "site_address": "Somewhere",
                "am_contact_name": "Alice Manager",
                "am_contact_email": "alice@example.com",
                "notion_page_id": "page_123",
                "notion_url": "https://www.notion.so/asset",
                "capacity_kwp": 500.0,
                "ppa_rate_gbp_mwh": 95.0,
                "ppa_rate_source": "PPA Rate (GBP/MWh)",
                "target_pr_assumption_ratio": 0.8,
                "target_gen_yesterday_kwh": 1200.0,
                "target_revenue_yesterday_gbp": 114.0,
                "target_weather_yesterday": "archive",
                "target_gen_today_kwh": 1350.0,
                "target_revenue_today_gbp": 128.25,
                "target_weather_today": "forecast",
                "target_gen_week_kwh": 8200.0,
                "target_revenue_week_gbp": 779.0,
                "target_weather_week": "archive+forecast",
                "target_revenue_message": "",
                "irradiance_source": "juggle_weather_station",
                "irradiance_device_id": "WETH:000001",
                "irradiance_threshold_wm2": 75.0,
                "daylight_hh_periods": 18,
                "available_hh_periods": 17,
                "availability_ratio": 17 / 18,
                "actual_daylight_kwh": 123.4,
                "expected_daylight_kwh": 150.0,
                "h_poa_daylight_kwh_m2": 0.3,
                "performance_ratio": 123.4 / 150.0,
                "irradiance_message": "",
                "inverter_count": 2,
                "inverters_reporting": 1,
                "best_inverter_availability_ratio": 1.0,
                "worst_inverter_availability_ratio": 0.5,
                "inverter_availability_summary": "INV:A 100.0% (18/18); INV:B 50.0% (9/18)",
                "inverter_availability_breakdown": [
                    {
                        "device_id": "INV:A",
                        "daylight_hh_periods": 18,
                        "available_hh_periods": 18,
                        "availability_ratio": 1.0,
                        "actual_daylight_kwh": 70.1,
                    },
                    {
                        "device_id": "INV:B",
                        "daylight_hh_periods": 18,
                        "available_hh_periods": 9,
                        "availability_ratio": 0.5,
                        "actual_daylight_kwh": 53.3,
                    },
                ],
                "juggle_identifier": "AMP:00001",
                "juggle_status": "ok",
                "juggle_has_data": True,
                "juggle_sample_count": 96,
                "juggle_message": "",
                "solaredge_identifier": "",
                "solaredge_status": "unconfigured",
                "solaredge_has_data": False,
                "solaredge_sample_count": 0,
                "solaredge_message": "",
                "solis_identifier": "",
                "solis_status": "unconfigured",
                "solis_has_data": False,
                "solis_sample_count": 0,
                "solis_message": "",
                "enphase_identifier": "",
                "enphase_status": "unconfigured",
                "enphase_has_data": False,
                "enphase_sample_count": 0,
                "enphase_message": "",
                "huawei_identifier": "",
                "huawei_status": "unconfigured",
                "huawei_has_data": False,
                "huawei_sample_count": 0,
                "huawei_message": "",
                "sma_identifier": "",
                "sma_status": "unconfigured",
                "sma_has_data": False,
                "sma_sample_count": 0,
                "sma_message": "",
                "findings": [
                    {
                        "finding_type": "inverter_meter_comparison",
                        "severity": "high",
                        "confidence": 0.9,
                        "summary": "Inverter total differs from PV meter total.",
                        "recommended_action": "Review Juggle inverter and PV meter totals.",
                        "metrics": {
                            "inverter_kwh": 123.4,
                            "meter_kwh": 120.0,
                            "diff_kwh": 3.4,
                            "diff_pct": 2.8333,
                            "alert_label": "Critical",
                            "platform": "solis",
                            "solis_kwh": 121.0,
                        },
                    }
                ],
                "finding_types": ["inverter_meter_comparison"],
                "actionable_finding_count": 1,
                "highest_finding_severity": "high",
            },
            {
                "asset_name": "No Data Site",
                "target_date": "2026-03-07",
                "pac_date": "2026-03-01",
                "pac_phase": "post_pac",
                "pac_in_past": True,
                "pac_date_missing": False,
                "has_any_data": False,
                "sources_with_data": "",
                "preferred_source": "",
                "checked_sources": "juggle",
                "match_name": "",
                "match_method": "unresolved",
                "match_confidence": 0.0,
                "resolved_source_types": "",
                "resolution_notes": "No data",
                "project_name": "No Data Site",
                "customer_name": "",
                "spv": "",
                "priority": "",
                "notion_url": "https://www.notion.so/no-data",
                "juggle_status": "no_data",
                "juggle_sample_count": 0,
                "solaredge_status": "unconfigured",
                "solaredge_sample_count": 0,
                "solis_status": "unconfigured",
                "solis_sample_count": 0,
                "enphase_status": "unconfigured",
                "enphase_sample_count": 0,
                "huawei_status": "unconfigured",
                "huawei_sample_count": 0,
                "sma_status": "unconfigured",
                "sma_sample_count": 0,
            }
        ],
        parent_page_id="page_daily_json",
    )

    assert result["database_id"] == "db_triage"
    assert result["eligible_rows"] == 1
    assert result["published"] == 1
    assert notion.database_ensures[0][0] == "Daily JSON"
    assert notion.database_ensures[0][2] == "page_daily_json"
    assert notion.database_property_ensures[0][0] == "db_triage"
    assert notion.database_upserts == []
    assert len(notion.database_creates) == 1
    database_id, properties = notion.database_creates[0]
    assert database_id == "db_triage"
    assert properties["Row Key"] == {"rich_text": [{"text": {"content": "2026-03-07|Cromwell Tools"}}]}
    assert properties["PAC Date"] == {"date": None}
    assert properties["PAC Phase"] == {"rich_text": [{"text": {"content": "unknown"}}]}
    assert properties["Has Any Data"] == {"checkbox": True}
    assert properties["Juggle Identifier"] == {"rich_text": [{"text": {"content": "AMP:00001"}}]}
    assert properties["Juggle Has Data"] == {"checkbox": True}
    assert properties["Availability (%)"] == {"number": pytest.approx(17 / 18)}
    daily_json = properties["Daily JSON"]["rich_text"][0]["text"]["content"]
    assert "\"finding_type\": \"inverter_meter_comparison\"" in daily_json
    assert properties["PR (%)"] == {"number": pytest.approx(123.4 / 150.0)}
    assert properties["PPA Rate (GBP/MWh)"] == {"number": 95.0}
    assert properties["PPA Rate Source"] == {
        "rich_text": [{"text": {"content": "PPA Rate (GBP/MWh)"}}]
    }
    assert properties["Target PR Assumption (%)"] == {"number": 0.8}
    assert properties["Target Gen Yesterday (kWh)"] == {"number": 1200.0}
    assert properties["Target Revenue Yesterday (£)"] == {"number": 114.0}
    assert properties["Target Weather Yesterday"] == {
        "rich_text": [{"text": {"content": "archive"}}]
    }
    assert properties["Target Gen Today (kWh)"] == {"number": 1350.0}
    assert properties["Target Revenue Today (£)"] == {"number": 128.25}
    assert properties["Target Weather Today"] == {
        "rich_text": [{"text": {"content": "forecast"}}]
    }
    assert properties["Target Gen Week (kWh)"] == {"number": 8200.0}
    assert properties["Target Revenue Week (£)"] == {"number": 779.0}
    assert properties["Target Weather Week"] == {
        "rich_text": [{"text": {"content": "archive+forecast"}}]
    }
    assert properties["Inverter Count"] == {"number": 2.0}
    assert properties["Inverters Reporting"] == {"number": 1.0}
    assert properties["Best Inverter Availability (%)"] == {"number": 1.0}
    assert properties["Worst Inverter Availability (%)"] == {"number": 0.5}
    assert properties["Inverter Availability Summary"] == {
        "rich_text": [{"text": {"content": "INV:A 100.0% (18/18); INV:B 50.0% (9/18)"}}]
    }
    assert properties["Inverter Availability Breakdown"] == {
        "rich_text": [
            {
                "text": {
                    "content": (
                        '[{"actual_daylight_kwh": 70.1, "availability_ratio": 1.0, '
                        '"available_hh_periods": 18, "daylight_hh_periods": 18, '
                        '"device_id": "INV:A"}, {"actual_daylight_kwh": 53.3, '
                        '"availability_ratio": 0.5, "available_hh_periods": 9, '
                        '"daylight_hh_periods": 18, "device_id": "INV:B"}]'
                    )
                }
            }
        ]
    }


def test_publish_daily_dataset_to_notion_includes_rows_with_findings_even_without_source_data(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService([])
    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    result = service.publish_daily_dataset_to_notion(
        [
            {
                "asset_name": "Hibernian Stadium",
                "target_date": "2026-03-07",
                "pac_date": "2026-03-01",
                "pac_phase": "post_pac",
                "pac_in_past": True,
                "pac_date_missing": False,
                "has_any_data": False,
                "sources_with_data": "",
                "preferred_source": "",
                "checked_sources": "juggle",
                "match_name": "Hibernian Stadium",
                "match_method": "notion_override",
                "match_confidence": 1.0,
                "resolved_source_types": "juggle",
                "resolution_notes": "Used Data Source Match override from Notion.",
                "project_name": "Hibernian Stadium",
                "customer_name": "",
                "spv": "",
                "priority": "",
                "notion_url": "https://www.notion.so/hibernian",
                "juggle_status": "missing_identifier",
                "juggle_sample_count": 0,
                "solaredge_status": "unconfigured",
                "solaredge_sample_count": 0,
                "solis_status": "unconfigured",
                "solis_sample_count": 0,
                "enphase_status": "unconfigured",
                "enphase_sample_count": 0,
                "huawei_status": "unconfigured",
                "huawei_sample_count": 0,
                "sma_status": "unconfigured",
                "sma_sample_count": 0,
                "findings": [
                    {
                        "finding_type": "missing_identifier",
                        "severity": "medium",
                        "confidence": 0.8,
                        "summary": "Missing Juggle identifier.",
                        "recommended_action": "Populate the identifier.",
                    }
                ],
                "finding_types": ["missing_identifier"],
                "actionable_finding_count": 1,
                "highest_finding_severity": "medium",
            }
        ],
        parent_page_id="page_daily_json",
    )

    assert result["eligible_rows"] == 1
    assert result["published"] == 1
    assert len(notion.database_creates) == 1
    _, properties = notion.database_creates[0]
    daily_json = properties["Daily JSON"]["rich_text"][0]["text"]["content"]
    assert "\"finding_type\": \"missing_identifier\"" in daily_json
    assert properties["Has Any Data"] == {"checkbox": False}


def test_publish_daily_dataset_to_notion_republishes_same_row_key_as_new_row(tmp_path) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")

    notion = FakeWritableNotionAssetRegisterService([])
    service = AssetRegisterAuditService(
        notion_service=notion,
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    row = {
        "asset_name": "Cromwell Tools",
        "target_date": "2026-03-07",
        "pac_date": "",
        "pac_phase": "unknown",
        "pac_in_past": False,
        "pac_date_missing": True,
        "has_any_data": True,
        "sources_with_data": "juggle",
        "preferred_source": "juggle",
        "checked_sources": "juggle",
        "match_name": "Cromwell Tools",
        "match_method": "notion_override",
        "match_confidence": 1.0,
        "resolved_source_types": "juggle",
        "resolution_notes": "Used Data Source Match override from Notion.",
        "project_name": "Cromwell Tools",
        "customer_name": "Cromwell",
        "spv": "",
        "priority": "",
        "site_address": "Somewhere",
        "am_contact_name": "Alice Manager",
        "am_contact_email": "alice@example.com",
        "notion_page_id": "page_123",
        "notion_url": "https://www.notion.so/asset",
        "juggle_identifier": "AMP:00001",
        "juggle_status": "ok",
        "juggle_has_data": True,
        "juggle_sample_count": 96,
        "juggle_message": "",
        "findings": [],
        "finding_types": [],
        "actionable_finding_count": 0,
        "highest_finding_severity": "",
    }

    first = service.publish_daily_dataset_to_notion([row], parent_page_id="page_daily_json")
    second = service.publish_daily_dataset_to_notion([row], database_id=first["database_id"])

    assert first["published"] == 1
    assert second["published"] == 1
    assert notion.database_upserts == []
    assert len(notion.database_creates) == 2
    assert notion.database_creates[0][1]["Row Key"] == notion.database_creates[1][1]["Row Key"]


@pytest.mark.asyncio
async def test_solaredge_daily_checker_uses_site_specific_keys_json(monkeypatch) -> None:
    from solar_platform.services.performance_copilot_asset_audit import SolarEdgeDailyChecker

    class FakeAdapter:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        async def fetch_readings(self, identifier, start, end):  # noqa: ANN001
            assert identifier == "4667531"
            assert start.date() == date(2026, 3, 7)
            assert end.date() == date(2026, 3, 8)
            return SimpleNamespace(readings=[{"power_kw": 1.2}], errors=[], warnings=[])

    monkeypatch.setenv("SOLAREDGE_KEYS_JSON", '{"4667531":"site-key-123"}')
    checker = SolarEdgeDailyChecker()
    monkeypatch.setattr(checker, "_build_adapter", lambda api_key: FakeAdapter(api_key))

    result = await checker.check_day("4667531", date(2026, 3, 7))

    assert result.status == "ok"
    assert result.has_data is True
    assert result.sample_count == 1
    assert result.identifier == "4667531"


@pytest.mark.asyncio
async def test_solaredge_daily_checker_reports_unconfigured_when_site_key_missing(monkeypatch) -> None:
    from solar_platform.services.performance_copilot_asset_audit import SolarEdgeDailyChecker

    monkeypatch.setenv("SOLAREDGE_KEYS_JSON", '{"1111111":"other-key"}')
    checker = SolarEdgeDailyChecker()

    result = await checker.check_day("4667531", date(2026, 3, 7))

    assert result.status == "unconfigured"
    assert result.has_data is False
    assert "missing site-specific API key" in result.message


def test_solis_daily_checker_uses_default_base_url_when_env_is_empty(monkeypatch) -> None:
    from solar_platform.services.performance_copilot_asset_audit import SolisDailyChecker

    monkeypatch.setenv("SOLIS_API_URL", "")
    checker = SolisDailyChecker()

    assert checker.base_url == "https://www.soliscloud.com:13333"


@pytest.mark.asyncio
async def test_solis_daily_checker_accepts_list_data_payload(monkeypatch) -> None:
    from solar_platform.services.performance_copilot_asset_audit import SolisDailyChecker

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {
                        "dateStr": "2026-03-07",
                        "energy": "42.5",
                    }
                ]
            }

    monkeypatch.setenv("SOLIS_KEY_ID", "key")
    monkeypatch.setenv("SOLIS_KEY_SECRET", "secret")
    monkeypatch.setattr(
        "solar_platform.services.performance_copilot_asset_audit.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    checker = SolisDailyChecker()
    result = await checker.check_day("1298491919450070492", date(2026, 3, 7))

    assert result.status == "ok"
    assert result.has_data is True
    assert result.sample_count == 1


def test_fetch_solis_day_energy_accepts_list_data_payload(tmp_path, monkeypatch) -> None:
    from solar_platform.services.performance_copilot_asset_audit import AssetRegisterAuditService

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {
                        "dateStr": "2026-03-07",
                        "energy": "84.2",
                    }
                ]
            }

    monkeypatch.setenv("SOLIS_KEY_ID", "key")
    monkeypatch.setenv("SOLIS_KEY_SECRET", "secret")
    monkeypatch.setattr(
        "solar_platform.services.performance_copilot_asset_audit.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("{}", encoding="utf-8")
    service = AssetRegisterAuditService(
        notion_service=FakeNotionAssetRegisterService([]),
        settings=SimpleNamespace(),
        legacy_mapping_path=mapping_path,
        checkers={},
    )

    result = service._fetch_solis_day_energy("1298491919450070492", date(2026, 3, 7))

    assert result == 84.2


def test_emig_adapter_maps_iso_z_timestamps_with_microseconds() -> None:
    from solar_platform.ingestion.emig_adapter import EMIGAdapter

    adapter = EMIGAdapter(api_key="dummy")
    raw = {
        "ts": "2026-03-07T00:00:00.000000Z",
        "activePower": {"value": 1200},
        "energy": {"value": 3400},
    }

    reading = adapter._map_reading(raw, plant_uid="ERS:00001", emig_id="INVERT:001")

    assert reading is not None
    assert reading.timestamp.isoformat() == "2026-03-07T00:00:00+00:00"
    assert reading.power_kw == pytest.approx(1200)


def test_emig_adapter_maps_import_active_power_watts_to_kw() -> None:
    from solar_platform.ingestion.emig_adapter import EMIGAdapter

    adapter = EMIGAdapter(api_key="dummy")
    raw = {
        "ts": "2026-03-07T06:45:00.000000Z",
        "importActivePower": {"value": 3003, "unit": "W"},
        "exportEnergy": {"value": 207887500, "unit": "Wh"},
    }

    reading = adapter._map_reading(raw, plant_uid="ERS:00001", emig_id="INVERT:002946")

    assert reading is not None
    assert reading.timestamp.isoformat() == "2026-03-07T06:45:00+00:00"
    assert reading.power_kw == pytest.approx(3.003)


@pytest.mark.asyncio
async def test_emig_adapter_fetch_readings_uses_bounded_device_concurrency(monkeypatch) -> None:
    from datetime import UTC, datetime

    from solar_platform.ingestion.emig_adapter import EMIGAdapter

    adapter = EMIGAdapter(api_key="dummy", rate_limit_rpm=1000, max_concurrent_devices=2)

    async def fake_get(path, params=None):  # noqa: ANN001
        assert params is None
        assert path == "/plant/ERS:00001"
        return {
            "meters": [
                {"type": "INVERTER", "emigId": "INV:1"},
                {"type": "INVERTER", "emigId": "INV:2"},
                {"type": "INVERTER", "emigId": "INV:3"},
            ]
        }

    active = 0
    peak = 0
    seen_devices: list[str] = []

    async def fake_fetch_device_readings(batch, plant_uid, emig_id, start, end):  # noqa: ANN001
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        seen_devices.append(emig_id)
        await asyncio.sleep(0.01)
        active -= 1

    monkeypatch.setattr(adapter, "_get", fake_get)
    monkeypatch.setattr(adapter, "_fetch_device_readings", fake_fetch_device_readings)

    batch = await adapter.fetch_readings(
        "ERS:00001",
        datetime(2026, 3, 7, tzinfo=UTC),
        datetime(2026, 3, 8, tzinfo=UTC),
    )

    assert batch.errors == []
    assert sorted(seen_devices) == ["INV:1", "INV:2", "INV:3"]
    assert peak == 2
