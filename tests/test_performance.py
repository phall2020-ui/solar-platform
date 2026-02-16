"""Performance and speed tests for the Solar Platform.

Validates that core operations (imports, queries, DataFrame ops, analysis init,
bulk inserts, concurrent reads, memory usage, validation, repository CRUD)
complete within generous but meaningful time budgets.

Run with:  pytest tests/test_performance.py -m performance -v
"""

from __future__ import annotations

import importlib
import math
import random
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pytest

from solar_platform.db.engine import DuckDBEngine

# ── custom marker ────────────────────────────────────────────────────────

pytestmark = pytest.mark.performance


# ── helpers: synthetic solar data generators ─────────────────────────────


def _generate_timestamps(
    n: int,
    start: datetime | None = None,
    freq_minutes: int = 15,
) -> list[datetime]:
    """Return *n* evenly-spaced UTC timestamps."""
    base = start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [base + timedelta(minutes=i * freq_minutes) for i in range(n)]


def _generate_readings_df(
    n: int,
    n_plants: int = 3,
    n_devices_per_plant: int = 2,
    start: datetime | None = None,
) -> pd.DataFrame:
    """Build a realistic readings DataFrame with *n* rows."""
    rng = np.random.default_rng(42)
    ts_list = _generate_timestamps(n, start=start)
    plant_uids = [f"uid-{i:04d}" for i in range(n_plants)]
    device_ids = [
        f"dev-{p}-{d}"
        for p in range(n_plants)
        for d in range(n_devices_per_plant)
    ]

    rows: dict[str, Any] = {
        "timestamp": ts_list,
        "plant_uid": rng.choice(plant_uids, size=n).tolist(),
        "device_id": rng.choice(device_ids, size=n).tolist(),
        "apparentPower_value": (rng.uniform(0.0, 500.0, size=n)).tolist(),
        "poaIrradiance_value": (rng.uniform(0.0, 1200.0, size=n)).tolist(),
        "ambientTemperature_value": (rng.uniform(-5.0, 40.0, size=n)).tolist(),
        "moduleTemperature_value": (rng.uniform(0.0, 70.0, size=n)).tolist(),
    }
    return pd.DataFrame(rows)


def _generate_solar_data_df(n: int) -> pd.DataFrame:
    """Build a realistic solar_data DataFrame with *n* rows."""
    rng = np.random.default_rng(99)
    sites = [f"Site-{i:03d}" for i in range(max(1, n // 12))]
    months = pd.date_range("2020-01-01", periods=12, freq="MS").strftime("%b-%y").tolist()

    records: list[dict[str, Any]] = []
    for _ in range(n):
        records.append(
            {
                "Site": rng.choice(sites),
                "Date": rng.choice(months),
                "PR": round(float(rng.uniform(0.70, 0.95)), 4),
                "Irradiance": round(float(rng.uniform(800, 1300)), 1),
                "Energy": round(float(rng.uniform(500, 5000)), 1),
                "Availability": round(float(rng.uniform(95, 100)), 2),
            }
        )
    return pd.DataFrame(records)


def _generate_validation_readings(n: int) -> list[dict[str, Any]]:
    """Generate *n* reading dicts suitable for the validation pipeline."""
    rng = random.Random(7)
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    readings: list[dict[str, Any]] = []
    for i in range(n):
        readings.append(
            {
                "timestamp": (base + timedelta(minutes=15 * i)).isoformat(),
                "power_kw": round(rng.uniform(0, 5000), 2),
                "energy_kwh": round(rng.uniform(0, 1250), 2),
                "poa_wm2": round(rng.uniform(0, 1200), 1),
                "ghi_wm2": round(rng.uniform(0, 1100), 1),
                "ambient_temp_c": round(rng.uniform(-5, 40), 1),
                "module_temp_c": round(rng.uniform(0, 65), 1),
                "wind_speed_ms": round(rng.uniform(0, 20), 1),
                "source": rng.choice(["juggle", "solargis", "manual"]),
            }
        )
    return readings


def _seed_large_readings(engine: DuckDBEngine, n: int = 10_000) -> pd.DataFrame:
    """Insert *n* synthetic readings into the engine's readings table and return the DF."""
    df = _generate_readings_df(n)
    with engine.connection(read_only=False) as conn:
        # Ensure table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                timestamp TIMESTAMP,
                plant_uid VARCHAR,
                device_id VARCHAR,
                apparentPower_value DOUBLE,
                poaIrradiance_value DOUBLE,
                ambientTemperature_value DOUBLE,
                moduleTemperature_value DOUBLE
            )
            """
        )
        conn.register("__perf_df", df)
        conn.execute("INSERT INTO readings SELECT * FROM __perf_df")
        conn.unregister("__perf_df")
    return df


def _seed_plants(engine: DuckDBEngine, n: int = 20) -> None:
    """Insert *n* plants into the engine."""
    with engine.connection(read_only=False) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plants (
                plant_uid VARCHAR PRIMARY KEY,
                alias VARCHAR,
                dc_size_kw DOUBLE,
                ac_size_kw DOUBLE,
                latitude DOUBLE,
                longitude DOUBLE,
                tilt DOUBLE,
                azimuth DOUBLE,
                timezone VARCHAR DEFAULT 'UTC'
            )
            """
        )
        for i in range(n):
            conn.execute(
                "INSERT OR IGNORE INTO plants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    f"uid-{i:04d}",
                    f"Plant {i}",
                    round(3000 + i * 500, 1),
                    round(2700 + i * 450, 1),
                    51.0 + i * 0.1,
                    -1.0 + i * 0.05,
                    30.0,
                    180.0,
                    "UTC",
                ],
            )


def _seed_solar_data(engine: DuckDBEngine, n: int = 500) -> pd.DataFrame:
    """Insert *n* solar_data rows."""
    df = _generate_solar_data_df(n)
    with engine.connection(read_only=False) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS solar_data (
                Site VARCHAR,
                Date VARCHAR,
                PR DOUBLE,
                Irradiance DOUBLE,
                Energy DOUBLE,
                Availability DOUBLE
            )
            """
        )
        conn.register("__perf_sd", df)
        conn.execute("INSERT INTO solar_data SELECT * FROM __perf_sd")
        conn.unregister("__perf_sd")
    return df


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def perf_engine(tmp_db_path):
    """A DuckDBEngine pre-seeded with large synthetic data."""
    duckdb.connect(str(tmp_db_path)).close()
    engine = DuckDBEngine(str(tmp_db_path))
    _seed_plants(engine, n=20)
    _seed_large_readings(engine, n=15_000)
    _seed_solar_data(engine, n=600)
    return engine


# =====================================================================
# 1. IMPORT TIMES
# =====================================================================


_CORE_MODULES = [
    "solar_platform.db.engine",
    "solar_platform.db.repository",
    "solar_platform.analysis",
    "solar_platform.analysis.base",
    "solar_platform.analysis.clipping",
    "solar_platform.analysis.curtailment",
    "solar_platform.analysis.degradation",
    "solar_platform.analysis.shading",
    "solar_platform.analysis.thermal",
    "solar_platform.analysis.waterfall",
    "solar_platform.analysis.pr_trending",
    "solar_platform.analysis.comparative",
    "solar_platform.data_quality",
    "solar_platform.data_quality.validators",
    "solar_platform.data_quality.quality_scorer",
    "solar_platform.data_quality.gap_detection",
    "solar_platform.ingestion",
    "solar_platform.reporting",
]


@pytest.mark.parametrize("module_name", _CORE_MODULES)
def test_import_time(module_name: str) -> None:
    """Each core module should import in under 2 seconds."""
    t0 = time.perf_counter()
    try:
        importlib.import_module(module_name)
    except ImportError:
        pytest.skip(f"Module not installed: {module_name}")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"Import of {module_name} took {elapsed:.3f}s (limit 2s)"


# =====================================================================
# 2. DUCKDB QUERY PERFORMANCE (10k+ rows)
# =====================================================================


class TestDuckDBQueryPerformance:
    """Query performance on a 15k-row readings table."""

    def test_count_query(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        rows = perf_engine.execute("SELECT COUNT(*) FROM readings")
        elapsed = time.perf_counter() - t0
        assert rows[0][0] >= 15_000
        assert elapsed < 2.0, f"COUNT(*) took {elapsed:.3f}s"

    def test_group_by_plant(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        df = perf_engine.execute_df(
            "SELECT plant_uid, COUNT(*) AS cnt, AVG(poaIrradiance_value) AS avg_poa "
            "FROM readings GROUP BY plant_uid ORDER BY cnt DESC"
        )
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 2.0, f"GROUP BY query took {elapsed:.3f}s"

    def test_time_range_filter(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        df = perf_engine.execute_df(
            "SELECT * FROM readings "
            "WHERE timestamp BETWEEN '2025-01-01' AND '2025-02-01' "
            "ORDER BY timestamp"
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"Range filter took {elapsed:.3f}s"

    def test_aggregation_with_window(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        df = perf_engine.execute_df(
            "SELECT plant_uid, timestamp, apparentPower_value, "
            "AVG(apparentPower_value) OVER (PARTITION BY plant_uid ORDER BY timestamp "
            "ROWS BETWEEN 3 PRECEDING AND 3 FOLLOWING) AS rolling_avg "
            "FROM readings ORDER BY plant_uid, timestamp"
        )
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 5.0, f"Window function took {elapsed:.3f}s"

    def test_join_plants_readings(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        df = perf_engine.execute_df(
            "SELECT p.alias, COUNT(*) AS cnt, SUM(r.apparentPower_value) AS total_power "
            "FROM readings r JOIN plants p ON r.plant_uid = p.plant_uid "
            "GROUP BY p.alias ORDER BY total_power DESC"
        )
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 3.0, f"JOIN + GROUP BY took {elapsed:.3f}s"

    def test_solar_data_pivot(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        df = perf_engine.execute_df(
            'SELECT "Site", AVG("PR") AS avg_pr, SUM("Energy") AS total_energy, '
            'MIN("Availability") AS min_avail '
            'FROM solar_data GROUP BY "Site" ORDER BY total_energy DESC'
        )
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 2.0, f"Solar data pivot took {elapsed:.3f}s"


# =====================================================================
# 3. DATAFRAME OPERATIONS PERFORMANCE
# =====================================================================


class TestDataFrameOpsPerformance:
    """Pandas operations on realistic-sized DataFrames."""

    def test_groupby_agg(self) -> None:
        df = _generate_readings_df(50_000)
        t0 = time.perf_counter()
        result = df.groupby("plant_uid").agg(
            avg_power=("apparentPower_value", "mean"),
            max_irr=("poaIrradiance_value", "max"),
            reading_count=("timestamp", "count"),
        )
        elapsed = time.perf_counter() - t0
        assert not result.empty
        assert elapsed < 5.0, f"groupby took {elapsed:.3f}s"

    def test_resample_30min(self) -> None:
        df = _generate_readings_df(20_000)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
        t0 = time.perf_counter()
        resampled = df[["apparentPower_value", "poaIrradiance_value"]].resample("30min").mean()
        elapsed = time.perf_counter() - t0
        assert not resampled.empty
        assert elapsed < 5.0, f"resample took {elapsed:.3f}s"

    def test_merge_two_dataframes(self) -> None:
        readings = _generate_readings_df(30_000)
        plant_info = pd.DataFrame(
            {
                "plant_uid": [f"uid-{i:04d}" for i in range(10)],
                "capacity_kw": [3000 + i * 500 for i in range(10)],
                "region": [f"Region-{i % 3}" for i in range(10)],
            }
        )
        t0 = time.perf_counter()
        merged = readings.merge(plant_info, on="plant_uid", how="left")
        elapsed = time.perf_counter() - t0
        assert len(merged) == len(readings)
        assert elapsed < 5.0, f"merge took {elapsed:.3f}s"

    def test_rolling_window(self) -> None:
        df = _generate_readings_df(20_000)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp")
        t0 = time.perf_counter()
        df["rolling_power"] = df["apparentPower_value"].rolling(window=96, min_periods=1).mean()
        elapsed = time.perf_counter() - t0
        assert df["rolling_power"].notna().all()
        assert elapsed < 5.0, f"rolling took {elapsed:.3f}s"

    def test_pivot_table(self) -> None:
        sd = _generate_solar_data_df(2_000)
        t0 = time.perf_counter()
        pivot = sd.pivot_table(
            values="Energy",
            index="Site",
            columns="Date",
            aggfunc="sum",
            fill_value=0,
        )
        elapsed = time.perf_counter() - t0
        assert not pivot.empty
        assert elapsed < 5.0, f"pivot_table took {elapsed:.3f}s"


# =====================================================================
# 4. ANALYSIS ENGINE INITIALISATION SPEED
# =====================================================================


class TestAnalysisEngineInitSpeed:
    """Analysis engine classes should instantiate fast."""

    _ENGINE_CLASSES = [
        ("solar_platform.analysis.clipping", "ClippingEngine"),
        ("solar_platform.analysis.curtailment", "CurtailmentEngine"),
        ("solar_platform.analysis.degradation", "DegradationEngine"),
        ("solar_platform.analysis.shading", "ShadingEngine"),
        ("solar_platform.analysis.thermal", "ThermalLossEngine"),
        ("solar_platform.analysis.waterfall", "LossWaterfallEngine"),
        ("solar_platform.analysis.pr_trending", "PRTrendingEngine"),
        ("solar_platform.analysis.comparative", "ComparativeEngine"),
        ("solar_platform.analysis.fouling", "FoulingEngine"),
    ]

    @pytest.mark.parametrize("mod_path,cls_name", _ENGINE_CLASSES)
    def test_init_speed(self, mod_path: str, cls_name: str, perf_engine: DuckDBEngine) -> None:
        try:
            mod = importlib.import_module(mod_path)
        except ImportError:
            pytest.skip(f"Cannot import {mod_path}")

        cls = getattr(mod, cls_name, None)
        if cls is None:
            pytest.skip(f"{cls_name} not found in {mod_path}")

        t0 = time.perf_counter()
        for _ in range(100):
            try:
                cls(engine=perf_engine)
            except TypeError:
                # Some engines may not accept engine kwarg; try no-arg
                cls()
        elapsed = time.perf_counter() - t0
        per_init = elapsed / 100
        assert per_init < 0.05, f"{cls_name} init took {per_init:.4f}s each (limit 50ms)"


# =====================================================================
# 5. BULK INSERT PERFORMANCE
# =====================================================================


class TestBulkInsertPerformance:
    """Verify bulk_insert_df can handle large DataFrames quickly."""

    def test_bulk_insert_10k(self, test_engine: DuckDBEngine) -> None:
        with test_engine.connection(read_only=False) as conn:
            conn.execute(
                """
                CREATE TABLE readings (
                    timestamp TIMESTAMP,
                    plant_uid VARCHAR,
                    device_id VARCHAR,
                    apparentPower_value DOUBLE,
                    poaIrradiance_value DOUBLE,
                    ambientTemperature_value DOUBLE,
                    moduleTemperature_value DOUBLE
                )
                """
            )
        df = _generate_readings_df(10_000)
        t0 = time.perf_counter()
        inserted = test_engine.bulk_insert_df("readings", df)
        elapsed = time.perf_counter() - t0
        assert inserted == 10_000
        assert elapsed < 5.0, f"Bulk insert of 10k rows took {elapsed:.3f}s"

    def test_bulk_insert_50k(self, tmp_db_path) -> None:
        duckdb.connect(str(tmp_db_path)).close()
        engine = DuckDBEngine(str(tmp_db_path))
        with engine.connection(read_only=False) as conn:
            conn.execute(
                """
                CREATE TABLE readings (
                    timestamp TIMESTAMP,
                    plant_uid VARCHAR,
                    device_id VARCHAR,
                    apparentPower_value DOUBLE,
                    poaIrradiance_value DOUBLE,
                    ambientTemperature_value DOUBLE,
                    moduleTemperature_value DOUBLE
                )
                """
            )
        df = _generate_readings_df(50_000)
        t0 = time.perf_counter()
        inserted = engine.bulk_insert_df("readings", df)
        elapsed = time.perf_counter() - t0
        assert inserted == 50_000
        assert elapsed < 10.0, f"Bulk insert of 50k rows took {elapsed:.3f}s"

    def test_bulk_insert_solar_data(self, test_engine: DuckDBEngine) -> None:
        with test_engine.connection(read_only=False) as conn:
            conn.execute(
                """
                CREATE TABLE solar_data (
                    Site VARCHAR, Date VARCHAR, PR DOUBLE,
                    Irradiance DOUBLE, Energy DOUBLE, Availability DOUBLE
                )
                """
            )
        df = _generate_solar_data_df(5_000)
        t0 = time.perf_counter()
        inserted = test_engine.bulk_insert_df("solar_data", df)
        elapsed = time.perf_counter() - t0
        assert inserted == 5_000
        assert elapsed < 5.0, f"Bulk insert of 5k solar_data rows took {elapsed:.3f}s"


# =====================================================================
# 6. CONCURRENT READ PERFORMANCE
# =====================================================================


class TestConcurrentReadPerformance:
    """Multiple threads reading from the same DuckDB file concurrently."""

    def test_concurrent_reads(self, perf_engine: DuckDBEngine) -> None:
        queries = [
            "SELECT COUNT(*) FROM readings",
            "SELECT plant_uid, AVG(apparentPower_value) FROM readings GROUP BY plant_uid",
            "SELECT * FROM plants ORDER BY alias",
            'SELECT "Site", SUM("Energy") FROM solar_data GROUP BY "Site"',
            "SELECT COUNT(DISTINCT device_id) FROM readings",
        ]

        def _run_query(q: str) -> float:
            t0 = time.perf_counter()
            perf_engine.execute(q)
            return time.perf_counter() - t0

        t_total = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_run_query, q) for q in queries * 3]
            times = [f.result() for f in as_completed(futures)]
        total_elapsed = time.perf_counter() - t_total

        assert all(t < 5.0 for t in times), f"Some queries exceeded 5s: {times}"
        assert total_elapsed < 15.0, f"Total concurrent reads took {total_elapsed:.3f}s"

    def test_concurrent_read_write_isolation(self, perf_engine: DuckDBEngine) -> None:
        """Readers should not block writers and vice-versa within reasonable time."""

        def _reader() -> int:
            rows = perf_engine.execute("SELECT COUNT(*) FROM readings")
            return rows[0][0]

        def _writer() -> int:
            small_df = _generate_readings_df(100)
            return perf_engine.bulk_insert_df("readings", small_df)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = []
            for _ in range(5):
                futs.append(pool.submit(_reader))
            futs.append(pool.submit(_writer))
            results = []
            for f in as_completed(futs):
                try:
                    results.append(f.result())
                except Exception:
                    # DuckDB may raise on concurrent write; acceptable for this test
                    results.append(-1)
        elapsed = time.perf_counter() - t0
        assert elapsed < 10.0, f"Concurrent r/w took {elapsed:.3f}s"


# =====================================================================
# 7. MEMORY USAGE
# =====================================================================


class TestMemoryUsage:
    """Ensure memory doesn't explode for large operations."""

    def test_memory_large_dataframe_creation(self) -> None:
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        df = _generate_readings_df(100_000)
        _ = df.groupby("plant_uid").agg({"apparentPower_value": ["mean", "max", "min"]})

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_increase_mb = sum(s.size_diff for s in stats) / (1024 * 1024)
        # 100k rows with 7 float columns ≈ 5-20 MB; allow generous headroom
        assert total_increase_mb < 500, f"Memory increased by {total_increase_mb:.1f} MB (limit 500 MB)"

    def test_memory_bulk_insert(self, tmp_db_path) -> None:
        duckdb.connect(str(tmp_db_path)).close()
        engine = DuckDBEngine(str(tmp_db_path))
        with engine.connection(read_only=False) as conn:
            conn.execute(
                """
                CREATE TABLE readings (
                    timestamp TIMESTAMP, plant_uid VARCHAR, device_id VARCHAR,
                    apparentPower_value DOUBLE, poaIrradiance_value DOUBLE,
                    ambientTemperature_value DOUBLE, moduleTemperature_value DOUBLE
                )
                """
            )

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        df = _generate_readings_df(50_000)
        engine.bulk_insert_df("readings", df)

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_increase_mb = sum(s.size_diff for s in stats) / (1024 * 1024)
        assert total_increase_mb < 500, f"Memory increased by {total_increase_mb:.1f} MB (limit 500 MB)"

    def test_memory_repeated_queries(self, perf_engine: DuckDBEngine) -> None:
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for _ in range(50):
            perf_engine.execute_df("SELECT * FROM readings LIMIT 1000")

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_increase_mb = sum(s.size_diff for s in stats) / (1024 * 1024)
        # Repeated queries should not leak memory unboundedly
        assert total_increase_mb < 200, f"Memory increased by {total_increase_mb:.1f} MB after 50 queries"


# =====================================================================
# 8. DATA QUALITY VALIDATION SPEED
# =====================================================================


class TestDataQualityValidationSpeed:
    """Validator pipeline throughput on large reading sets."""

    def test_run_validation_1k_readings(self) -> None:
        from solar_platform.data_quality.validators import run_validation

        readings = _generate_validation_readings(1_000)
        plant_config = {"capacity_kw": 5000}

        t0 = time.perf_counter()
        for r in readings:
            run_validation(r, plant_config)
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"Validating 1k readings took {elapsed:.3f}s"

    def test_run_validation_5k_readings(self) -> None:
        from solar_platform.data_quality.validators import run_validation

        readings = _generate_validation_readings(5_000)
        plant_config = {"capacity_kw": 5000}

        t0 = time.perf_counter()
        for r in readings:
            run_validation(r, plant_config)
        elapsed = time.perf_counter() - t0
        assert elapsed < 15.0, f"Validating 5k readings took {elapsed:.3f}s"

    def test_range_validator_throughput(self) -> None:
        from solar_platform.data_quality.validators import RangeValidator

        validator = RangeValidator()
        readings = _generate_validation_readings(10_000)
        plant_config: dict[str, Any] = {}

        t0 = time.perf_counter()
        total_findings = 0
        for r in readings:
            total_findings += len(validator.validate(r, plant_config))
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"RangeValidator on 10k readings took {elapsed:.3f}s"

    def test_flatline_validator_series(self) -> None:
        from solar_platform.data_quality.validators import FlatLineValidator

        validator = FlatLineValidator(min_repeat=6)
        # Generate readings where some values are deliberately flat
        readings = _generate_validation_readings(5_000)
        # Inject flat-line segments
        for i in range(100, 120):
            readings[i]["power_kw"] = 1234.0
        plant_config: dict[str, Any] = {}

        t0 = time.perf_counter()
        findings = validator.validate_series(readings, plant_config)
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"FlatLineValidator series on 5k readings took {elapsed:.3f}s"

    def test_quality_scorer_batch(self) -> None:
        try:
            from solar_platform.data_quality.quality_scorer import QualityScorer
        except ImportError:
            pytest.skip("QualityScorer not available")

        scorer = QualityScorer()
        n = 500
        readings = _generate_validation_readings(n)
        df = pd.DataFrame(readings)
        plant_config = {"capacity_kw": 5000}

        t0 = time.perf_counter()
        scored = scorer.score_batch(df, plant_config)
        elapsed = time.perf_counter() - t0
        assert "quality_score" in scored.columns
        assert len(scored) == n
        assert elapsed < 10.0, f"QualityScorer.score_batch on {n} rows took {elapsed:.3f}s"


# =====================================================================
# 9. REPOSITORY CRUD PERFORMANCE
# =====================================================================


class TestRepositoryCRUDPerformance:
    """Repository operations at realistic volumes."""

    def test_plant_repository_list_all(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import PlantRepository

        repo = PlantRepository(engine=perf_engine)
        t0 = time.perf_counter()
        for _ in range(100):
            df = repo.get_all()
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 5.0, f"100x PlantRepository.get_all took {elapsed:.3f}s"

    def test_plant_repository_get_by_uid(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import PlantRepository

        repo = PlantRepository(engine=perf_engine)
        t0 = time.perf_counter()
        for i in range(20):
            result = repo.get_by_uid(f"uid-{i:04d}")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"20x get_by_uid took {elapsed:.3f}s"

    def test_plant_repository_list_aliases(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import PlantRepository

        repo = PlantRepository(engine=perf_engine)
        t0 = time.perf_counter()
        for _ in range(100):
            aliases = repo.list_aliases()
        elapsed = time.perf_counter() - t0
        assert len(aliases) > 0
        assert elapsed < 5.0, f"100x list_aliases took {elapsed:.3f}s"

    def test_readings_repository_get_readings(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import ReadingsRepository

        repo = ReadingsRepository(engine=perf_engine)
        t0 = time.perf_counter()
        df = repo.get_readings(
            "uid-0000",
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"ReadingsRepository.get_readings took {elapsed:.3f}s"

    def test_readings_repository_multiple_plants(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import ReadingsRepository

        repo = ReadingsRepository(engine=perf_engine)
        t0 = time.perf_counter()
        for i in range(3):
            repo.get_readings(f"uid-{i:04d}")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"3x get_readings took {elapsed:.3f}s"

    def test_solar_data_repository_get_monthly(self, perf_engine: DuckDBEngine) -> None:
        from solar_platform.db.repository import SolarDataRepository

        repo = SolarDataRepository(engine=perf_engine)
        t0 = time.perf_counter()
        for _ in range(50):
            df = repo.get_monthly()
        elapsed = time.perf_counter() - t0
        assert not df.empty
        assert elapsed < 5.0, f"50x get_monthly took {elapsed:.3f}s"

    def test_upsert_performance(self, perf_engine: DuckDBEngine) -> None:
        """Upsert 50 plant records and verify speed."""
        t0 = time.perf_counter()
        for i in range(50):
            perf_engine.execute_upsert(
                "plants",
                {
                    "plant_uid": f"uid-{i:04d}",
                    "alias": f"Updated Plant {i}",
                    "dc_size_kw": 4000.0 + i,
                    "ac_size_kw": 3600.0 + i,
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "tilt": 30.0,
                    "azimuth": 180.0,
                    "timezone": "UTC",
                },
                ["plant_uid"],
            )
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"50 upserts took {elapsed:.3f}s"

    def test_execute_insert_performance(self, perf_engine: DuckDBEngine) -> None:
        """Single-row inserts for 50 readings."""
        t0 = time.perf_counter()
        base = datetime(2030, 1, 1, tzinfo=timezone.utc)
        for i in range(50):
            perf_engine.execute_insert(
                "readings",
                {
                    "timestamp": base + timedelta(minutes=15 * i),
                    "plant_uid": "uid-0000",
                    "device_id": "dev-perf",
                    "apparentPower_value": 100.0 + i,
                    "poaIrradiance_value": 500.0 + i,
                    "ambientTemperature_value": 20.0,
                    "moduleTemperature_value": 35.0,
                },
            )
        elapsed = time.perf_counter() - t0
        assert elapsed < 10.0, f"50 single inserts took {elapsed:.3f}s"


# =====================================================================
# 10. ENGINE API PERFORMANCE
# =====================================================================


class TestEngineAPIPerformance:
    """DuckDBEngine method-level performance."""

    def test_table_exists_speed(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        for _ in range(100):
            perf_engine.table_exists("readings")
            perf_engine.table_exists("plants")
            perf_engine.table_exists("nonexistent_table")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"300x table_exists took {elapsed:.3f}s"

    def test_get_tables_speed(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        for _ in range(100):
            tables = perf_engine.get_tables()
        elapsed = time.perf_counter() - t0
        assert len(tables) >= 3
        assert elapsed < 5.0, f"100x get_tables took {elapsed:.3f}s"

    def test_execute_df_roundtrip(self, perf_engine: DuckDBEngine) -> None:
        """Fetch full readings table as DataFrame and verify shape."""
        t0 = time.perf_counter()
        df = perf_engine.execute_df("SELECT * FROM readings")
        elapsed = time.perf_counter() - t0
        assert len(df) >= 15_000
        assert elapsed < 5.0, f"Full readings fetch took {elapsed:.3f}s"

    def test_transaction_commit_speed(self, perf_engine: DuckDBEngine) -> None:
        t0 = time.perf_counter()
        for _ in range(20):
            with perf_engine.transaction() as conn:
                conn.execute(
                    "INSERT INTO readings VALUES "
                    "('2030-06-01', 'uid-0000', 'dev-tx', 100.0, 500.0, 20.0, 35.0)"
                )
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"20 transactions took {elapsed:.3f}s"


# =====================================================================
# 11. END-TO-END SYNTHETIC WORKFLOW
# =====================================================================


class TestEndToEndWorkflow:
    """Simulate a realistic ingest → query → analyse workflow."""

    def test_ingest_query_analyse_pipeline(self, tmp_db_path) -> None:
        """Full pipeline: create schema, bulk insert, query, aggregate."""
        duckdb.connect(str(tmp_db_path)).close()
        engine = DuckDBEngine(str(tmp_db_path))

        # Create schema
        with engine.connection(read_only=False) as conn:
            conn.execute(
                """
                CREATE TABLE plants (
                    plant_uid VARCHAR PRIMARY KEY, alias VARCHAR,
                    dc_size_kw DOUBLE, ac_size_kw DOUBLE,
                    latitude DOUBLE, longitude DOUBLE,
                    tilt DOUBLE, azimuth DOUBLE, timezone VARCHAR DEFAULT 'UTC'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE readings (
                    timestamp TIMESTAMP, plant_uid VARCHAR, device_id VARCHAR,
                    apparentPower_value DOUBLE, poaIrradiance_value DOUBLE,
                    ambientTemperature_value DOUBLE, moduleTemperature_value DOUBLE
                )
                """
            )

        pipeline_start = time.perf_counter()

        # Ingest plants
        _seed_plants(engine, n=10)

        # Ingest readings
        df = _generate_readings_df(20_000, n_plants=10)
        engine.bulk_insert_df("readings", df)

        # Query and aggregate
        summary = engine.execute_df(
            "SELECT p.alias, COUNT(*) AS readings, "
            "AVG(r.apparentPower_value) AS avg_power, "
            "AVG(r.poaIrradiance_value) AS avg_irr "
            "FROM readings r JOIN plants p ON r.plant_uid = p.plant_uid "
            "GROUP BY p.alias ORDER BY avg_power DESC"
        )

        # Compute daily energy (simulated)
        daily = engine.execute_df(
            "SELECT plant_uid, DATE_TRUNC('day', timestamp) AS day, "
            "SUM(apparentPower_value * 0.25) AS energy_kwh "
            "FROM readings GROUP BY plant_uid, day ORDER BY plant_uid, day"
        )

        pipeline_elapsed = time.perf_counter() - pipeline_start

        assert not summary.empty
        assert not daily.empty
        assert pipeline_elapsed < 10.0, f"Full pipeline took {pipeline_elapsed:.3f}s"

    def test_large_scale_validation_pipeline(self) -> None:
        """Generate, validate, and score a large batch of readings."""
        try:
            from solar_platform.data_quality.validators import RangeValidator, run_validation
        except ImportError:
            pytest.skip("Validators not available")

        n = 3_000
        readings = _generate_validation_readings(n)
        plant_config = {"capacity_kw": 5000}

        t0 = time.perf_counter()

        error_count = 0
        warning_count = 0
        for r in readings:
            report = run_validation(r, plant_config)
            error_count += report.error_count
            warning_count += report.warning_count

        elapsed = time.perf_counter() - t0
        assert elapsed < 10.0, f"Validation pipeline on {n} readings took {elapsed:.3f}s"
