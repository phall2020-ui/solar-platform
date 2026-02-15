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

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

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
    return parser.parse_args()


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
        f"workers={max(1, args.workers)} report_every_plants={max(1, args.report_every_plants)}"
    )

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

        if status == JobStatus.COMPLETED:
            print("Job completed")
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
