"""
Juggle/EMIG data pull service.

Uses the EMIG REST API (https://www.emig.co.uk/p/api) to discover plants, 
fetch inverter/weather readings, and store them in the platform's DuckDB
database. Designed to run as a background job with rate limiting and progress 
tracking.

Plant names and DC capacities are sourced from the Notion asset register
(irradiance DB) which is the single source of truth. API-provided names
are used only as a fallback when no Notion match is found.

Rate limiting:
  - 60 requests/minute sliding window (EMIG API limit)
  - 1.2 s minimum gap between consecutive requests
  - Automatic retry with exponential backoff on transient errors
  - Date-range chunking (≤90 days per request) to avoid 413 responses

Usage:
    from solar_platform.services.data_pull import JuggleDataPullService

    svc = JuggleDataPullService()
    # Discover & register plants (cross-referenced with Notion)
    svc.discover_and_register_plants()
    # Pull last 7 days for all plants (background-safe)
    result = svc.pull_all_plants(days_back=7, job_id="optional-for-progress")
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx
import requests

from solar_platform.config import get_settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

BASE_URL = "https://www.emig.co.uk/p/api"
MAX_DAYS_PER_CHUNK = 90          # Stay under EMIG payload limit
MAX_READINGS_PER_REQUEST = 5_000  # API hard cap
DEFAULT_MIN_INTERVAL_S = 1800    # Half-hourly
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRIES = 3
RATE_LIMIT_RPM = 60
MIN_REQUEST_GAP_S = 1.2         # Minimum gap between API calls


# ═══════════════════════════════════════════════════════════════════════
# Rate limiter
# ═══════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Sliding-window rate limiter with minimum gap enforcement."""

    def __init__(self, max_rpm: int = RATE_LIMIT_RPM, min_gap_s: float = MIN_REQUEST_GAP_S):
        self._max_rpm = max_rpm
        self._min_gap_s = min_gap_s
        self._calls: list[float] = []
        self._last_call: float = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next request is allowed."""
        with self._lock:
            now = time.monotonic()

            elapsed = now - self._last_call
            if elapsed < self._min_gap_s:
                gap_wait = self._min_gap_s - elapsed
                logger.debug("Rate limit: waiting %.2fs (min gap)", gap_wait)
                time.sleep(gap_wait)
                now = time.monotonic()

            window_start = now - 60.0
            self._calls = [t for t in self._calls if t > window_start]
            if len(self._calls) >= self._max_rpm:
                wait_until = self._calls[0] + 60.0
                sleep_s = wait_until - now
                if sleep_s > 0:
                    logger.info("Rate limit: waiting %.1fs (RPM cap %d)", sleep_s, self._max_rpm)
                    time.sleep(sleep_s)
                now = time.monotonic()
                self._calls = [t for t in self._calls if t > now - 60.0]

            self._calls.append(now)
            self._last_call = now


# ═══════════════════════════════════════════════════════════════════════
# Notion asset register lookup (source of truth for names & capacities)
# ═══════════════════════════════════════════════════════════════════════

# Known name mismatches between the Juggle/EMIG API and the Notion asset
# register.  Keys are *normalised* API names, values are the canonical
# Notion site names.  Extend this dict when new mismatches are discovered.
_API_TO_NOTION_NAME: dict[str, str] = {
    "man city fc training ground": "City Football Group Phase 1",
    "sheldons bakery": "Hazelwick School",
    "merry hill shopping centre": "Merry Hill",
    "metrocentre": "Metro Centre",
    "blachford uk": "Blachford",
    "sofina foods": "Sofina Haverhill",
    "smithys mushrooms ph1": "Smithys Mushrooms",
    "smithys mushrooms": "Smithys Mushrooms",
    "smithys mushrooms ph2": "Smithys Mushrooms Phase 2",
    "smithys mushrooms ph1 2": "Smithys Mushrooms",    # PH1+2 combined meter
    "parfetts birmingham": "Parfetts - Birmingham",
    "newfold farm": "BAE Fylde",
    "faltec europe ltd": "Faltec Europe Ltd",
    "smeed dean works": "Wienerberger - Smeed",
}

_NOTION_API_VERSION = "2022-06-28"

def _norm(s: str) -> str:
    """Normalise a string for fuzzy comparison.
    
    Strips apostrophes before collapsing non-alphanum so that
    "Smithy's" matches "Smithys".
    """
    s = s.lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class NotionSiteLookup:
    """Queries the Notion irradiance DB (asset register) for canonical
    site names and DC capacities (kWp).

    Results are cached for the lifetime of the object.
    """

    def __init__(self, token: str | None = None, database_id: str | None = None):
        settings = get_settings()
        self._token = (
            token
            or str(getattr(settings, "notion_integration_token", "")).strip()
        )
        self._db_id = (
            database_id
            or str(getattr(settings, "notion_asset_database_id", "")).strip()
        )
        self._sites: dict[str, float] | None = None  # {canonical_name: kWp}

    @property
    def available(self) -> bool:
        return bool(self._token and self._db_id)

    def fetch_sites(self) -> dict[str, float]:
        """Return {canonical_site_name: kWp} from Notion, cached."""
        if self._sites is not None:
            return dict(self._sites)

        if not self.available:
            logger.warning("Notion integration not configured; skipping asset register lookup")
            self._sites = {}
            return {}

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": _NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        url = f"https://api.notion.com/v1/databases/{self._db_id}/query"

        sites: dict[str, float] = {}
        cursor: str | None = None

        try:
            while True:
                payload: dict[str, Any] = {"page_size": 100}
                if cursor:
                    payload["start_cursor"] = cursor

                resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                body = resp.json()

                for page in body.get("results", []):
                    props = page.get("properties", {})
                    # Extract Site (title field)
                    site_prop = props.get("Site", {})
                    site_name = ""
                    if site_prop.get("type") == "title":
                        parts = site_prop.get("title", [])
                        site_name = "".join(
                            p.get("plain_text", "") for p in parts if isinstance(p, dict)
                        ).strip()
                    # Extract kWp (number field)
                    kwp_prop = props.get("kWp", {})
                    kwp = kwp_prop.get("number") if kwp_prop.get("type") == "number" else None

                    if site_name and kwp is not None:
                        # Keep the *largest* kWp seen for this site (handles
                        # capacity upgrades over time)
                        if site_name not in sites or kwp > sites[site_name]:
                            sites[site_name] = kwp

                if not body.get("has_more"):
                    break
                cursor = body.get("next_cursor")
                if not cursor:
                    break

            logger.info("Notion asset register: loaded %d sites", len(sites))
        except Exception as exc:
            logger.warning("Failed to load Notion asset register: %s", exc)

        self._sites = sites
        return dict(sites)

    def match(self, api_name: str) -> tuple[str, float | None]:
        """Match an API plant name to a Notion site.

        Returns (canonical_name, kWp) where canonical_name comes from
        Notion when a match is found, or the original *api_name* as a
        fallback.  kWp is ``None`` when no Notion match exists.
        """
        sites = self.fetch_sites()
        norm_api = _norm(api_name)

        # 1. Explicit override table
        if norm_api in _API_TO_NOTION_NAME:
            notion_name = _API_TO_NOTION_NAME[norm_api]
            kwp = sites.get(notion_name)
            if kwp is not None:
                return notion_name, kwp
            # Override exists but Notion doesn't have the site – still use
            # the canonical name from the override.
            return notion_name, None

        # 2. Exact match (case-insensitive)
        for sname, skwp in sites.items():
            if _norm(sname) == norm_api:
                return sname, skwp

        # 3. Substring / token overlap
        api_tokens = set(norm_api.split())
        best_score = 0.0
        best_name: str | None = None
        best_kwp: float | None = None
        for sname, skwp in sites.items():
            s_tokens = set(_norm(sname).split())
            if not s_tokens:
                continue
            overlap = len(api_tokens & s_tokens)
            score = overlap / max(len(api_tokens), len(s_tokens))
            if score > best_score and score >= 0.5:
                best_score = score
                best_name = sname
                best_kwp = skwp

        if best_name:
            logger.info("Fuzzy-matched API '%s' → Notion '%s' (score=%.2f)",
                        api_name, best_name, best_score)
            return best_name, best_kwp

        # 4. No match – fall back to API name
        logger.warning("No Notion match for API plant '%s'", api_name)
        return api_name, None


# ═══════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PullResult:
    """Result of a data pull operation."""
    plant_uid: str
    alias: str
    devices_fetched: int = 0
    readings_fetched: int = 0
    readings_stored: int = 0
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 or self.readings_stored > 0


@dataclass
class PullSummary:
    """Summary of a multi-plant data pull."""
    plants_attempted: int = 0
    plants_succeeded: int = 0
    plants_failed: int = 0
    total_readings: int = 0
    total_stored: int = 0
    errors: list[str] = field(default_factory=list)
    plant_results: list[PullResult] = field(default_factory=list)
    duration_s: float = 0.0
    started_at: str = ""
    completed_at: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════

class JuggleDataPullService:
    """
    Service to pull data from the Juggle/EMIG API into the platform DuckDB.

    Handles plant discovery, device enumeration, readings fetch with rate
    limiting, and DuckDB upserts. Safe for background execution.
    """

    def __init__(
        self,
        api_key: str | None = None,
        db_path: str | None = None,
        min_interval_s: int = DEFAULT_MIN_INTERVAL_S,
        rate_limiter: RateLimiter | None = None,
        db_write_lock: threading.Lock | None = None,
    ):
        settings = get_settings()
        self.api_key = (
            api_key
            or settings.effective_api_key
            or os.environ.get("JUGGLE_API_KEY", "")
            or os.environ.get("EMIG_API_KEY", "")
        )
        self.db_path = db_path or str(settings.db_path)
        self.min_interval_s = min_interval_s
        self._rate_limiter = rate_limiter or RateLimiter()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"token {self.api_key}",
            "Accept": "application/json",
        })
        # Notion asset register lookup (source of truth for names/capacities)
        self._notion = NotionSiteLookup()
        self._db_write_lock = db_write_lock or threading.Lock()
        # Progress callback (set by background job wrapper)
        self._progress_callback: Any = None

    def _create_worker_service(self) -> "JuggleDataPullService":
        worker = JuggleDataPullService(
            api_key=self.api_key,
            db_path=self.db_path,
            min_interval_s=self.min_interval_s,
            rate_limiter=self._rate_limiter,
            db_write_lock=self._db_write_lock,
        )
        worker._progress_callback = self._progress_callback
        return worker

    # ── API helpers ───────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None, timeout: float = DEFAULT_TIMEOUT_S) -> Any:
        """Make a rate-limited GET request with retries."""
        url = f"{BASE_URL}{path}"
        last_error: Exception | None = None

        for attempt in range(DEFAULT_RETRIES):
            self._rate_limiter.wait()
            try:
                resp = self._session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    # Rate limited — back off harder
                    wait = 10 * (attempt + 1)
                    logger.warning("429 rate limited, backing off %ds", wait)
                    time.sleep(wait)
                    last_error = exc
                    continue
                raise
            except requests.exceptions.RequestException as exc:
                last_error = exc
                backoff = 2 ** attempt * 1.5
                logger.warning("Request error (attempt %d/%d): %s, retrying in %.1fs",
                               attempt + 1, DEFAULT_RETRIES, exc, backoff)
                time.sleep(backoff)

        if last_error:
            raise last_error
        return None

    # ── Plant discovery ───────────────────────────────────────────────

    def discover_plants(self) -> list[dict[str, Any]]:
        """
        Discover all plants accessible via the API key, then cross-reference
        the Notion asset register to apply canonical names and DC capacities.

        Returns list of dicts with ``uid``, ``name`` (Notion canonical),
        ``api_name`` (original API name), ``inverter_count``,
        ``inverter_ids``, ``weather_id``, ``dc_size_kw``.
        """
        if not self.api_key:
            raise ValueError("No API key configured. Set JUGGLE_API_KEY or EMIG_API_KEY.")

        plants: list[dict[str, Any]] = []

        # Try the plant-list endpoint first (EMIG style)
        for endpoint in ["/plant-list", "/plants", "/plants/list"]:
            try:
                data = self._get(endpoint)
                if isinstance(data, dict) and "plants" in data:
                    data = data["plants"]
                if isinstance(data, list) and data:
                    for p in data:
                        uid = p.get("uid") or p.get("id") or p.get("plantUID")
                        name = p.get("name") or p.get("plantName") or uid
                        if uid:
                            plants.append({"uid": uid, "api_name": name, "name": name})
                    break
            except Exception:
                continue

        if not plants:
            logger.warning("Could not discover plants via list endpoints")
            return []

        # Enrich each plant with device information
        for plant in plants:
            try:
                details = self._get(f"/plant/{plant['uid']}")
                meters = details.get("meters", []) if isinstance(details, dict) else []
                inverter_ids = [
                    m["emigId"] for m in meters
                    if m.get("type") == "INVERTER" and "emigId" in m
                ]
                weather_ids = [
                    m["emigId"] for m in meters
                    if m.get("type") in ("WEATHER", "WEATHER_STATION") and "emigId" in m
                ]
                plant["inverter_ids"] = inverter_ids
                plant["inverter_count"] = len(inverter_ids)
                plant["weather_id"] = weather_ids[0] if weather_ids else None
                # API-provided capacity (fallback only)
                plant["api_dc_size_kw"] = details.get("dcCapacity") or details.get("capacity")
            except Exception as exc:
                logger.warning("Failed to get details for %s: %s", plant["uid"], exc)
                plant["inverter_ids"] = []
                plant["inverter_count"] = 0
                plant["weather_id"] = None
                plant["api_dc_size_kw"] = None

        # ── Cross-reference Notion asset register (SOURCE OF TRUTH) ──
        notion_sites = self._notion.fetch_sites()
        if notion_sites:
            logger.info("Cross-referencing %d API plants against %d Notion sites",
                        len(plants), len(notion_sites))

        for plant in plants:
            canonical_name, kwp = self._notion.match(plant["api_name"])
            plant["name"] = canonical_name          # Notion name (or API fallback)
            plant["dc_size_kw"] = kwp               # Notion kWp (source of truth)
            if kwp is None:
                # Fall back to API capacity if Notion doesn't have it
                plant["dc_size_kw"] = plant.get("api_dc_size_kw")

            if canonical_name != plant["api_name"]:
                logger.info("Name override: API '%s' → Notion '%s'",
                            plant["api_name"], canonical_name)

        logger.info("Discovered %d plants (%d matched to Notion)",
                    len(plants),
                    sum(1 for p in plants if p["name"] != p["api_name"] or p.get("dc_size_kw")))
        return plants

    def register_plants_in_db(self, plants: list[dict[str, Any]]) -> int:
        """
        Register discovered plants in the DuckDB plants table.

        Uses the Notion canonical name as ``alias`` and Notion kWp as
        ``dc_size_kw``.  The original API name is stored in the
        ``api_name`` column for traceability.

        Upserts by plant_uid so re-running is safe.
        Returns number of plants registered.
        """
        if not plants:
            return 0

        registered = 0
        with duckdb.connect(self.db_path, read_only=False) as conn:
            # Ensure proper schema
            self._ensure_schema(conn)

            for p in plants:
                try:
                    # Check if plant already exists
                    existing = conn.execute(
                        "SELECT COUNT(*) FROM plants WHERE plant_uid = ?",
                        [p["uid"]],
                    ).fetchone()[0]

                    inverter_ids_json = json.dumps(p.get("inverter_ids", []))

                    if existing:
                        conn.execute(
                            """UPDATE plants SET
                                alias = ?,
                                inverter_ids = ?,
                                weather_id = COALESCE(?, weather_id),
                                dc_size_kw = COALESCE(?, dc_size_kw),
                                api_name = ?
                            WHERE plant_uid = ?""",
                            [
                                p["name"],           # Notion canonical name
                                inverter_ids_json,
                                p.get("weather_id"),
                                p.get("dc_size_kw"),
                                p.get("api_name", p["name"]),
                                p["uid"],
                            ],
                        )
                    else:
                        conn.execute(
                            """INSERT INTO plants (alias, plant_uid, inverter_ids, weather_id, dc_size_kw, api_name)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                            [
                                p["name"],           # Notion canonical name
                                p["uid"],
                                inverter_ids_json,
                                p.get("weather_id"),
                                p.get("dc_size_kw"),
                                p.get("api_name", p["name"]),
                            ],
                        )
                    registered += 1
                except Exception as exc:
                    logger.warning("Failed to register plant %s: %s", p.get("uid"), exc)

        logger.info("Registered %d/%d plants in DB", registered, len(plants))
        return registered

    def discover_and_register_plants(self) -> list[dict[str, Any]]:
        """Discover plants from API and register them in the DB. Returns the plant list."""
        plants = self.discover_plants()
        if plants:
            self.register_plants_in_db(plants)
        return plants

    # ── DB helpers ────────────────────────────────────────────────────

    @staticmethod
    def _ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
        """Ensure the DuckDB schema supports our data.
        
        Detects old INTEGER-typed placeholder schemas and recreates
        them with proper VARCHAR/DOUBLE types.
        """
        tables = [
            r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        ]

        if "plants" in tables:
            # Check for wrong column types (old placeholder schema used INTEGER)
            col_types = {
                r[0]: r[1] for r in conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'plants'"
                ).fetchall()
            }
            if col_types.get("alias") in ("INTEGER", "INT32", "INT"):
                logger.warning("Dropping old plants table with INTEGER types — will recreate")
                conn.execute("DROP TABLE plants")
                tables = [t for t in tables if t != "plants"]

        if "readings" in tables:
            col_types = {
                r[0]: r[1] for r in conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'readings'"
                ).fetchall()
            }
            if col_types.get("plant_uid") in ("INTEGER", "INT32", "INT"):
                logger.warning("Dropping old readings table with INTEGER types — will recreate")
                conn.execute("DROP TABLE readings")
                tables = [t for t in tables if t != "readings"]

        if "plants" not in tables:
            conn.execute("""
                CREATE TABLE plants (
                    alias VARCHAR,
                    plant_uid VARCHAR PRIMARY KEY,
                    inverter_ids VARCHAR,
                    weather_id VARCHAR,
                    dc_size_kw DOUBLE,
                    api_name VARCHAR
                )
            """)
        else:
            # Ensure api_name column exists (migration for existing DBs)
            cols = {
                r[0] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'plants'"
                ).fetchall()
            }
            if "api_name" not in cols:
                conn.execute("ALTER TABLE plants ADD COLUMN api_name VARCHAR")

        if "readings" not in tables:
            conn.execute("""
                CREATE TABLE readings (
                    plant_uid VARCHAR NOT NULL,
                    emig_id VARCHAR NOT NULL,
                    ts VARCHAR NOT NULL,
                    payload VARCHAR NOT NULL
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_pk
                ON readings (plant_uid, emig_id, ts)
            """)
        else:
            # Ensure the unique index exists for upserts
            try:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_pk
                    ON readings (plant_uid, emig_id, ts)
                """)
            except Exception:
                pass  # Index may already exist

    def get_registered_plants(self) -> list[dict[str, Any]]:
        """Get all plants registered in the DB."""
        try:
            with duckdb.connect(self.db_path, read_only=True) as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    "SELECT alias, plant_uid, inverter_ids, weather_id, dc_size_kw, api_name FROM plants ORDER BY alias"
                ).fetchall()
                plants = []
                for r in rows:
                    inv_ids = []
                    if r[2]:
                        try:
                            inv_ids = json.loads(r[2])
                        except (json.JSONDecodeError, TypeError):
                            inv_ids = [s.strip() for s in str(r[2]).split(",") if s.strip()]
                    plants.append({
                        "alias": r[0],
                        "plant_uid": r[1],
                        "inverter_ids": inv_ids,
                        "weather_id": r[3],
                        "dc_size_kw": r[4],
                        "api_name": r[5],
                    })
                return plants
        except Exception as exc:
            logger.warning("Failed to get registered plants: %s", exc)
            return []

    def get_data_status(self) -> dict[str, Any]:
        """Get overview of data currently in the DB."""
        try:
            with duckdb.connect(self.db_path, read_only=True) as conn:
                self._ensure_schema(conn)
                plant_count = conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
                reading_count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

                # Per-plant latest reading
                plant_status = []
                plants = conn.execute("SELECT alias, plant_uid FROM plants ORDER BY alias").fetchall()
                for alias, uid in plants:
                    row = conn.execute(
                        "SELECT COUNT(*), MIN(ts), MAX(ts) FROM readings WHERE plant_uid = ?",
                        [uid],
                    ).fetchone()
                    plant_status.append({
                        "alias": alias,
                        "plant_uid": uid,
                        "reading_count": row[0],
                        "earliest": row[1],
                        "latest": row[2],
                    })

                return {
                    "plant_count": plant_count,
                    "total_readings": reading_count,
                    "plants": plant_status,
                }
        except Exception as exc:
            return {"error": str(exc), "plant_count": 0, "total_readings": 0, "plants": []}

    # ── Readings fetch ────────────────────────────────────────────────

    def _fetch_device_readings(
        self,
        plant_uid: str,
        emig_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """
        Fetch readings for one device across a date range, chunked to avoid limits.

        Args:
            plant_uid: Plant UID (for logging).
            emig_id: Device EMIG ID.
            start_date: YYYYMMDD start (inclusive).
            end_date: YYYYMMDD end (inclusive).

        Returns:
            List of raw reading dicts from the API.
        """
        all_readings: list[dict] = []
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")

        chunk_start = start_dt
        while chunk_start <= end_dt:
            chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_CHUNK - 1), end_dt)

            try:
                data = self._get(
                    f"/meter/{emig_id}/readings",
                    params={
                        "startDate": chunk_start.strftime("%Y%m%d"),
                        "endDate": chunk_end.strftime("%Y%m%d"),
                        "minIntervalS": str(self.min_interval_s),
                    },
                )
                readings = data.get("readings", []) if isinstance(data, dict) else []
                for r in readings:
                    r["emigId"] = emig_id
                all_readings.extend(readings)

                logger.debug(
                    "Fetched %d readings for %s (%s to %s)",
                    len(readings), emig_id,
                    chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"),
                )
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                logger.warning(
                    "HTTP %s fetching %s (%s–%s)",
                    status, emig_id,
                    chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"),
                )
            except Exception as exc:
                logger.warning("Error fetching %s: %s", emig_id, exc)

            chunk_start = chunk_end + timedelta(days=1)

        return all_readings

    def _store_readings(self, plant_uid: str, readings: list[dict]) -> int:
        """
        Store readings in DuckDB using INSERT OR REPLACE semantics.

        Returns number of readings stored.
        """
        if not readings:
            return 0

        with self._db_write_lock:
            with duckdb.connect(self.db_path, read_only=False) as conn:
                self._ensure_schema(conn)

                stored = 0
                batch_size = 500

                for i in range(0, len(readings), batch_size):
                    batch = readings[i : i + batch_size]
                    rows = []
                    for r in batch:
                        ts = r.get("ts") or r.get("timestamp")
                        emig_id = r.get("emigId", "")
                        if not ts or not emig_id:
                            continue
                        payload = json.dumps(r)
                        rows.append((plant_uid, emig_id, str(ts), payload))

                    if rows:
                        try:
                            conn.executemany(
                                """INSERT INTO readings (plant_uid, emig_id, ts, payload)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT (plant_uid, emig_id, ts) DO UPDATE SET
                                    payload = EXCLUDED.payload""",
                                rows,
                            )
                            stored += len(rows)
                        except Exception as exc:
                            logger.warning("Batch insert failed (%s), falling back to row-by-row", exc)
                            for row in rows:
                                try:
                                    conn.execute(
                                        """INSERT INTO readings (plant_uid, emig_id, ts, payload)
                                        VALUES (?, ?, ?, ?)
                                        ON CONFLICT (plant_uid, emig_id, ts) DO UPDATE SET
                                            payload = EXCLUDED.payload""",
                                        row,
                                    )
                                    stored += 1
                                except Exception:
                                    pass

        return stored

    # ── Single plant pull ─────────────────────────────────────────────

    def pull_plant(
        self,
        plant_uid: str,
        alias: str,
        inverter_ids: list[str],
        weather_id: str | None,
        start_date: str,
        end_date: str,
        job_id: str | None = None,
    ) -> PullResult:
        """
        Pull all data for one plant over the given date range.

        Args:
            plant_uid: Plant UID.
            alias: Human-friendly name (for logging).
            inverter_ids: List of EMIG IDs for inverters.
            weather_id: Optional weather device EMIG ID.
            start_date: YYYYMMDD start.
            end_date: YYYYMMDD end.
            job_id: Optional job ID for progress updates.
        """
        t0 = time.monotonic()
        result = PullResult(plant_uid=plant_uid, alias=alias)

        # Collect all device IDs to fetch
        device_ids = list(inverter_ids)
        if weather_id:
            device_ids.append(weather_id)

        if not device_ids:
            # Try to discover devices from the API
            try:
                details = self._get(f"/plant/{plant_uid}")
                meters = details.get("meters", []) if isinstance(details, dict) else []
                device_ids = [m["emigId"] for m in meters if "emigId" in m]
                if not device_ids:
                    result.errors.append(f"No devices found for {alias}")
                    return result
            except Exception as exc:
                result.errors.append(f"Failed to discover devices for {alias}: {exc}")
                return result

        all_readings: list[dict] = []

        for idx, device_id in enumerate(device_ids):
            logger.info("Fetching %s device %d/%d: %s (%s–%s)",
                        alias, idx + 1, len(device_ids), device_id, start_date, end_date)

            try:
                readings = self._fetch_device_readings(plant_uid, device_id, start_date, end_date)
                all_readings.extend(readings)
                result.devices_fetched += 1
                logger.info("  → %d readings from %s", len(readings), device_id)
            except Exception as exc:
                result.errors.append(f"Device {device_id}: {exc}")
                logger.error("Error fetching %s/%s: %s", alias, device_id, exc)

            # Update progress
            if job_id and self._progress_callback:
                device_progress = (idx + 1) / len(device_ids)
                self._progress_callback(
                    job_id,
                    device_progress * 0.8,  # 80% for fetching, 20% for storing
                    f"Fetching {alias}: {idx + 1}/{len(device_ids)} devices",
                )

        result.readings_fetched = len(all_readings)

        # Store readings
        if all_readings:
            if job_id and self._progress_callback:
                self._progress_callback(job_id, 0.85, f"Storing {len(all_readings):,} readings for {alias}...")
            result.readings_stored = self._store_readings(plant_uid, all_readings)
            logger.info("Stored %d/%d readings for %s", result.readings_stored, len(all_readings), alias)

        result.duration_s = round(time.monotonic() - t0, 1)
        return result

    # ── Multi-plant pull ──────────────────────────────────────────────

    def pull_all_plants(
        self,
        days_back: int = 7,
        job_id: str | None = None,
        plant_uids: list[str] | None = None,
        parallel_workers: int = 1,
        report_every_plants: int = 1,
    ) -> PullSummary:
        """
        Pull data for all registered plants (or a subset).

        Args:
            days_back: Number of days to look back from today.
            job_id: Background job ID for progress tracking.
            plant_uids: Optional subset of plant UIDs to pull. None = all.
            parallel_workers: Number of plants to process concurrently.
            report_every_plants: Emit progress update every N completed plants.

        Returns:
            PullSummary with per-plant results.
        """
        t0 = time.monotonic()
        summary = PullSummary(started_at=datetime.now().isoformat())

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

        # Get plants
        plants = self.get_registered_plants()
        if plant_uids:
            plants = [p for p in plants if p["plant_uid"] in plant_uids]

        if not plants:
            summary.errors.append("No plants registered. Run 'Discover Plants' first.")
            return summary

        summary.plants_attempted = len(plants)
        workers = max(1, int(parallel_workers))

        def _run_single(plant: dict[str, Any]) -> PullResult:
            worker_svc = self if workers == 1 else self._create_worker_service()
            return worker_svc.pull_plant(
                plant_uid=plant["plant_uid"],
                alias=plant["alias"],
                inverter_ids=plant.get("inverter_ids", []),
                weather_id=plant.get("weather_id"),
                start_date=start_date,
                end_date=end_date,
                job_id=None,
            )

        completed = 0
        if workers == 1:
            for idx, plant in enumerate(plants):
                alias = plant["alias"]
                logger.info("=== Pulling %s (%d/%d) ===", alias, idx + 1, len(plants))
                try:
                    result = _run_single(plant)
                except Exception as exc:
                    result = PullResult(plant_uid=plant["plant_uid"], alias=alias, errors=[str(exc)])
                completed += 1
                summary.plant_results.append(result)
                summary.total_readings += result.readings_fetched
                summary.total_stored += result.readings_stored
                if result.success:
                    summary.plants_succeeded += 1
                else:
                    summary.plants_failed += 1
                    summary.errors.extend(result.errors)
                if job_id and self._progress_callback and completed % max(1, report_every_plants) == 0:
                    self._progress_callback(
                        job_id,
                        completed / len(plants),
                        f"Completed {completed}/{len(plants)} plants",
                    )
        else:
            logger.info("Starting parallel plant pull with %d workers", workers)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="juggle-pull") as pool:
                future_to_plant = {pool.submit(_run_single, plant): plant for plant in plants}
                for future in as_completed(future_to_plant):
                    plant = future_to_plant[future]
                    alias = plant["alias"]
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error("Failed to pull %s: %s", alias, exc)
                        result = PullResult(plant_uid=plant["plant_uid"], alias=alias, errors=[str(exc)])

                    completed += 1
                    summary.plant_results.append(result)
                    summary.total_readings += result.readings_fetched
                    summary.total_stored += result.readings_stored
                    if result.success:
                        summary.plants_succeeded += 1
                    else:
                        summary.plants_failed += 1
                        summary.errors.extend(result.errors)

                    if completed % max(1, report_every_plants) == 0:
                        logger.info(
                            "Progress: %d/%d plants complete, %d readings stored",
                            completed,
                            len(plants),
                            summary.total_stored,
                        )

                    if job_id and self._progress_callback and completed % max(1, report_every_plants) == 0:
                        self._progress_callback(
                            job_id,
                            completed / len(plants),
                            f"Completed {completed}/{len(plants)} plants",
                        )

        if job_id and self._progress_callback:
            self._progress_callback(job_id, 1.0, "Complete")

        summary.duration_s = round(time.monotonic() - t0, 1)
        summary.completed_at = datetime.now().isoformat()

        logger.info(
            "Pull complete: %d/%d plants, %d readings stored in %.1fs",
            summary.plants_succeeded, summary.plants_attempted,
            summary.total_stored, summary.duration_s,
        )

        return summary


# ═══════════════════════════════════════════════════════════════════════
# Background job wrappers
# ═══════════════════════════════════════════════════════════════════════

def _create_service() -> JuggleDataPullService:
    """Create a JuggleDataPullService with background-job progress support."""
    from solar_platform.services.background_jobs import get_job_manager

    svc = JuggleDataPullService()
    manager = get_job_manager()
    svc._progress_callback = manager.update_progress
    return svc


def bg_discover_plants(job_id: str | None = None) -> dict:
    """Background job: discover and register plants."""
    svc = _create_service()
    if job_id and svc._progress_callback:
        svc._progress_callback(job_id, 0.1, "Connecting to Juggle API...")

    plants = svc.discover_and_register_plants()

    if job_id and svc._progress_callback:
        svc._progress_callback(job_id, 1.0, f"Found {len(plants)} plants")

    return {
        "plants_found": len(plants),
        "plants": [
            {
                "uid": p["uid"],
                "name": p["name"],
                "api_name": p.get("api_name", p["name"]),
                "dc_size_kw": p.get("dc_size_kw"),
                "inverters": p.get("inverter_count", 0),
            }
            for p in plants
        ],
    }


def bg_pull_all_plants(
    days_back: int = 7,
    job_id: str | None = None,
    parallel_workers: int = 1,
    report_every_plants: int = 1,
) -> dict:
    """Background job: pull data for all registered plants."""
    svc = _create_service()
    summary = svc.pull_all_plants(
        days_back=days_back,
        job_id=job_id,
        parallel_workers=parallel_workers,
        report_every_plants=report_every_plants,
    )
    return {
        "plants_attempted": summary.plants_attempted,
        "plants_succeeded": summary.plants_succeeded,
        "plants_failed": summary.plants_failed,
        "total_readings": summary.total_readings,
        "total_stored": summary.total_stored,
        "duration_s": summary.duration_s,
        "errors": summary.errors[:10],  # Cap errors for display
        "plant_results": [
            {
                "alias": r.alias,
                "readings_fetched": r.readings_fetched,
                "readings_stored": r.readings_stored,
                "devices": r.devices_fetched,
                "errors": r.errors[:3],
            }
            for r in summary.plant_results
        ],
    }


def bg_pull_all_available_data(
    job_id: str | None = None,
    parallel_workers: int = 3,
    report_every_plants: int = 2,
    days_back: int = 6000,
) -> dict:
    """Background job: discover plants then backfill all available data."""
    svc = _create_service()
    if job_id and svc._progress_callback:
        svc._progress_callback(job_id, 0.02, "Discovering and registering plants")
    plants = svc.discover_and_register_plants()
    if not plants:
        return {
            "plants_found": 0,
            "plants_attempted": 0,
            "plants_succeeded": 0,
            "plants_failed": 0,
            "total_readings": 0,
            "total_stored": 0,
            "duration_s": 0,
            "errors": ["No plants discovered"],
            "plant_results": [],
        }
    summary = svc.pull_all_plants(
        days_back=days_back,
        job_id=job_id,
        parallel_workers=parallel_workers,
        report_every_plants=report_every_plants,
    )
    return {
        "plants_found": len(plants),
        "plants_attempted": summary.plants_attempted,
        "plants_succeeded": summary.plants_succeeded,
        "plants_failed": summary.plants_failed,
        "total_readings": summary.total_readings,
        "total_stored": summary.total_stored,
        "duration_s": summary.duration_s,
        "errors": summary.errors[:10],
        "plant_results": [
            {
                "alias": r.alias,
                "readings_fetched": r.readings_fetched,
                "readings_stored": r.readings_stored,
                "devices": r.devices_fetched,
                "errors": r.errors[:3],
            }
            for r in summary.plant_results
        ],
    }


def bg_pull_single_plant(plant_uid: str, days_back: int = 7, job_id: str | None = None) -> dict:
    """Background job: pull data for a single plant."""
    svc = _create_service()
    plants = svc.get_registered_plants()
    plant = next((p for p in plants if p["plant_uid"] == plant_uid), None)

    if not plant:
        return {"error": f"Plant {plant_uid} not found in registry"}

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

    result = svc.pull_plant(
        plant_uid=plant["plant_uid"],
        alias=plant["alias"],
        inverter_ids=plant.get("inverter_ids", []),
        weather_id=plant.get("weather_id"),
        start_date=start_date,
        end_date=end_date,
        job_id=job_id,
    )

    return {
        "alias": result.alias,
        "readings_fetched": result.readings_fetched,
        "readings_stored": result.readings_stored,
        "devices": result.devices_fetched,
        "duration_s": result.duration_s,
        "errors": result.errors,
    }
