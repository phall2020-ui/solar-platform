# Phase 8: Polish, Testing & Launch — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3 weeks  
**Goal:** Harden the platform for production: comprehensive testing, performance optimization, documentation, deployment automation, and go-live. This is the final phase — no new features, only quality.

**Key Principle:** Every claim must be backed by evidence. "It works" means a test says so. "It's fast" means a benchmark proves it. "It's documented" means a user can follow the docs from zero to running.

**Prerequisite:** All prior phases (0–7) substantially complete.

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 8.1: Test Infrastructure](#task-81-test-infrastructure)
4. [Task 8.2: Unit Tests](#task-82-unit-tests)
5. [Task 8.3: Integration Tests](#task-83-integration-tests)
6. [Task 8.4: End-to-End Tests](#task-84-end-to-end-tests)
7. [Task 8.5: Performance Benchmarks](#task-85-performance-benchmarks)
8. [Task 8.6: Load Testing](#task-86-load-testing)
9. [Task 8.7: User Documentation](#task-87-user-documentation)
10. [Task 8.8: Admin & Operations Guide](#task-88-admin--operations-guide)
11. [Task 8.9: Deployment Automation](#task-89-deployment-automation)
12. [Task 8.10: Go-Live Checklist](#task-810-go-live-checklist)
13. [Task 8.11: Post-Launch Monitoring](#task-811-post-launch-monitoring)
14. [Risks](#risks)
15. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 8.1 Test Infrastructure | ✅ Done | 4 | P0 | Phase 0 |
| 8.2 Unit Tests | ✅ Done | 12 | P0 | 8.1 |
| 8.3 Integration Tests | ✅ Done | 8 | P0 | 8.1 |
| 8.4 End-to-End Tests | ✅ Done | 6 | P1 | 8.1 |
| 8.5 Performance Benchmarks | ✅ Done | 6 | P0 | 8.1 |
| 8.6 Load Testing | ✅ Done | 4 | P1 | 8.5 |
| 8.7 User Documentation | ✅ Done | 8 | P0 | — |
| 8.8 Admin & Ops Guide | ✅ Done | 6 | P0 | — |
| 8.9 Deployment Automation | ✅ Done | 6 | P0 | Phase 0 |
| 8.10 Go-Live Checklist | ✅ Done | 4 | P0 | All |
| 8.11 Post-Launch Monitoring | ✅ Done | 4 | P1 | 8.9 |
| **TOTAL** | | **68** | | |

---

## 2. Dependency Graph

```
┌────────────────────────┐
│ 8.1 Test Infrastructure│
└────────┬───────────────┘
         │
    ┌────┼────────┬───────────┐
    │    │        │           │
    ▼    ▼        ▼           ▼
┌──────┐┌──────┐┌──────┐ ┌──────┐
│ 8.2  ││ 8.3  ││ 8.4  │ │ 8.5  │
│ Unit ││Integ.││ E2E  │ │Perf. │
└──────┘└──────┘└──────┘ └──┬───┘
                            │
                            ▼
                       ┌──────┐
                       │ 8.6  │
                       │ Load │
                       └──────┘

┌──────────┐  ┌──────────┐
│ 8.7 User │  │ 8.8 Admin│
│ Docs     │  │ & Ops    │
└──────────┘  └──────────┘

┌──────────┐
│ 8.9      │
│ Deploy   │
│ Automate │
└────┬─────┘
     │
     ├────────────┐
     ▼            ▼
┌──────────┐ ┌──────────┐
│ 8.10     │ │ 8.11     │
│ Go-Live  │ │ Post-    │
│ Checklist│ │ Launch   │
└──────────┘ └──────────┘
```

---

## Task 8.1: Test Infrastructure

**Goal:** Set up pytest, fixtures, test database, and CI configuration.

**Estimated Hours:** 4

### `pyproject.toml` — Test Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--tb=short",
    "-q",
    "--cov=services",
    "--cov=modules",
    "--cov-report=term-missing",
]
markers = [
    "unit: Unit tests (no external deps)",
    "integration: Integration tests (need database)",
    "e2e: End-to-end tests (need full app)",
    "slow: Tests that take > 5 seconds",
]

[tool.coverage.run]
source = ["services", "modules", "components"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
fail_under = 60
show_missing = true
```

### `tests/conftest.py`
```python
"""
Shared test fixtures.

The test database is a fresh DuckDB in a temp directory.
All tests use this isolated DB — no interaction with production data.
"""
import os
import tempfile
from pathlib import Path

import duckdb
import pytest


@pytest.fixture(scope="session")
def test_db_path():
    """Create a temporary DuckDB for testing."""
    with tempfile.TemporaryDirectory(prefix="solar_test_") as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        yield str(db_path)


@pytest.fixture(scope="session")
def test_db(test_db_path):
    """Initialize test database with schema."""
    conn = duckdb.connect(test_db_path)
    
    # Create schema (matches Phase 0 migrations)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plants (
            uid VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            capacity_kwp DOUBLE DEFAULT 0.0,
            ac_capacity_kw DOUBLE DEFAULT 0.0,
            latitude DOUBLE,
            longitude DOUBLE,
            status VARCHAR DEFAULT 'active',
            commissioning_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id VARCHAR DEFAULT gen_random_uuid()::VARCHAR,
            plant_uid VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            generation_kwh DOUBLE DEFAULT 0.0,
            irradiance_kwh_m2 DOUBLE,
            pr DOUBLE,
            temperature_c DOUBLE,
            source VARCHAR DEFAULT 'test',
            quality_score DOUBLE DEFAULT 100.0,
            quality_flags VARCHAR,
            UNIQUE(plant_uid, timestamp, source)
        )
    """)
    
    # Seed test plants
    conn.execute("""
        INSERT INTO plants (uid, name, capacity_kwp, ac_capacity_kw, latitude, longitude)
        VALUES
            ('TEST001', 'Test Plant Alpha', 1000.0, 900.0, 51.5, -0.1),
            ('TEST002', 'Test Plant Beta', 2000.0, 1800.0, 52.0, -1.5),
            ('TEST003', 'Test Plant Gamma', 500.0, 450.0, 53.2, -2.3)
    """)
    
    conn.close()
    yield test_db_path


@pytest.fixture
def db_conn(test_db):
    """Per-test database connection."""
    conn = duckdb.connect(test_db)
    yield conn
    conn.close()


@pytest.fixture
def sample_readings():
    """Sample reading data for tests."""
    import pandas as pd
    import numpy as np
    
    np.random.seed(42)
    n = 720  # 30 days × 24 hours
    
    return pd.DataFrame({
        "plant_uid": ["TEST001"] * n,
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="h"),
        "generation_kwh": np.random.normal(400, 50, n).clip(0),
        "irradiance_kwh_m2": np.random.normal(0.7, 0.1, n).clip(0),
        "pr": np.random.normal(0.82, 0.03, n).clip(0, 1),
        "temperature_c": np.random.normal(15, 5, n),
        "source": ["test"] * n,
    })
```

### Directory Structure

```
tests/
├── conftest.py
├── unit/
│   ├── test_validators.py
│   ├── test_gap_detection.py
│   ├── test_anomaly_detection.py
│   ├── test_revenue.py
│   ├── test_budget.py
│   ├── test_report_models.py
│   └── test_alert_rules.py
├── integration/
│   ├── test_db_repository.py
│   ├── test_data_fetcher.py
│   ├── test_ingestion.py
│   └── test_pdf_renderer.py
└── e2e/
    ├── test_report_generation.py
    └── test_alert_pipeline.py
```

### Acceptance Criteria

- [ ] `pytest` runs from project root with zero config
- [ ] Test database isolated from production
- [ ] Coverage reporting enabled
- [ ] CI pipeline runs tests on every push

---

## Task 8.2: Unit Tests

**Goal:** 80+ unit tests covering all service modules.

**Estimated Hours:** 12

### Coverage Targets

| Module | Min Tests | Focus Areas |
|--------|-----------|-------------|
| `services/data_quality/validators.py` | 12 | Each validator, edge cases, scoring |
| `services/data_quality/gap_detection.py` | 8 | No gaps, single gap, multiple gaps, full missing |
| `services/data_quality/gap_filling.py` | 6 | Interpolation, typical day, strategy selection |
| `services/analytics/anomaly_detection.py` | 10 | Statistical, isolation forest, contextual |
| `services/financial/revenue.py` | 6 | Fixed tariff, TOU, zero generation |
| `services/financial/budget.py` | 6 | On track, over, under, no budget |
| `services/reporting/models.py` | 4 | Template creation, section ordering |
| `services/reporting/pdf_renderer.py` | 6 | Cover, KPI table, generation table |
| `services/alert_engine.py` | 10 | Each rule type, state transitions |
| `services/pvsyst_import.py` | 4 | CSV parsing, column mapping |

### Example Test File

```python
# tests/unit/test_validators.py
"""Unit tests for data quality validators."""
import pytest
from services.data_quality.validators import (
    CapacityExceedanceValidator,
    NegativeValueValidator,
    NighttimeGenerationValidator,
    RangeValidator,
    ValidationSeverity,
    run_validation,
)


class TestRangeValidator:
    def test_within_range(self):
        v = RangeValidator("pr", 0, 1.1)
        result = v.validate({"pr": 0.82}, {})
        assert result.passed
    
    def test_below_range(self):
        v = RangeValidator("pr", 0, 1.1)
        result = v.validate({"pr": -0.5}, {})
        assert not result.passed
    
    def test_above_range(self):
        v = RangeValidator("pr", 0, 1.1)
        result = v.validate({"pr": 1.5}, {})
        assert not result.passed
    
    def test_null_value_skipped(self):
        v = RangeValidator("pr", 0, 1.1)
        result = v.validate({"pr": None}, {})
        assert result.passed  # Null values are skipped
    
    def test_missing_field_skipped(self):
        v = RangeValidator("pr", 0, 1.1)
        result = v.validate({}, {})
        assert result.passed


class TestCapacityExceedance:
    def test_normal_generation(self):
        v = CapacityExceedanceValidator()
        result = v.validate(
            {"generation_kwh": 500, "interval_hours": 1},
            {"ac_capacity_kw": 1000},
        )
        assert result.passed
    
    def test_exceeds_capacity(self):
        v = CapacityExceedanceValidator()
        result = v.validate(
            {"generation_kwh": 2000, "interval_hours": 1},
            {"ac_capacity_kw": 1000},
        )
        assert not result.passed
        assert result.severity == ValidationSeverity.ERROR


class TestNegativeValues:
    def test_positive_values(self):
        v = NegativeValueValidator()
        result = v.validate({"generation_kwh": 100, "pr": 0.8}, {})
        assert result.passed
    
    def test_negative_generation(self):
        v = NegativeValueValidator()
        result = v.validate({"generation_kwh": -50}, {})
        assert not result.passed


class TestNighttimeGeneration:
    def test_daytime_generation(self):
        v = NighttimeGenerationValidator()
        result = v.validate({"hour": 12, "generation_kwh": 500}, {})
        assert result.passed
    
    def test_nighttime_generation_flagged(self):
        v = NighttimeGenerationValidator()
        result = v.validate({"hour": 2, "generation_kwh": 100}, {})
        assert not result.passed


class TestRunValidation:
    def test_all_pass(self):
        reading = {"generation_kwh": 100, "irradiance_kwh_m2": 0.8, "pr": 0.82, "hour": 12}
        report = run_validation(reading, {"ac_capacity_kw": 500})
        assert report.passed
        assert report.quality_score > 80
    
    def test_mixed_results(self):
        reading = {"generation_kwh": -50, "irradiance_kwh_m2": 0.8, "pr": 0.82, "hour": 12}
        report = run_validation(reading, {"ac_capacity_kw": 500})
        assert not report.passed  # negative generation is ERROR
        assert report.error_count >= 1
```

### Acceptance Criteria

- [ ] 80+ unit tests written
- [ ] All service modules have test files
- [ ] `pytest tests/unit/ -q` passes 100%
- [ ] Coverage ≥ 60% on services/

---

## Task 8.3: Integration Tests

**Goal:** Test service interactions with the database and across modules.

**Estimated Hours:** 8

### Test Scenarios

| Test | Description |
|------|-------------|
| Ingest → query back | Insert reading via adapter → read back via repository |
| Alert pipeline | Insert readings → run alert rules → verify alerts created |
| Report generation | Template + data → PDF file exists and is valid |
| Gap detection + filling | Insert data with gaps → detect → fill → verify completeness |
| Revenue calculation | Insert readings + tariff → calculate revenue → verify total |
| Access control | Assign plants to user → verify filtered results |

### Example

```python
# tests/integration/test_alert_pipeline.py
"""Integration test: readings → alert detection → alert creation."""
import pytest
from datetime import datetime


@pytest.mark.integration
class TestAlertPipeline:
    def test_low_pr_triggers_alert(self, db_conn, sample_readings):
        """Insert readings with low PR → alert rule should fire."""
        # 1. Insert readings with artificially low PR
        low_pr_readings = sample_readings.copy()
        low_pr_readings["pr"] = 0.5  # Well below threshold
        
        # Insert into DB
        db_conn.executemany(
            "INSERT INTO readings (plant_uid, timestamp, generation_kwh, pr, source) VALUES (?, ?, ?, ?, ?)",
            low_pr_readings[["plant_uid", "timestamp", "generation_kwh", "pr", "source"]].values.tolist()
        )
        
        # 2. Run alert evaluation
        from services.alert_engine import AlertRuleEngine
        engine = AlertRuleEngine(db_conn)
        alerts = engine.evaluate_all()
        
        # 3. Verify
        low_pr_alerts = [a for a in alerts if a.rule_name == "low_pr"]
        assert len(low_pr_alerts) > 0, "Should detect low PR"
```

### Acceptance Criteria

- [ ] 15+ integration tests
- [ ] Use test database (not production)
- [ ] Test cross-module interactions
- [ ] Clean up test data after each test

---

## Task 8.4: End-to-End Tests

**Goal:** Test complete user flows using Streamlit testing utilities.

**Estimated Hours:** 6

### Flows to Test

1. **Login → Dashboard → Plant Detail**: Authenticate, see KPIs, drill into plant
2. **Report Generation**: Select template → configure → generate → download PDF
3. **Alert → Ticket**: Trigger alert → auto-create ticket → acknowledge
4. **Data Import**: Upload CSV → validate → ingest → verify in explorer

### Framework

```python
# Using Streamlit's AppTest (built-in testing)
# tests/e2e/test_dashboard.py
from streamlit.testing.v1 import AppTest


@pytest.mark.e2e
def test_dashboard_loads():
    """Dashboard page loads without errors."""
    at = AppTest.from_file("modules/dashboard.py")
    at.run(timeout=10)
    assert not at.exception
    # Check that KPI metrics are displayed
    assert len(at.metric) >= 3
```

### Acceptance Criteria

- [ ] 5+ end-to-end tests for critical flows
- [ ] Tests run in CI with Streamlit headless mode
- [ ] Failure screenshots captured where possible

---

## Task 8.5: Performance Benchmarks

**Goal:** Establish performance baselines and targets for key operations.

**Estimated Hours:** 6

### Targets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Dashboard load (20 plants) | < 2 seconds | Time from page request to all metrics rendered |
| Plant detail load | < 1 second | Time from selection to data displayed |
| 30-day reading query (1 plant) | < 200ms | DuckDB query time |
| 1-year reading query (1 plant) | < 500ms | DuckDB query time |
| Full portfolio query (20 plants) | < 1 second | Aggregate query time |
| PDF report generation (monthly) | < 10 seconds | Template to PDF file |
| Alert rule evaluation (all plants) | < 3 seconds | Full sweep time |
| CSV import (10K rows) | < 5 seconds | File upload to database commit |
| Anomaly detection (1 plant, 1 year) | < 5 seconds | All three methods |
| Data quality validation (1K readings) | < 1 second | All 8 validators |

### Benchmark Script

```python
# tests/benchmarks/bench_queries.py
"""Performance benchmarks for database queries."""
import time
import duckdb


def benchmark(name: str, func, iterations: int = 10):
    """Run a function N times and report timing."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    p95 = sorted(times)[int(0.95 * len(times))]
    print(f"{name}: avg={avg*1000:.1f}ms, p95={p95*1000:.1f}ms")
    return avg


def run_benchmarks(db_path: str):
    conn = duckdb.connect(db_path, read_only=True)
    
    # Query benchmarks
    benchmark("30-day single plant", lambda: conn.execute(
        "SELECT * FROM readings WHERE plant_uid = 'TEST001' AND timestamp > CURRENT_TIMESTAMP - INTERVAL '30 days'"
    ).fetchdf())
    
    benchmark("Portfolio aggregate", lambda: conn.execute(
        "SELECT plant_uid, SUM(generation_kwh), AVG(pr) FROM readings GROUP BY plant_uid"
    ).fetchdf())
    
    benchmark("Daily rollup", lambda: conn.execute(
        "SELECT DATE_TRUNC('day', timestamp), SUM(generation_kwh) FROM readings GROUP BY 1 ORDER BY 1"
    ).fetchdf())
    
    conn.close()
```

### Acceptance Criteria

- [ ] All targets documented with measurements
- [ ] Benchmark script runs reproducibly
- [ ] Dashboard loads in < 2 seconds with 20 plants
- [ ] DuckDB queries meet targets with 1.28M rows

---

## Task 8.6: Load Testing

**Goal:** Test with realistic data volumes to find breaking points.

**Estimated Hours:** 4

### Data Volumes to Test

| Scenario | Plants | Readings | Expected Size |
|----------|--------|----------|---------------|
| Current | 20 | 1.28M | ~150 MB |
| Growth (1 year) | 50 | 5M | ~600 MB |
| Stress | 100 | 20M | ~2.4 GB |
| Extreme | 200 | 50M | ~6 GB |

### Load Test Script

```python
# tests/benchmarks/generate_load_data.py
"""Generate synthetic data for load testing."""
import duckdb
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_readings(n_plants: int, days: int, freq_hours: int = 1) -> pd.DataFrame:
    """Generate synthetic readings for load testing."""
    readings_per_plant = days * 24 // freq_hours
    total = n_plants * readings_per_plant
    
    print(f"Generating {total:,} readings for {n_plants} plants × {days} days...")
    
    np.random.seed(42)
    plant_uids = [f"LOAD_{i:04d}" for i in range(n_plants)]
    
    rows = []
    for uid in plant_uids:
        capacity = np.random.uniform(500, 5000)
        timestamps = pd.date_range(
            datetime(2024, 1, 1),
            periods=readings_per_plant,
            freq=f"{freq_hours}h",
        )
        gen = np.random.normal(capacity * 0.15, capacity * 0.05, readings_per_plant).clip(0)
        irr = np.random.normal(0.7, 0.15, readings_per_plant).clip(0, 1.5)
        pr = np.random.normal(0.82, 0.04, readings_per_plant).clip(0.3, 1.0)
        
        df = pd.DataFrame({
            "plant_uid": uid,
            "timestamp": timestamps,
            "generation_kwh": gen,
            "irradiance_kwh_m2": irr,
            "pr": pr,
            "source": "load_test",
        })
        rows.append(df)
    
    return pd.concat(rows, ignore_index=True)
```

### Acceptance Criteria

- [ ] System handles 5M readings without degradation
- [ ] Dashboard still loads in < 3 seconds with 50 plants
- [ ] DuckDB file size manageable (< 1 GB at 5M rows)
- [ ] Memory usage documented at each scale

---

## Task 8.7: User Documentation

**Goal:** End-user guide for the solar portfolio manager.

**Estimated Hours:** 8

### `docs/USER_GUIDE.md` — Structure

```markdown
# AMPYR Solar Portfolio Manager — User Guide

## Getting Started
- Logging in
- Navigation overview
- Dashboard walkthrough

## Portfolio Overview
- Understanding KPI cards
- Plant status indicators
- Portfolio map

## Plant Detail
- Performance tab
- Generation charts
- PR analysis

## Analysis Tools
- Comparative analysis
- Clipping analysis
- Loss waterfall
- Data explorer

## Reports
- Generating a monthly report
- Customizing sections
- Report library

## Alerts & Tickets
- Understanding alert types
- Acknowledging alerts
- Creating tickets manually
- Kanban board

## Data Management
- Importing CSV data
- PVsyst import
- Data quality indicators
- Understanding quality badges

## Financial Overview
- Revenue tracking
- Budget vs. actual
- Tariff management

## Settings
- Theme (light/dark)
- User preferences
- API key management

## Troubleshooting
- Common errors
- Data not loading
- Report generation issues
```

### Acceptance Criteria

- [ ] Complete user guide covering all features
- [ ] Screenshots for key workflows
- [ ] Searchable structure
- [ ] Troubleshooting section

---

## Task 8.8: Admin & Operations Guide

**Goal:** Documentation for administrators and operators.

**Estimated Hours:** 6

### `docs/ADMIN_GUIDE.md` — Structure

```markdown
# Administration & Operations Guide

## Deployment
- Docker Compose setup
- Environment variables
- SSL/TLS configuration

## User Management
- Creating users
- Role assignment
- Plant access control

## Database
- DuckDB file location
- Backup procedures
- Migration scripts
- Viewing database statistics

## Data Sources
- API key configuration
- Adapter health checks
- Polling schedule
- Manual data trigger

## Monitoring
- Application health endpoint
- Log file locations (structlog)
- Key metrics to watch
- Alert on application errors

## Maintenance
- Clearing cache
- Report cleanup
- Database optimization
- Updating dependencies

## Disaster Recovery
- Database backup/restore
- Configuration backup
- Recovery time objective: < 1 hour

## Security
- Password policy
- Session management
- API key rotation
- Audit logging
```

### Acceptance Criteria

- [ ] Deployment documented step-by-step
- [ ] Backup and restore procedures tested
- [ ] Monitoring checklist complete
- [ ] Security hardening steps documented

---

## Task 8.9: Deployment Automation

**Goal:** One-command deployment with rollback capability.

**Estimated Hours:** 6

### `docker-compose.yml` — Production Ready

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "${PORT:-8501}:8501"
    volumes:
      - solar_data:/root/.solar_toolkit
      - reports:/app/reports
    environment:
      - ENVIRONMENT=production
      - STREAMLIT_SERVER_HEADLESS=true
      - STREAMLIT_SERVER_ENABLE_CORS=false
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'

  api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uvicorn api.main:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    volumes:
      - solar_data:/root/.solar_toolkit
    environment:
      - ENVIRONMENT=production
    restart: unless-stopped
    profiles:
      - api  # Only started when explicitly requested

volumes:
  solar_data:
    driver: local
  reports:
    driver: local
```

### `scripts/deploy.sh`
```bash
#!/bin/bash
set -euo pipefail

# Deployment script with rollback
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"

echo "=== AMPYR Solar Portfolio Manager — Deploy ==="

# 1. Pre-flight checks
echo "1. Pre-flight checks..."
docker compose version || { echo "Docker Compose not found"; exit 1; }

# 2. Backup database
echo "2. Backing up database..."
mkdir -p "$BACKUP_DIR"
if docker compose exec -T app test -f /root/.solar_toolkit/plant_registry.duckdb; then
    docker compose cp app:/root/.solar_toolkit/plant_registry.duckdb "$BACKUP_DIR/"
    echo "   Database backed up to $BACKUP_DIR"
else
    echo "   No existing database to backup"
fi

# 3. Pull/build new image
echo "3. Building new image..."
docker compose build --no-cache

# 4. Rolling restart
echo "4. Deploying..."
docker compose up -d --remove-orphans

# 5. Health check
echo "5. Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo "   Healthy after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "   UNHEALTHY — rolling back..."
        docker compose down
        echo "   Restore database from $BACKUP_DIR if needed"
        exit 1
    fi
    sleep 1
done

echo "=== Deploy complete ==="
```

### `scripts/rollback.sh`
```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:?Usage: rollback.sh <backup_dir>}"

echo "=== Rolling back to $BACKUP_DIR ==="

# Stop current deployment
docker compose down

# Restore database
if [ -f "$BACKUP_DIR/plant_registry.duckdb" ]; then
    echo "Restoring database..."
    docker compose run --rm -v "$BACKUP_DIR:/backup" app \
        cp /backup/plant_registry.duckdb /root/.solar_toolkit/
fi

# Start previous version
docker compose up -d
echo "=== Rollback complete ==="
```

### Acceptance Criteria

- [ ] Single command deployment: `./scripts/deploy.sh`
- [ ] Database backup before every deploy
- [ ] Health check with 30-second timeout
- [ ] Automated rollback on health check failure
- [ ] Rollback script: `./scripts/rollback.sh <backup_dir>`

---

## Task 8.10: Go-Live Checklist

**Goal:** Pre-launch verification checklist — every item must be checked before go-live.

**Estimated Hours:** 4

### Checklist

```markdown
## Go-Live Checklist

### Security
- [ ] Default admin password changed
- [ ] API keys stored in environment variables (not in code)
- [ ] HTTPS enabled in production
- [ ] Session timeout configured (< 30 min idle)
- [ ] Rate limiting on login endpoint
- [ ] Audit logging enabled

### Data
- [ ] All 20 plants in plant registry
- [ ] Historical data loaded (at least 3 months)
- [ ] API adapters tested with production credentials
- [ ] Data quality backfill complete
- [ ] PVsyst budgets imported for all plants

### Application
- [ ] Dashboard loads in < 2 seconds
- [ ] All 18 pages accessible and functional
- [ ] PDF report generation tested
- [ ] Alert rules evaluated on real data
- [ ] Ticket system creates tickets from alerts
- [ ] Search returns results for all plants

### Infrastructure
- [ ] Docker container starts cleanly
- [ ] Health check endpoint responds
- [ ] Database backup automated (daily)
- [ ] Log aggregation configured
- [ ] Disk space monitoring (alert at 80%)
- [ ] Memory usage under 2 GB

### Documentation
- [ ] User guide complete and reviewed
- [ ] Admin guide complete
- [ ] API documentation published (if API enabled)
- [ ] Runbook for common operations

### Stakeholders
- [ ] Demo to key stakeholders
- [ ] Training session for primary users
- [ ] Support contact established
- [ ] Feedback channel set up
```

### Acceptance Criteria

- [ ] Every checklist item verified with evidence
- [ ] Sign-off from project lead
- [ ] Deployment date confirmed

---

## Task 8.11: Post-Launch Monitoring

**Goal:** Define monitoring, alerting, and support procedures for the first 30 days.

**Estimated Hours:** 4

### Monitoring Plan

| Metric | Target | Alert Threshold | Check Frequency |
|--------|--------|-----------------|-----------------|
| App uptime | 99.5% | Any downtime > 5 min | Continuous |
| Response time (dashboard) | < 2s | > 5s for 3 consecutive checks | Every 5 min |
| Database size | < 500 MB | > 1 GB | Daily |
| Memory usage | < 1.5 GB | > 2 GB | Every 5 min |
| Failed API pulls | 0 | > 3 consecutive failures | Per adapter run |
| Error log rate | < 5/hour | > 20/hour | Every 15 min |
| Data freshness | < 6 hours | > 24 hours any plant | Hourly |
| Report generation failures | 0 | Any failure | Per generation |

### Support Tiers

| Tier | Response Time | Who | Issues |
|------|---------------|-----|--------|
| P0 (Critical) | 15 min | On-call engineer | App down, data loss |
| P1 (High) | 1 hour | Development team | Feature broken, data incorrect |
| P2 (Medium) | 4 hours | Development team | Minor bug, UI issue |
| P3 (Low) | Next business day | Development team | Enhancement request |

### Week 1 Post-Launch Actions

1. **Daily**: Check dashboard load time, error logs, data freshness
2. **Daily**: Verify alert rules running correctly
3. **Daily**: Review user feedback
4. **End of week 1**: Performance report vs. benchmarks
5. **End of week 1**: Retrospective with stakeholders

### Acceptance Criteria

- [ ] Monitoring dashboard or script in place
- [ ] Alert thresholds configured
- [ ] On-call schedule defined (first 2 weeks)
- [ ] Retrospective scheduled for week 1

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Test coverage gaps in legacy code | Medium | High | Focus on new services; accept lower coverage on modules/ |
| Performance degrades under real load | High | Medium | Benchmark early; optimize DuckDB queries |
| Deployment script fails on target machine | Medium | Medium | Test on clean Docker environment; document prerequisites |
| Users resist new interface | Medium | Medium | Training session; keep familiar workflows |
| Database corruption during deploy | High | Low | Backup before every deploy; test restore procedure |
| Post-launch bugs overwhelm support | Medium | Medium | Prioritize critical paths; have rollback ready |

---

## Definition of Done

- [ ] 80+ unit tests passing
- [ ] 15+ integration tests passing
- [ ] 5+ end-to-end tests passing
- [ ] Code coverage ≥ 60% on services/
- [ ] All performance benchmarks meet targets
- [ ] Load test with 5M readings stable
- [ ] User guide complete
- [ ] Admin guide complete
- [ ] Deploy script tested on clean environment
- [ ] Go-live checklist 100% complete
- [ ] Post-launch monitoring active
- [ ] Stakeholder sign-off received
