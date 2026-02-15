"""Analysis engine performance benchmarks.

Usage:
    python -m tests.benchmarks.bench_analysis [--plants N] [--days N]
"""

from __future__ import annotations

import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from solar_platform.analysis.clipping import ClippingEngine
from solar_platform.db.engine import DuckDBEngine
from tests.benchmarks.generate_load_data import seed_benchmark_db


# ── Benchmark helper ─────────────────────────────────────────────────────


def benchmark(name: str, func, iterations: int = 10) -> dict:
    """Time a function over multiple iterations and return stats."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func()
        elapsed = time.perf_counter() - t0
        times.append(elapsed)

    avg = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    p50 = statistics.median(times)
    mn = min(times)
    mx = max(times)

    print(f"  {name:<50s}  avg={avg*1000:7.1f}ms  p50={p50*1000:7.1f}ms  p95={p95*1000:7.1f}ms  min={mn*1000:6.1f}ms  max={mx*1000:6.1f}ms")
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


def run_benchmarks(db_path: str, iterations: int = 5) -> list[dict]:
    """Run all analysis engine benchmarks."""
    engine = DuckDBEngine(db_path)

    # Discover plants
    from solar_platform.db.repository import PlantRepository
    plant_repo = PlantRepository(engine=engine)
    all_uids = plant_repo.list_uids()
    if not all_uids:
        print("No plants in database — skipping analysis benchmarks.")
        return []

    first_plant = all_uids[0]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end_7d = start + timedelta(days=7)
    end_30d = start + timedelta(days=30)

    results: list[dict] = []
    print(f"\n{'='*95}")
    print(f"  Analysis Engine Benchmarks ({len(all_uids)} plants, {iterations} iterations)")
    print(f"{'='*95}")

    # 1. ClippingEngine — 7-day window
    clipping = ClippingEngine(engine=engine)
    results.append(benchmark(
        "ClippingEngine.run(7d)",
        lambda: clipping.run(first_plant, start, end_7d),
        iterations=iterations,
    ))

    # 2. ClippingEngine — 30-day window
    results.append(benchmark(
        "ClippingEngine.run(30d)",
        lambda: clipping.run(first_plant, start, end_30d),
        iterations=iterations,
    ))

    # 3. Try ThermalLossEngine
    try:
        from solar_platform.analysis.thermal import ThermalLossEngine
        thermal = ThermalLossEngine(engine=engine)
        results.append(benchmark(
            "ThermalLossEngine.run(30d)",
            lambda: thermal.run(first_plant, start, end_30d),
            iterations=iterations,
        ))
    except Exception as e:
        print(f"  ThermalLossEngine skipped: {e}")

    # 4. Try CurtailmentEngine
    try:
        from solar_platform.analysis.curtailment import CurtailmentEngine
        curtailment = CurtailmentEngine(engine=engine)
        results.append(benchmark(
            "CurtailmentEngine.run(30d)",
            lambda: curtailment.run(first_plant, start, end_30d),
            iterations=iterations,
        ))
    except Exception as e:
        print(f"  CurtailmentEngine skipped: {e}")

    # 5. Try FoulingEngine
    try:
        from solar_platform.analysis.fouling import FoulingEngine
        fouling = FoulingEngine(engine=engine)
        results.append(benchmark(
            "FoulingEngine.run(30d)",
            lambda: fouling.run(first_plant, start, end_30d),
            iterations=iterations,
        ))
    except Exception as e:
        print(f"  FoulingEngine skipped: {e}")

    # 6. QualityScorer batch scoring
    try:
        from solar_platform.data_quality.quality_scorer import QualityScorer
        from solar_platform.db.repository import ReadingsRepository

        readings_repo = ReadingsRepository(engine=engine)
        df = readings_repo.get_readings(first_plant, start=start, end=end_7d)

        if not df.empty:
            # Rename columns to what QualityScorer expects
            scorer = QualityScorer()
            sample_df = df.head(200).copy()
            # Add mock fields for scorer
            sample_df["power_kw"] = sample_df.get("apparentPower_value", 0)
            sample_df["poa_wm2"] = sample_df.get("poaIrradiance_value", 0)
            sample_df["ambient_temp_c"] = sample_df.get("ambientTemperature_value", 0)
            sample_df["energy_kwh"] = 25.0
            sample_df["source"] = "emig"

            results.append(benchmark(
                f"QualityScorer.score_batch({len(sample_df)} rows)",
                lambda: scorer.score_batch(sample_df, {"capacity_kw": 5000}),
                iterations=iterations,
            ))
    except Exception as e:
        print(f"  QualityScorer skipped: {e}")

    # 7. Multi-plant sequential analysis
    plants_to_test = all_uids[:min(5, len(all_uids))]
    results.append(benchmark(
        f"Clipping × {len(plants_to_test)} plants (7d)",
        lambda: [clipping.run(uid, start, end_7d) for uid in plants_to_test],
        iterations=iterations,
    ))

    print(f"{'='*95}\n")
    return results


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analysis engine benchmarks")
    parser.add_argument("--plants", type=int, default=10, help="Number of plants to seed")
    parser.add_argument("--days", type=int, default=30, help="Days of readings per plant")
    parser.add_argument("--iterations", type=int, default=5, help="Benchmark iterations")
    parser.add_argument("--db", type=str, default=None, help="Path to existing bench DB")
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
