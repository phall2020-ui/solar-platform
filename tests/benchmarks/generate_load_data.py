"""Synthetic data generator for load testing and benchmarks."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd


def generate_plants(count: int = 20) -> pd.DataFrame:
    """Generate a DataFrame of synthetic plant records."""
    plants = []
    for i in range(count):
        plants.append({
            "plant_uid": f"bench-{i:04d}",
            "alias": f"Benchmark Plant {i}",
            "dc_size_kw": round(random.uniform(1000, 50000), 0),
            "ac_size_kw": round(random.uniform(900, 45000), 0),
            "latitude": round(random.uniform(48, 55), 4),
            "longitude": round(random.uniform(-5, 3), 4),
            "tilt": round(random.uniform(15, 40), 1),
            "azimuth": round(random.uniform(160, 200), 1),
            "timezone": "UTC",
        })
    return pd.DataFrame(plants)


def generate_readings(
    plant_uid: str,
    days: int = 30,
    interval_minutes: int = 15,
    start: datetime | None = None,
) -> pd.DataFrame:
    """Generate a DataFrame of synthetic time-series readings for one plant."""
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = []
    intervals_per_day = int(24 * 60 / interval_minutes)
    total_intervals = days * intervals_per_day

    for i in range(total_intervals):
        ts = start + timedelta(minutes=i * interval_minutes)
        hour = ts.hour
        # Simulated solar curve
        if 6 <= hour <= 18:
            sun_factor = max(0, 1.0 - abs(hour - 12) / 7.0)
            power = round(random.gauss(3000 * sun_factor, 200), 1)
            irr = round(max(0, random.gauss(800 * sun_factor, 50)), 1)
        else:
            power = 0.0
            irr = 0.0

        records.append({
            "timestamp": ts.replace(tzinfo=None),  # DuckDB prefers naive
            "plant_uid": plant_uid,
            "device_id": f"dev-{random.randint(1, 3)}",
            "apparentPower_value": max(0, power),
            "poaIrradiance_value": irr,
            "ambientTemperature_value": round(random.gauss(20, 5), 1),
            "moduleTemperature_value": round(random.gauss(35, 8), 1),
        })

    return pd.DataFrame(records)


def seed_benchmark_db(db_path: str, num_plants: int = 10, days: int = 30) -> str:
    """Create and seed a DuckDB database for benchmarking.

    Returns the database path.
    """
    conn = duckdb.connect(db_path)

    conn.execute("""
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
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            timestamp TIMESTAMP,
            plant_uid VARCHAR,
            device_id VARCHAR,
            apparentPower_value DOUBLE,
            poaIrradiance_value DOUBLE,
            ambientTemperature_value DOUBLE,
            moduleTemperature_value DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS solar_data (
            Site VARCHAR,
            Date VARCHAR,
            PR DOUBLE,
            Irradiance DOUBLE,
            Energy DOUBLE,
            Availability DOUBLE
        )
    """)

    # Seed plants
    plants_df = generate_plants(num_plants)
    conn.register("__plants_df", plants_df)
    conn.execute("INSERT INTO plants SELECT * FROM __plants_df")
    conn.unregister("__plants_df")

    # Seed readings for each plant
    for _, plant in plants_df.iterrows():
        readings_df = generate_readings(plant["plant_uid"], days=days)
        conn.register("__readings_df", readings_df)
        conn.execute("INSERT INTO readings SELECT * FROM __readings_df")
        conn.unregister("__readings_df")

    # Seed solar_data
    months = ["Jan-24", "Feb-24", "Mar-24", "Apr-24", "May-24", "Jun-24",
              "Jul-24", "Aug-24", "Sep-24", "Oct-24", "Nov-24", "Dec-24"]
    solar_records = []
    for _, plant in plants_df.iterrows():
        for month in months:
            solar_records.append({
                "Site": plant["alias"],
                "Date": month,
                "PR": round(random.uniform(0.75, 0.95), 3),
                "Irradiance": round(random.uniform(800, 1200), 1),
                "Energy": round(random.uniform(500, 5000), 1),
                "Availability": round(random.uniform(95, 100), 1),
            })
    solar_df = pd.DataFrame(solar_records)
    conn.register("__solar_df", solar_df)
    conn.execute("INSERT INTO solar_data SELECT * FROM __solar_df")
    conn.unregister("__solar_df")

    total_readings = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    total_plants = conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
    conn.close()

    print(f"Seeded bench DB: {total_plants} plants, {total_readings} readings, {len(solar_records)} solar_data rows")
    return db_path


if __name__ == "__main__":
    import sys
    import tempfile

    db_path = sys.argv[1] if len(sys.argv) > 1 else tempfile.mktemp(suffix=".duckdb")
    num_plants = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    seed_benchmark_db(db_path, num_plants=num_plants, days=days)
