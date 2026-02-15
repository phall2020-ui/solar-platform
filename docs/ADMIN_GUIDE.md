# Administration & Operations Guide

> **AMPYR Solar Portfolio Manager v1.1.0** | Last updated: February 2026

This guide is for system administrators responsible for deploying, configuring, and maintaining the Solar Portfolio Manager.

---

## Table of Contents

1. [Deployment](#deployment)
2. [User Management](#user-management)
3. [Database](#database)
4. [Data Sources](#data-sources)
5. [Monitoring](#monitoring)
6. [Maintenance](#maintenance)
7. [Disaster Recovery](#disaster-recovery)
8. [Security](#security)

---

## Deployment

### Prerequisites

- **Python 3.11+** (for local development)
- **Docker** and **Docker Compose** (for containerised deployment)
- **DuckDB** (embedded — no separate installation required)
- **Redis 7+** (for caching — included in Docker Compose)

### Local Development

```bash
# Clone and enter the project
cd solar-platform

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e .[all]

# Start the development server with hot-reload
streamlit run app/main.py --server.port=8501 --server.runOnSave=true
```

This runs `streamlit run app/main.py --server.port=8501 --server.runOnSave=true`.

### Docker Compose (Production)

The project ships with two Compose files:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Production deployment with Redis |
| `docker-compose.dev.yml` | Development overlay with hot-reload and debug logging |

**Production deployment:**

```bash
# Build and start
make docker-build
make docker-up

# Or directly
docker compose up -d
```

**Development deployment:**

```bash
make docker-up-dev
# Equivalent to:
# docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Stop the stack:**

```bash
make docker-down
```

**View logs:**

```bash
make docker-logs
```

### Docker Compose Services

The production `docker-compose.yml` defines two services:

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `app` | Custom (Dockerfile) | 8501 | Streamlit application |
| `redis` | `redis:7-alpine` | 6379 | Cache layer (LRU, 256 MB max) |

Redis is configured with:
- Append-only file persistence (`appendonly yes`)
- 256 MB memory limit with LRU eviction (`allkeys-lru`)
- Health check via `redis-cli ping`

### Environment Variables

Configure via `.env` file or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENVIRONMENT` | `development` | Environment: `development`, `staging`, or `production` |
| `STREAMLIT_SERVER_PORT` | `8501` | Port the Streamlit server listens on |
| `UNIFIED_DB_PATH` | `~/.solar_toolkit/plant_registry.duckdb` | Path to the DuckDB database file |
| `GOOGLE_DRIVE_SYNC_PATH` | *(empty)* | Google Drive sync folder for cross-device DB sharing |
| `EMIG_API_KEY` | *(empty)* | API key for EMIG / Juggle Energy platform |
| `JUGGLE_API_KEY` | *(empty)* | Alias for `EMIG_API_KEY` (legacy) |
| `NREL_API_KEY` | *(empty)* | API key for NREL services |
| `SOLARGIS_API_KEY` | *(empty)* | API key for SolarGIS irradiance data |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `console` | Log format: `console` (human-readable) or `json` (structured) |
| `SMA_CLIENT_ID` | *(empty)* | OAuth2 client ID for SMA adapter |
| `SMA_CLIENT_SECRET` | *(empty)* | OAuth2 client secret for SMA adapter |

**Example `.env` file:**

```env
APP_ENVIRONMENT=production
EMIG_API_KEY=your-emig-api-key-here
NREL_API_KEY=your-nrel-api-key-here
SOLARGIS_API_KEY=your-solargis-key-here
LOG_LEVEL=INFO
LOG_FORMAT=json
GOOGLE_DRIVE_SYNC_PATH=~/Library/CloudStorage/GoogleDrive-user@ampyr.com/My Drive/SolarPortfolioManager/databases
```

### Configuration Hierarchy

Settings are resolved in priority order:

1. **Environment variables** (highest priority)
2. **`.env` file** values
3. **Environment-specific config** (`app_config/production.py`, `app_config/staging.py`, `app_config/development.py`)
4. **Base config** (`app_config/base.py`) — defaults

The validated settings model is defined in `services/config.py` using Pydantic v2 (`pydantic-settings`).

### Make Targets

| Target | Command | Description |
|--------|---------|-------------|
| `make dev` | `streamlit run app.py --server.port=8501 --server.runOnSave=true` | Start dev server with hot-reload |
| `make run` | `streamlit run app.py --server.port=8501 --server.headless=true` | Start headless (no browser auto-open) |
| `make test` | `pytest tests/ -v --tb=short` | Run all tests |
| `make test-cov` | `pytest tests/ -v --cov=services --cov=modules --cov-report=html` | Run tests with HTML coverage report |
| `make lint` | `ruff check .` | Run linter |
| `make format` | `ruff format . && ruff check --fix .` | Auto-format code |
| `make docker-build` | `docker compose build` | Build Docker images |
| `make docker-up` | `docker compose up -d` | Start production stack |
| `make docker-up-dev` | `docker compose -f ... up` | Start development stack |
| `make docker-down` | `docker compose down` | Stop stack |
| `make docker-logs` | `docker compose logs -f app` | Tail application logs |
| `make db-shell` | Opens DuckDB interactive shell | Inspect database tables |

### Health Check

The Docker container includes a health check that polls the Streamlit internal endpoint:

```
http://localhost:8501/_stcore/health
```

Parameters:
- **Interval:** 30 seconds
- **Timeout:** 10 seconds
- **Retries:** 3
- **Start period:** 20 seconds

---

## User Management

### Authentication Architecture

The authentication system (`services/auth_service.py`) manages users in a SQLite database located at `~/.solar_toolkit/users.db`.

**Database tables:**

| Table | Purpose |
|-------|---------|
| `users` | User accounts (username, email, password hash, role, active status) |
| `sessions` | Active sessions with expiry tracking |
| `audit_log` | Audit trail of all user actions |

### Default Admin Account

On first run, the system automatically creates a default admin user:

- **Username:** `admin`
- **Email:** `admin@ampyr.com`
- **Role:** `admin`
- **Password:** Auto-generated (printed to console output)

> ⚠️ **IMPORTANT:** Note the auto-generated password from the startup logs and change it immediately.

The console will display:
```
[AUTH] Default admin user created. Username: admin | Password: <random-token>
[AUTH] *** Change this password immediately after first login! ***
```

### Creating Users

Users are created via the `AuthService.create_user()` method. Admins can manage users through the **User Management** page (accessible via sidebar → Settings area).

**Via the UI:**

1. Log in as an admin.
2. Navigate to User Management.
3. Fill in username, email, full name, and password.
4. Select a role.
5. Click Create.

**Programmatically:**

```python
from services.auth_service import AuthService

auth = AuthService()
auth.create_user(
    username="jane.doe",
    email="jane@ampyr.com",
    full_name="Jane Doe",
    password="initial-password-change-me",
    role="engineer"
)
```

### Role Assignment

Four roles are available, each with escalating permissions:

| Role | read | write | delete | export | manage_users | manage_settings |
|------|------|-------|--------|--------|--------------|-----------------|
| `viewer` | ✅ | — | — | — | — | — |
| `analyst` | ✅ | ✅ | — | ✅ | — | — |
| `manager` | ✅ | ✅ | — | ✅ | — | — |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

In the page registry, navigation visibility is controlled per role. Four navigation roles are used: `viewer`, `engineer`, `manager`, `admin`. Pages only appear in the sidebar for users with a matching role.

### Plant-Level Access Control

The `AccessControlService` (`services/access_control.py`) provides granular per-user plant access stored in DuckDB:

**Tables:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `user_plant_access` | `user_id`, `plant_uid`, `granted_by`, `granted_at` | Maps users to permitted plants |
| `user_feature_access` | `user_id`, `feature`, `granted_by`, `granted_at` | Maps users to enabled features |

**Grant plant access:**

```python
from services.access_control import AccessControlService

acl = AccessControlService()
acl.grant_plant_access(user_id="jane.doe", plant_uid="PLANT001", granted_by="admin")
```

**Check permissions:**

```python
perms = acl.get_permissions("jane.doe")
if perms.has_plant_access("PLANT001"):
    # User can see this plant
    ...
```

Admin users bypass all plant-level restrictions.

---

## Database

### DuckDB File Location

The application uses a single consolidated DuckDB database file. The default location is:

```
~/.solar_toolkit/plant_registry.duckdb
```

Override via the `UNIFIED_DB_PATH` environment variable.

**Google Drive sync** (optional):

If `GOOGLE_DRIVE_SYNC_PATH` is set and the path exists, the database is loaded from:
```
$GOOGLE_DRIVE_SYNC_PATH/plant_registry.duckdb
```

This enables cross-device database sharing via Google Drive.

### Key Tables

| Table | Approx. Rows | Description |
|-------|--------------|-------------|
| `plants` | ~20 | Plant registry with capacity, location, API config |
| `readings` | ~1.28M | Timestamped operational data (generation, irradiance, etc.) |
| `solar_data` | ~95 | Monthly aggregated data for reporting |
| `alert_rules` | 12 | Alert rule definitions |
| `alert_history` | Variable | Fired alert records |
| `tickets` | Variable | Operational tickets from alerts |
| `user_plant_access` | Variable | Per-user plant permissions |
| `user_feature_access` | Variable | Per-user feature permissions |
| `_cache` | Variable | Query cache entries |
| `_mv_metadata` | Variable | Materialised view refresh timestamps |

### Database Shell

Quick database inspection via Make:

```bash
make db-shell
```

Or manually:

```python
import duckdb
conn = duckdb.connect("~/.solar_toolkit/plant_registry.duckdb")
conn.execute("SHOW TABLES").fetchall()
conn.execute("SELECT COUNT(*) FROM readings").fetchone()
conn.close()
```

### Backup Procedures

DuckDB stores everything in a single file, making backup straightforward:

**Manual backup:**

```bash
# Simple file copy (ensure no active connections for consistency)
cp ~/.solar_toolkit/plant_registry.duckdb ~/.solar_toolkit/backups/plant_registry_$(date +%Y%m%d).duckdb
```

**Scheduled backup (crontab):**

```cron
# Daily backup at 02:00
0 2 * * * cp ~/.solar_toolkit/plant_registry.duckdb ~/.solar_toolkit/backups/plant_registry_$(date +\%Y\%m\%d).duckdb
```

**Retention policy:**

```bash
# Delete backups older than 30 days
find ~/.solar_toolkit/backups/ -name "plant_registry_*.duckdb" -mtime +30 -delete
```

> ⚠️ **Important:** DuckDB files should ideally be copied when no connections are active. In production with Docker, stop the app container briefly or use the DuckDB `EXPORT DATABASE` command for a consistent snapshot.

**Consistent export (while running):**

```sql
-- From within a DuckDB connection
EXPORT DATABASE '/path/to/backup_dir' (FORMAT PARQUET);
```

### Migration Scripts

| Script | Purpose |
|--------|---------|
| `scripts/migrate_to_postgres.py` | Migrate DuckDB data to PostgreSQL for larger-scale deployments |

### Database Viewer

The **Database Viewer** module (Admin → Database Viewer, 🗃️) provides a web-based interface for inspecting all database tables, viewing schemas, and running ad-hoc queries. This is restricted to the `admin` role.

---

## Data Sources

### API Adapter Architecture

Data ingestion is handled by a set of adapters in `services/ingestion/`, all inheriting from `DataSourceAdapter` (defined in `services/ingestion/base.py`).

Each adapter:
- Connects to an external monitoring API
- Fetches data for a specified date range
- Maps vendor-specific fields to the standard `Reading` model
- Returns normalised data for storage in DuckDB

### Available Adapters

| Adapter | File | Source | Auth |
|---------|------|--------|------|
| **EMIG / Juggle** | `emig_adapter.py` | EMIG monitoring API | API key (`EMIG_API_KEY`) |
| **Juggle** | `juggle_adapter.py` | Juggle Energy platform | API key |
| **SMA** | `sma_adapter.py` | SMA Sunny Portal / ennexOS | OAuth2 (`SMA_CLIENT_ID`, `SMA_CLIENT_SECRET`) |
| **Enphase** | `enphase_adapter.py` | Enphase Enlighten | API key |
| **SolarEdge** | `solaredge_adapter.py` | SolarEdge monitoring | API key |
| **Huawei** | `huawei_adapter.py` | Huawei FusionSolar | API key |
| **Fronius** | `fronius_adapter.py` | Fronius Solar.web | API key |
| **SolarGIS** | `solargis_adapter.py` | Satellite irradiance data | API key (`SOLARGIS_API_KEY`) |
| **Generic CSV** | `generic_csv.py` | Manual file upload | None |

### Data Confidence Scores

Each adapter has an associated confidence score reflecting the reliability of its data:

| Source | Confidence |
|--------|------------|
| EMIG | 0.95 |
| Juggle | 0.93 |
| SMA | 0.92 |
| Enphase | 0.92 |
| SolarEdge | 0.91 |
| Huawei | 0.90 |
| Fronius | 0.90 |
| SolarGIS | 0.85 (satellite-derived) |

### Adapter Health Monitoring

Monitor adapter status via:

1. **API Management UI** (Admin → API Management) — Test connectivity, view last-success timestamps.
2. **System Health** (Admin → System Health) — See adapter status in the system health dashboard.
3. **Application logs** — Adapter errors are logged with structlog including adapter name, plant UID, and error details.

### Data Pull Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/data_pull.py` | Pull latest data for all plants | `python scripts/data_pull.py` |
| `scripts/historic_data_pull.py` | Backfill historical data for a specified date range | `python scripts/historic_data_pull.py --start 2024-01-01 --end 2024-12-31` |
| `scripts/bulk_historic_pull.py` | Bulk historical pull across all plants | `python scripts/bulk_historic_pull.py` |
| `scripts/retry_failed_pulls.py` | Retry previously failed data pulls | `python scripts/retry_failed_pulls.py` |
| `scripts/export_limit_historic_pull.py` | Pull historical export limit data | `python scripts/export_limit_historic_pull.py` |
| `scripts/import_poa_dec2025.py` | Import POA irradiance data (December 2025) | `python scripts/import_poa_dec2025.py` |

### Ingestion Coordinator

The `services/ingestion/coordinator.py` orchestrates multi-adapter ingestion, handling:
- Adapter selection based on plant configuration
- Rate limiting (EMIG: 60 req/min)
- Error handling and retry logic
- Data deduplication on insert

---

## Monitoring

### Application Health

**Streamlit health endpoint:**

```
GET http://localhost:8501/_stcore/health
```

Returns `ok` when the server is running. Used by Docker health checks.

**System Health module:**

Navigate to **Admin → System Health** (💚) for a comprehensive dashboard showing:

- Application uptime
- Database connection status and size
- Redis connectivity and memory usage
- Adapter health and last successful pull
- Recent error counts
- Cache hit rates

### Structured Logging

The application uses **structlog** for structured logging, configured in `services/logging.py`.

**Configuration:**

| Setting | Development | Production |
|---------|-------------|------------|
| Format | Console (coloured) | JSON |
| Level | DEBUG | INFO |
| Output | stderr | stderr |

**Log fields include:**
- Timestamp (ISO 8601)
- Log level
- Logger name
- Event message
- Contextual fields (plant_uid, user_id, adapter_name, etc.)

**Example JSON log entry:**

```json
{
  "timestamp": "2026-02-14T10:30:00.000Z",
  "level": "info",
  "event": "data_pull_complete",
  "plant_uid": "PLANT001",
  "adapter": "emig",
  "rows_inserted": 96,
  "duration_seconds": 2.3
}
```

### Observability

The observability module (`services/observability.py`) provides:

- **Request timing** — Decorator-based function timing
- **Cache tracking** — Hit/miss rates for query cache
- **Error aggregation** — Recent error counts by category
- **Metrics collection** — In-memory metrics with deque-based windowing

Enable/disable observability via the `ENABLE_OBSERVABILITY` flag (default: `true`).

### Key Metrics to Watch

| Metric | Healthy | Warning | Action |
|--------|---------|---------|--------|
| Health endpoint | `ok` | Not responding | Restart container |
| DuckDB file size | < 2 GB | > 2 GB | Consider archiving old data |
| Redis memory | < 200 MB | > 200 MB | Check eviction stats |
| Data freshness (per plant) | < 1 hour | > 4 hours | Check adapter health |
| Error rate (logs) | < 1/hr | > 10/hr | Investigate root cause |
| Login failures (audit log) | < 5/day | > 20/day | Possible brute-force attempt |

---

## Maintenance

### Cache Clearing

**Application cache:**

The application uses an in-memory and DuckDB-backed cache layer (`services/cache_layer.py`).

```sql
-- Clear all cached queries
DELETE FROM _cache;
```

**Redis cache:**

```bash
# Connect to Redis and flush
redis-cli FLUSHDB

# Or from Docker
docker compose exec redis redis-cli FLUSHDB
```

**Materialised views:**

```sql
-- Reset all materialised views
DELETE FROM _mv_metadata;
```

After clearing caches, restart the application for a clean state.

### Report Cleanup

Generated reports are stored in the `reports/` directory. Temporary files reside in `reports/tmp/`.

```bash
# Remove temporary report files
rm -rf reports/tmp/*

# Remove reports older than 90 days
find reports/ -name "*.pdf" -mtime +90 -delete
```

### Database Optimization

DuckDB is self-optimising for most workloads. For large databases:

```sql
-- Analyse tables to update statistics
ANALYZE;

-- Vacuum to reclaim space after large deletes
VACUUM;

-- Check database size
SELECT database_size FROM pragma_database_size();
```

**Archive old readings:**

```sql
-- Export old data to Parquet before deleting
COPY (SELECT * FROM readings WHERE timestamp < '2023-01-01') TO 'archive_2022.parquet' (FORMAT PARQUET);

-- Delete archived data
DELETE FROM readings WHERE timestamp < '2023-01-01';

-- Reclaim space
VACUUM;
```

### Dependency Updates

```bash
# Check for outdated packages
pip list --outdated

# Update all dependencies
pip install -r requirements.txt --upgrade

# Or update a specific package
pip install --upgrade streamlit

# Rebuild Docker image after updates
make docker-build
```

> **Tip:** Pin dependency versions in `requirements.txt` for production. Test updates in the development environment first.

---

## Disaster Recovery

### Database Backup / Restore

**Backup (file copy):**

```bash
# Stop the application for a consistent backup
make docker-down

# Copy the database
cp ~/.solar_toolkit/plant_registry.duckdb /backup/plant_registry_$(date +%Y%m%d_%H%M%S).duckdb

# Restart
make docker-up
```

**Backup (DuckDB export — safe while running):**

```sql
-- Export all tables to Parquet (each table becomes a .parquet file)
EXPORT DATABASE '/backup/solar_export_20260214' (FORMAT PARQUET);
```

**Restore from file copy:**

```bash
make docker-down
cp /backup/plant_registry_20260214.duckdb ~/.solar_toolkit/plant_registry.duckdb
make docker-up
```

**Restore from Parquet export:**

```sql
-- Import from a previous export
IMPORT DATABASE '/backup/solar_export_20260214';
```

### Configuration Backup

Back up these configuration files:

| File / Path | Content |
|-------------|---------|
| `.env` | API keys and environment settings |
| `~/.solar_toolkit/users.db` | User accounts and audit log (SQLite) |
| `~/.solar_toolkit/plant_registry.duckdb` | All plant data |
| `app_config/*.py` | Environment-specific configuration |

```bash
# Full configuration backup
mkdir -p /backup/config_$(date +%Y%m%d)
cp .env /backup/config_$(date +%Y%m%d)/
cp ~/.solar_toolkit/users.db /backup/config_$(date +%Y%m%d)/
cp -r app_config/ /backup/config_$(date +%Y%m%d)/
```

### Recovery Procedures

**Scenario 1: Application won't start**

1. Check Docker logs: `make docker-logs`
2. Verify the DuckDB file is not corrupted: `python -c "import duckdb; duckdb.connect('path/to/db.duckdb').execute('SHOW TABLES').fetchall()"`
3. Check Redis is healthy: `docker compose exec redis redis-cli ping`
4. Verify environment variables in `.env`.
5. Rebuild the Docker image: `make docker-build && make docker-up`

**Scenario 2: Database corruption**

1. Stop the application: `make docker-down`
2. Restore from the most recent backup: `cp /backup/plant_registry_YYYYMMDD.duckdb ~/.solar_toolkit/plant_registry.duckdb`
3. Restart: `make docker-up`
4. Verify data with the Database Viewer.

**Scenario 3: Lost user database**

1. The `users.db` SQLite file can be restored from backup.
2. If no backup exists, delete the file and restart — a new default admin account will be created automatically.
3. Re-create all user accounts.

**Scenario 4: API adapter failure**

1. Check adapter health in the System Health dashboard.
2. Verify API keys haven't expired.
3. Test the API directly (use `curl` or the adapter's health check).
4. Check for rate limiting (EMIG: 60 req/min, 900s minimum interval).
5. Review adapter logs for detailed error messages.

---

## Security

### Password Management

All passwords are hashed using **bcrypt** with automatic salt generation.

- Passwords are never stored in plaintext.
- Legacy SHA-256 hashes (from earlier versions) are automatically upgraded to bcrypt on successful login.
- Minimum password requirements are enforced at the UI level.

**Changing a user's password (admin):**

```python
from services.auth_service import AuthService

auth = AuthService()
auth.change_password(user_id=2, new_password="new-secure-password")
```

### Session Management

Sessions are stored in the `sessions` SQLite table with:
- Unique session ID (cryptographically random)
- Expiry timestamp
- IP address and user agent tracking

Streamlit's built-in session state is used for the active session. Sessions expire based on the configured duration.

### Rate Limiting

Login attempts are rate-limited to prevent brute-force attacks:

- **Maximum failed attempts:** 5 per username
- **Lockout duration:** 15 minutes
- Failed attempts are tracked in-memory and pruned automatically.

Rate limiting events are logged to the audit log.

### API Key Rotation

Best practices for API key management:

1. Store API keys only in `.env` or environment variables — never commit them to version control.
2. Rotate keys periodically (at minimum quarterly).
3. When rotating:
   - Generate the new key with the provider.
   - Update `.env` with the new value.
   - Restart the application: `make docker-down && make docker-up`.
   - Verify adapter connectivity via API Management.
   - Revoke the old key with the provider.
4. Monitor for any `auth_failed` log entries after rotation.

### Audit Logging

The `audit_log` table (`~/.solar_toolkit/users.db`) records:

| Field | Description |
|-------|-------------|
| `log_id` | Auto-incrementing entry ID |
| `user_id` | ID of the acting user (NULL for failed logins) |
| `action` | Action type: `login`, `logout`, `login_failed`, `login_locked`, `password_change` |
| `resource` | Resource category: `system`, `user`, etc. |
| `details` | Additional context (e.g., failed username) |
| `timestamp` | When the event occurred |

**Query the audit log:**

```python
from services.auth_service import AuthService

auth = AuthService()

# Last 50 entries
logs = auth.get_audit_log(limit=50)

# Entries for a specific user
user_logs = auth.get_audit_log(user_id=1, limit=20)
```

**Or directly via SQLite:**

```bash
sqlite3 ~/.solar_toolkit/users.db "SELECT action, details, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT 20;"
```

### Network Security

For production deployments:

1. **Use a reverse proxy** (Nginx, Caddy, or Traefik) in front of Streamlit for TLS termination.
2. **Restrict port access** — Only expose port 8501 through the reverse proxy; do not expose Redis (6379) externally.
3. **Use Docker networks** — The default Compose configuration keeps Redis on an internal network.
4. **Enable HTTPS** — Streamlit itself does not handle TLS. Use a reverse proxy with valid certificates.

**Example Nginx reverse proxy config:**

```nginx
server {
    listen 443 ssl;
    server_name solar.ampyr.com;

    ssl_certificate     /etc/ssl/certs/solar.ampyr.com.pem;
    ssl_certificate_key /etc/ssl/private/solar.ampyr.com.key;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /_stcore/stream {
        proxy_pass http://localhost:8501/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### File Permissions

```bash
# Restrict database file access
chmod 600 ~/.solar_toolkit/plant_registry.duckdb
chmod 600 ~/.solar_toolkit/users.db
chmod 600 .env

# Ensure the application user owns the data directory
chown -R appuser:appuser ~/.solar_toolkit/
```

---

*© AMPYR Energy — Solar Portfolio Manager v1.1.0*
