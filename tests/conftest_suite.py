"""
Additional shared fixtures and utilities for the Solar Platform extended test suite.

This module supplements ``tests/conftest.py`` with fixtures used by:
  - test_compile_and_imports.py  (marker: compile)
  - test_performance.py          (marker: performance)
  - test_ui_errors.py            (marker: ui)
  - test_error_resilience.py     (marker: resilience)

Import or conftest-auto-discovery makes these fixtures available to any test
in the ``tests/`` directory tree.
"""

from __future__ import annotations

import contextlib
import random
import sys
import time
import warnings
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ══════════════════════════════════════════════════════════════════════════
#  Custom markers
# ══════════════════════════════════════════════════════════════════════════

def pytest_configure(config: pytest.Config) -> None:
    """Register additional markers used by the extended test suite."""
    config.addinivalue_line("markers", "performance: Speed and memory benchmarks")
    config.addinivalue_line("markers", "compile: Compilation and import verification")
    config.addinivalue_line("markers", "ui: UI error detection and page safety")
    config.addinivalue_line("markers", "resilience: Error-handling across all layers")


# ══════════════════════════════════════════════════════════════════════════
#  Auto-use: capture warnings during every test
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _capture_warnings(request: pytest.FixtureRequest) -> Generator[list[warnings.WarningMessage], None, None]:
    """Record warnings emitted during each test.

    The captured list is attached to the test node so downstream
    fixtures or plugins can inspect it.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield caught
    # Attach to the node for optional inspection in teardown hooks
    request.node._captured_warnings = caught  # type: ignore[attr-defined]


# ══════════════════════════════════════════════════════════════════════════
#  Data-generation utilities
# ══════════════════════════════════════════════════════════════════════════

PLANT_NAMES = [
    "Sunny Acres",
    "Green Fields",
    "Hilltop Solar",
    "BAE Fylde",
    "Blachford",
    "Inverurie",
    "Westfield Park",
    "Beacon Hill",
    "Fenland Array",
    "Croft Meadow",
]


def generate_solar_timeseries(
    n_rows: int = 1_000,
    n_plants: int = 3,
    *,
    start: datetime | None = None,
    freq_minutes: int = 30,
    seed: int = 42,
) -> pd.DataFrame:
    """Create a realistic solar-monitoring DataFrame.

    Columns: timestamp, plant, device_id, power_kw, irradiance_wm2,
             pr, temperature_c, energy_kwh
    """
    rng = np.random.default_rng(seed)
    start = start or datetime(2025, 1, 1, tzinfo=UTC)

    plants = PLANT_NAMES[:n_plants]
    rows_per_plant = n_rows // n_plants
    remainder = n_rows - rows_per_plant * n_plants

    records: list[dict[str, Any]] = []
    for i, plant in enumerate(plants):
        count = rows_per_plant + (1 if i < remainder else 0)
        timestamps = pd.date_range(start, periods=count, freq=f"{freq_minutes}min", tz="UTC")

        # Simulate a rough diurnal irradiance curve (0 at night, peak ~1000 W/m²)
        hours = np.array([t.hour + t.minute / 60 for t in timestamps])
        irr_base = np.clip(np.sin((hours - 6) / 12 * np.pi) * 1000, 0, None)
        irradiance = irr_base + rng.normal(0, 30, size=count)
        irradiance = np.clip(irradiance, 0, 1200)

        dc_capacity = rng.uniform(2000, 8000)
        pr = np.clip(rng.normal(0.82, 0.04, size=count), 0.5, 0.98)
        power = irradiance / 1000 * dc_capacity * pr
        temperature = rng.normal(22, 8, size=count)
        energy = power * (freq_minutes / 60)

        for j in range(count):
            records.append({
                "timestamp": timestamps[j],
                "plant": plant,
                "device_id": f"inv-{plant[:3].lower()}-{rng.integers(1, 5)}",
                "power_kw": round(float(power[j]), 2),
                "irradiance_wm2": round(float(irradiance[j]), 1),
                "pr": round(float(pr[j]), 4),
                "temperature_c": round(float(temperature[j]), 1),
                "energy_kwh": round(float(energy[j]), 2),
            })

    return pd.DataFrame(records)


def create_test_config(**overrides: Any) -> MagicMock:
    """Return a lightweight mock config matching ``solar_platform.config.Settings``.

    Keyword arguments override individual attributes.
    """
    from pathlib import Path

    cfg = MagicMock()
    defaults = {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
        "TOOLKIT_DB": Path("/tmp/test_toolkit.duckdb"),
        "REPORTING_DB": Path("/tmp/test_reporting.duckdb"),
        "JUGGLE_API_KEY": "test-key-000",
        "NOTION_API_KEY": "",
        "JWT_SECRET": "test-jwt-secret-very-long-string-for-testing",
        "LIVE_POLL_INTERVAL": 60,
        "BRAND_COLORS": {
            "primary": "#5FBFA0",
            "secondary": "#4A9E80",
            "accent": "#8FE0C5",
            "positive": "#5FBFA0",
            "negative": "#E66B6B",
            "warning": "#F2C265",
            "surface": "#1E2538",
            "background": "#0B1120",
            "border": "#2B354E",
            "text": "#FFFFFF",
            "text_secondary": "#E0E0E0",
        },
        "is_development": True,
        "is_production": False,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


def random_alerts(
    n: int = 5,
    *,
    seed: int = 42,
    plants: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate *n* alert-like dictionaries for testing.

    Each dict mirrors the shape of ``solar_platform.alerts.models.Alert``.
    """
    rng = random.Random(seed)
    plants = plants or PLANT_NAMES[:3]
    severities = ["critical", "warning", "info"]
    statuses = ["active", "acknowledged", "resolved"]
    rules = ["low_pr", "inverter_offline", "irradiance_mismatch", "high_temp", "clipping"]

    alerts: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for _ in range(n):
        first_seen = now - timedelta(hours=rng.uniform(1, 720))
        alerts.append({
            "id": f"alert-{rng.randint(1000, 9999)}",
            "plant_uid": rng.choice(plants),
            "rule_id": rng.choice(rules),
            "severity": rng.choice(severities),
            "status": rng.choice(statuses),
            "title": f"Test alert {rng.randint(1, 100)}",
            "description": "Auto-generated test alert",
            "metric_value": round(rng.uniform(0, 100), 2),
            "threshold_value": round(rng.uniform(50, 100), 2),
            "first_seen": first_seen.isoformat(),
            "last_seen": (first_seen + timedelta(hours=rng.uniform(0, 48))).isoformat(),
            "occurrence_count": rng.randint(1, 50),
        })
    return alerts


# ══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def large_dataframe() -> pd.DataFrame:
    """10 000-row DataFrame of realistic solar timeseries data.

    Columns: timestamp, plant, device_id, power_kw, irradiance_wm2,
             pr, temperature_c, energy_kwh
    """
    return generate_solar_timeseries(n_rows=10_000, n_plants=5)


@pytest.fixture
def mock_streamlit() -> Generator[MagicMock, None, None]:
    """Comprehensive Streamlit mock injected into ``sys.modules``.

    Patches ``streamlit`` and its commonly used sub-modules so that
    app/page code can be imported and partially exercised without a
    running Streamlit server.
    """
    st_mock = MagicMock(name="streamlit")

    # Core API stubs
    st_mock.cache_data = lambda f=None, **kw: f if f else (lambda fn: fn)
    st_mock.cache_resource = lambda f=None, **kw: f if f else (lambda fn: fn)
    st_mock.experimental_memo = lambda f=None, **kw: f if f else (lambda fn: fn)
    st_mock.experimental_singleton = lambda f=None, **kw: f if f else (lambda fn: fn)

    # session_state behaves like a dict
    st_mock.session_state = {}

    # Sidebar context manager
    st_mock.sidebar = MagicMock()
    st_mock.sidebar.__enter__ = MagicMock(return_value=st_mock.sidebar)
    st_mock.sidebar.__exit__ = MagicMock(return_value=False)

    # columns() returns list of context-manager mocks
    def _make_col() -> MagicMock:
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        return col

    st_mock.columns = lambda *a, **kw: [_make_col() for _ in range(a[0] if a else 2)]

    # tabs() returns list of context-manager mocks
    st_mock.tabs = lambda labels, **kw: [_make_col() for _ in labels]

    # container / expander / form
    for ctx_name in ("container", "expander", "form", "empty", "status"):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        setattr(st_mock, ctx_name, MagicMock(return_value=ctx))

    # Spinner context manager
    spinner = MagicMock()
    spinner.__enter__ = MagicMock(return_value=spinner)
    spinner.__exit__ = MagicMock(return_value=False)
    st_mock.spinner = MagicMock(return_value=spinner)

    # Sub-modules typically imported
    sub_modules = [
        "streamlit",
        "streamlit.components",
        "streamlit.components.v1",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner",
        "streamlit.delta_generator",
    ]
    saved = {}
    for mod_name in sub_modules:
        saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = st_mock if mod_name == "streamlit" else MagicMock()

    yield st_mock

    # Restore original modules
    for mod_name in sub_modules:
        if saved[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = saved[mod_name]


@pytest.fixture
def mock_api_response():
    """Factory fixture for creating mock HTTP responses.

    Usage::

        resp = mock_api_response(json={"data": [1, 2, 3]}, status=200)
        resp = mock_api_response(text="Not found", status=404)
        resp = mock_api_response(raise_for_status=ConnectionError("timeout"))
    """

    def _factory(
        *,
        json: Any = None,
        text: str = "",
        status: int = 200,
        headers: dict[str, str] | None = None,
        raise_for_status: Exception | None = None,
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.ok = 200 <= status < 300
        resp.headers = headers or {"Content-Type": "application/json"}
        resp.text = text or (json is not None and "") or ""
        resp.json.return_value = json if json is not None else {}
        if raise_for_status:
            resp.raise_for_status.side_effect = raise_for_status
        else:
            resp.raise_for_status.return_value = None
        return resp

    return _factory


@pytest.fixture
def mock_duckdb_error():
    """Fixture that patches DuckDB to raise errors on connect / execute.

    Returns a context manager so the caller controls the scope::

        with mock_duckdb_error("connect"):
            engine = DuckDBEngine("/bad/path.duckdb")

        with mock_duckdb_error("execute", error_cls=duckdb.IOException):
            conn.execute("SELECT 1")
    """
    import duckdb as _duckdb

    @contextmanager
    def _factory(
        method: str = "connect",
        *,
        message: str = "Simulated DuckDB error",
        error_cls: type[Exception] | None = None,
    ) -> Generator[None, None, None]:
        exc_class = error_cls or _duckdb.Error
        target = f"duckdb.{method}" if method == "connect" else method
        with patch(target, side_effect=exc_class(message)):
            yield

    return _factory


# ══════════════════════════════════════════════════════════════════════════
#  Timing context manager
# ══════════════════════════════════════════════════════════════════════════

class TimingResult:
    """Stores elapsed time and provides assertion helpers."""

    def __init__(self) -> None:
        self.start: float = 0.0
        self.end: float = 0.0

    @property
    def elapsed(self) -> float:
        return self.end - self.start

    def assert_under(self, max_seconds: float, label: str = "operation") -> None:
        """Raise ``AssertionError`` if elapsed > *max_seconds*."""
        assert self.elapsed <= max_seconds, (
            f"{label} took {self.elapsed:.3f}s, exceeding limit of {max_seconds:.3f}s"
        )

    def assert_over(self, min_seconds: float, label: str = "operation") -> None:
        """Raise ``AssertionError`` if elapsed < *min_seconds*."""
        assert self.elapsed >= min_seconds, (
            f"{label} took {self.elapsed:.3f}s, expected at least {min_seconds:.3f}s"
        )


@contextmanager
def timing_context(label: str = "block") -> Generator[TimingResult, None, None]:
    """Context manager for measuring and optionally asserting execution time.

    Usage::

        with timing_context("DataFrame groupby") as t:
            df.groupby("plant").sum()
        t.assert_under(0.5)
    """
    result = TimingResult()
    result.start = time.perf_counter()
    yield result
    result.end = time.perf_counter()


@pytest.fixture
def timing():
    """Expose ``timing_context`` as a pytest fixture."""
    return timing_context
