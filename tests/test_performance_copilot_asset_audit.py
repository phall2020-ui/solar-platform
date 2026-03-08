from __future__ import annotations

from datetime import date
from types import SimpleNamespace

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
        self.database_upserts: list[tuple[str, str, str, dict[str, object]]] = []

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

    def upsert_database_page(
        self,
        database_id: str,
        match_field: str,
        match_value: str,
        properties: dict[str, object],
    ) -> str | None:
        self.database_upserts.append((database_id, match_field, match_value, properties))
        return "page_triage"


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
    assert record["severity"] == "medium"
    assert record["am_contact_name"] == "Alice Manager"
    assert record["am_contact_email"] == "alice@example.com"
    assert "BAE Fylde" in record["email_subject"]
    assert "Alice Manager" in record["email_draft"]
    assert "Newfold Farm" in record["evidence_summary"]
    assert record["row_key"] == "2026-03-07|BAE Fylde|source_unconfigured"


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
