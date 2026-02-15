#!/usr/bin/env python3
"""Run and monitor a full Juggle backfill in the background.

This script:
1) Discovers/registers plants
2) Pulls all available historical data with bounded parallelism
3) Prints heartbeat status every N seconds
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import duckdb

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "platform" / ".env")

from solar_platform.services.background_jobs import JobStatus, get_job_manager, submit_background_job
from solar_platform.services.data_pull import bg_pull_all_available_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full Juggle data backfill")
    parser.add_argument("--days-back", type=int, default=6000, help="Historical window in days")
    parser.add_argument("--workers", type=int, default=3, help="Parallel plant workers")
    parser.add_argument(
        "--report-every-plants",
        type=int,
        default=2,
        help="Emit progress update every N completed plants",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=60,
        help="How often to print monitor updates",
    )
    parser.add_argument(
        "--summary-minutes",
        type=float,
        default=15.0,
        help="How often to print pulled coverage summary (sites + months)",
    )
    return parser.parse_args()


def _print_pulled_coverage_summary() -> None:
    from solar_platform.config import get_settings

    db_path = str(get_settings().db_path)

    try:
        conn = duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] coverage_summary_unavailable db={db_path} error={exc}")
        return

    try:
        has_readings = conn.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema='main' AND table_name='readings'
        """).fetchone()[0]
        if not has_readings:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] coverage_summary readings_table_missing")
            return

        month_rows = conn.execute("""
            SELECT DISTINCT strftime(CAST(ts AS TIMESTAMP), '%Y-%m') AS month
            FROM readings
            ORDER BY month
        """).fetchall()
        months = [r[0] for r in month_rows if r and r[0]]

        site_rows = conn.execute("""
            WITH site_months AS (
                SELECT
                    COALESCE(NULLIF(p.alias, ''), r.plant_uid) AS site,
                    strftime(CAST(r.ts AS TIMESTAMP), '%Y-%m') AS month,
                    COUNT(*) AS intervals
                FROM readings r
                LEFT JOIN plants p ON p.plant_uid = r.plant_uid
                GROUP BY 1, 2
            )
            SELECT
                site,
                COUNT(*) AS month_count,
                MIN(month) AS first_month,
                MAX(month) AS last_month,
                SUM(intervals) AS total_intervals
            FROM site_months
            GROUP BY 1
            ORDER BY site
        """).fetchall()

        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        if not site_rows:
            print(f"[{ts}] coverage_summary no_rows_yet")
            return

        month_list = ", ".join(months) if months else "none"
        print(
            f"[{ts}] coverage_summary sites={len(site_rows)} months={len(months)} "
            f"range={(months[0] if months else 'n/a')}->{(months[-1] if months else 'n/a')}"
        )
        print(f"[{ts}] months_pulled: {month_list}")
        print(f"[{ts}] sites_pulled:")
        for site, month_count, first_month, last_month, total_intervals in site_rows:
            print(
                f"[{ts}]  - {site}: {month_count} months "
                f"({first_month}→{last_month}), intervals={int(total_intervals)}"
            )
    except Exception as exc:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] coverage_summary_failed error={exc}")
    finally:
        conn.close()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    manager = get_job_manager()
    job_id = submit_background_job(
        bg_pull_all_available_data,
        "Juggle Full Backfill",
        parallel_workers=max(1, args.workers),
        report_every_plants=max(1, args.report_every_plants),
        days_back=max(1, args.days_back),
    )

    print(
        f"Started background job {job_id} | days_back={args.days_back} "
        f"workers={max(1, args.workers)} report_every_plants={max(1, args.report_every_plants)} "
        f"summary_minutes={max(0.1, args.summary_minutes):g}"
    )

    summary_interval_s = max(0.1, args.summary_minutes) * 60.0
    last_summary_ts = 0.0

    while True:
        job = manager.get_job(job_id)
        if not job:
            print("Job disappeared from manager; exiting monitor")
            return 2

        status = job.status
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"status={status.value} progress={job.progress:.0%} msg={job.progress_message}"
        )

        now_ts = time.time()
        if now_ts - last_summary_ts >= summary_interval_s:
            _print_pulled_coverage_summary()
            last_summary_ts = now_ts

        if status == JobStatus.COMPLETED:
            print("Job completed")
            _print_pulled_coverage_summary()
            print(json.dumps(job.result or {}, indent=2, default=str))
            return 0

        if status == JobStatus.FAILED:
            print(f"Job failed: {job.error}")
            return 1

        if status == JobStatus.CANCELLED:
            print("Job cancelled")
            return 3

        time.sleep(max(10, args.heartbeat_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
