"""Tests for services.database.repository."""

from __future__ import annotations

from datetime import datetime

from solar_platform.db.repository import PlantRepository, ReadingsRepository, SolarDataRepository


def test_plant_repository_reads_seed_data(seeded_engine):
    repo = PlantRepository(engine=seeded_engine)

    df = repo.get_all()
    assert list(df["alias"]) == ["Green Fields", "Hilltop Solar", "Sunny Acres"]

    by_uid = repo.get_by_uid("uid-001")
    assert by_uid is not None
    assert by_uid["alias"] == "Sunny Acres"

    by_alias = repo.get_by_alias("Green Fields")
    assert by_alias is not None
    assert by_alias["plant_uid"] == "uid-002"

    assert repo.list_aliases() == ["Green Fields", "Hilltop Solar", "Sunny Acres"]
    assert repo.list_uids() == ["uid-001", "uid-002", "uid-003"]


def test_plant_repository_upsert_updates_existing_row(seeded_engine):
    repo = PlantRepository(engine=seeded_engine)

    repo.upsert({
        "plant_uid": "uid-003",
        "alias": "Hilltop Solar Updated",
        "dc_size_kw": 3333.0,
        "ac_size_kw": 2700.0,
        "latitude": 50.8,
        "longitude": -2.1,
        "tilt": 35.0,
        "azimuth": 175.0,
        "timezone": "UTC",
    })

    updated = repo.get_by_uid("uid-003")
    assert updated is not None
    assert updated["alias"] == "Hilltop Solar Updated"
    assert updated["dc_size_kw"] == 3333.0


def test_readings_repository_filters_by_time_device_and_limit(seeded_engine):
    repo = ReadingsRepository(engine=seeded_engine)

    all_rows = repo.get_readings("uid-001")
    assert len(all_rows) == 3

    filtered = repo.get_readings(
        "uid-001",
        start=datetime(2026, 1, 1, 0, 10),
        end=datetime(2026, 1, 1, 0, 30),
        device_id="dev-1",
    )
    assert len(filtered) == 1
    assert filtered.iloc[0]["device_id"] == "dev-1"

    limited = repo.get_readings("uid-001", limit=2)
    assert len(limited) == 2


def test_readings_repository_supports_ts_emig_id_schema(test_engine):
    test_engine.execute("CREATE TABLE readings (ts TIMESTAMP, plant_uid VARCHAR, emig_id VARCHAR, activePower_value DOUBLE)")
    test_engine.execute(
        """
        INSERT INTO readings (ts, plant_uid, emig_id, activePower_value) VALUES
        ('2026-01-01 00:00:00', 'uid-001', 'inv-1', 10.0),
        ('2026-01-01 00:15:00', 'uid-001', 'inv-2', 20.0),
        ('2026-01-01 00:30:00', 'uid-001', 'inv-1', 30.0)
        """
    )

    repo = ReadingsRepository(engine=test_engine)
    filtered = repo.get_readings("uid-001", device_id="inv-1")

    assert len(filtered) == 2
    assert sorted(filtered["emig_id"].unique().tolist()) == ["inv-1"]


def test_solar_data_repository_filters_and_lists(seeded_engine):
    repo = SolarDataRepository(engine=seeded_engine)

    sites = repo.list_sites()
    months = repo.list_months()
    january_rows = repo.get_monthly(month="Jan-24")
    plant_b_rows = repo.get_monthly(month="Jan-24", site="Plant B")

    assert sites == ["Plant A", "Plant B", "Plant C"]
    assert months == ["Jan-24"]
    assert len(january_rows) == 3
    assert len(plant_b_rows) == 1
