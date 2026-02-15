"""DuckDB query performance benchmarks.

Usage:
    python -m tests.benchmarks.bench_queries [--plants N] [--days N]
"""

from __future__ import annotations

import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from solar_platform.db.engine import DuckDBEngine
from solar_platform.db.repository import PlantRepository, ReadingsRepository, SolarDataRepository
from tests.benchmarks.generate_load_data import seed_benchmark_db


# ── Benchmark helper ─────────────────────────────────────────────────────


def benchmark(name: str, func, iterations: int = 10) -> dict:
    """Time a function over multiple iterations and return stats."""
    times: list[float] = []
    result = None
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - t0
        times.append(elapsed)

    avg = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    p50 = statistics.median(times)
    mn = min(times)
    mx = max(times)

    print(f"  {name:<45s}  avg={avg*1000:7.1f}ms  p50={p50*1000:7.1f}ms  p95={p95*1000:7.1f}ms  min={mn*1000:6.1f}ms  max={mx*1000:6.1f}ms")
    return {
        "name": name,
        "avg_ms": round(avg * 1000, 2),
        "p50_ms": round(p50 * 1000, 2),
        "p95_ms": round(p95 * 1000, 2),
        "min_ms": round(mn * 1000, 2),
        "max_ms": round(mx * 1000, 2),
        "iterations": iterations,
    }


# ── Benchmark suite ──────────────────────────────────────────────────────


def run_benchmarks(db_path: str, iterations: int = 10) -> list[dict]:
    """Run all query benchmarks against the given database."""
    engine = DuckDBEngine(db_path)
    plant_repo = PlantRepository(engine=engine)
    readings_repo = ReadingsRepository(engine=engine)
    solar_repo = SolarDataRepository(engine=engine)

    # Discover available plants
    all_plants = plant_repo.list_uids()
    first_plant = all_plants[0] if all_plants else "bench-0000"

    results: list[dict] = []
    print(f"\n{'='*90}")
    print(f"  DuckDB Query Benchmarks ({len(all_plants)} plants, {iterations} iterations)")
    print(f"{'='*90}")

    # 1. List all plants
    results.append(benchmark(
        "PlantRepository.list_all()",
        lambda: plant_repo.list_all(),
        iterations=iterations,
    ))

    # 2. Get plant by UID
    results.append(benchmark(
        "PlantRepository.get_by_uid()",
        lambda: plant_repo.get_by_uid(first_plant),
        iterations=iterations,
    ))

    # 3. List all UIDs
    results.append(benchmark(
        "PlantRepository.list_uids()",
        lambda: plant_repo.list_uids(),
        iterations=iterations,
    ))

    # 4. 30-day readings query (single plant)
    start_30d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_30d = start_30d + timedelta(days=30)
    results.append(benchmark(
        "ReadingsRepository.get_readings(30d)",
        lambda: readings_repo.get_readings(first_plant, start=start_30d, end=end_30d),
        iterations=iterations,
    ))

    # 5. 7-day readings query
    end_7d = start_30d + timedelta(days=7)
    results.append(benchmark(
        "ReadingsRepository.get_readings(7d)",
        lambda: readings_repo.get_readings(first_plant, start=start_30d, end=end_7d),
        iterations=iterations,
    ))

    # 6. Readings with device filter
    results.append(benchmark(
        "ReadingsRepository.get_readings(device_filter)",
        lambda: readings_repo.get_readings(first_plant, start=start_30d, end=end_30d, device_id="dev-1"),
        iterations=iterations,
    ))

    # 7. Readings with limit
    results.append(benchmark(
        "ReadingsRepository.get_readings(limit=100)",
        lambda: readings_repo.get_readings(first_plant, start=start_30d, end=end_30d, limit=100),
        iterations=iterations,
    ))

    # 8. Full-table count query
    results.append(benchmark(
        "COUNT(*) readings",
        lambda: engine.execute("SELECT COUNT(*) FROM readings"),
        iterations=iterations,
    ))

    # 9. Portfolio aggregate: daily energy by plant
    results.append(benchmark(
        "Daily rollup by plant (SQL agg)",
        lambda: engine.execute_df(
            "SELECT plant_uid, CAST(timestamp AS DATE) AS date, AVG(apparentPower_value) AS avg_power "
            "FROM readings GROUP BY plant_uid, CAST(timestamp AS DATE) ORDER BY plant_uid, date"
        ),
        iterations=iterations,
    ))

    # 10. Solar data: monthly query
    results.append(benchmark(
        "SolarDataRepository.get_monthly()",
        lambda: solar_repo.get_monthly(),
        iterations=iterations,
    ))

    # 11. Table existence check
    results.append(benchmark(
        "DuckDBEngine.table_exists('readings')",
        lambda: engine.table_exists("readings"),
        iterations=iterations,
    ))

    # 12. Get tables list
    results.append(benchmark(
        "DuckDBEngine.get_tables()",
        lambda: engine.get_tables(),
        iterations=iterations,
    ))

    print(f"{'='*90}\n")
    return results


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DuckDB query benchmarks")
    parser.add_argument("--plants", type=int, default=10, help="Number of plants to seed")
    parser.add_argument("--days", type=int, default=30, help="Days of readings per plant")
    parser.add_argument("--iterations", type=int, default=10, help="Benchmark iterations")
    parser.add_argument("--db", type=str, default=None, help="Path to existing bench DB (skip seeding)")
    args = parser.parse_args()

    if args.db and Path(args.db).exists():
        db_path = args.db
        print(f"Using existing database: {db_path}")
    else:
        db_path = tempfile.mktemp(suffix=".duckdb")
        print(f"Seeding benchmark database at {db_path}...")
        seed_benchmark_db(db_path, num_plants=args.plants, days=args.days)

    run_benchmarks(db_path, iterations=args.iterations)


if __name__ == "__main__":
    main()
