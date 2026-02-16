#!/usr/bin/env python3
"""
Comprehensive test-suite runner for the Solar Platform.

Usage:
    python tests/test_suite_runner.py               # Run all categories
    python tests/test_suite_runner.py --quick        # Skip performance tests
    python tests/test_suite_runner.py --category ui  # Run only UI tests
    python tests/test_suite_runner.py --category compile,resilience

Categories:
    compile      – Compilation & import verification
    performance  – Speed and memory benchmarks
    ui           – UI error detection & page safety
    resilience   – Error-handling across all layers

Generates a JSON report at tests/reports/test_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── Colour helpers (gracefully degrade when piped) ──────────────────────
NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")

_RESET = "" if NO_COLOR else "\033[0m"
_BOLD = "" if NO_COLOR else "\033[1m"
_GREEN = "" if NO_COLOR else "\033[32m"
_RED = "" if NO_COLOR else "\033[31m"
_YELLOW = "" if NO_COLOR else "\033[33m"
_CYAN = "" if NO_COLOR else "\033[36m"
_DIM = "" if NO_COLOR else "\033[2m"


def _ok(msg: str) -> str:
    return f"{_GREEN}✓{_RESET} {msg}"


def _fail(msg: str) -> str:
    return f"{_RED}✗{_RESET} {msg}"


def _warn(msg: str) -> str:
    return f"{_YELLOW}⚠{_RESET} {msg}"


def _heading(msg: str) -> str:
    return f"\n{_BOLD}{_CYAN}{'─' * 60}\n  {msg}\n{'─' * 60}{_RESET}"


# ── Data structures ────────────────────────────────────────────────────
@dataclass
class CategoryResult:
    name: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_s: float = 0.0
    exit_code: int = 0
    output: str = ""
    error_details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


# ── Category definitions ───────────────────────────────────────────────
CATEGORIES: dict[str, dict] = {
    "compile": {
        "label": "Compilation & Import Verification",
        "markers": "compile",
        "test_files": ["tests/test_compile_and_imports.py"],
        "pytest_args": ["-x"],  # fail-fast on first compile error
    },
    "performance": {
        "label": "Speed & Memory Benchmarks",
        "markers": "performance",
        "test_files": ["tests/test_performance.py"],
        "pytest_args": [],
    },
    "ui": {
        "label": "UI Error Detection & Page Safety",
        "markers": "ui",
        "test_files": ["tests/test_ui_errors.py"],
        "pytest_args": [],
    },
    "resilience": {
        "label": "Error Resilience & Handling",
        "markers": "resilience",
        "test_files": ["tests/test_error_resilience.py"],
        "pytest_args": [],
    },
}


def _resolve_root() -> Path:
    """Return the project root (parent of ``tests/``)."""
    here = Path(__file__).resolve().parent
    return here.parent


def _parse_pytest_short_summary(output: str) -> dict:
    """Extract counts from the pytest short-test-summary line.

    Examples of the final status line pytest emits:
        ``= 12 passed, 1 failed, 2 skipped in 3.45s =``
        ``= 5 passed in 0.82s =``
    """
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for line in reversed(output.splitlines()):
        line = line.strip().strip("=").strip()
        if not line:
            continue
        # Look for the summary line with timing
        if " in " in line and any(k in line for k in ("passed", "failed", "error")):
            for token in ("passed", "failed", "error", "skipped", "warning"):
                # Match patterns like "12 passed"
                import re

                m = re.search(rf"(\d+)\s+{token}", line)
                if m:
                    key = "errors" if token == "error" else token
                    if key == "warning":
                        continue
                    counts[key] = int(m.group(1))
            break
    return counts


def _collect_failure_lines(output: str) -> list[str]:
    """Grab FAILED/ERROR lines for the report."""
    details: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
            details.append(stripped)
    return details


def run_category(
    name: str,
    root: Path,
    python: str,
) -> CategoryResult:
    """Execute pytest for one test category and return a ``CategoryResult``."""
    cat = CATEGORIES[name]
    result = CategoryResult(name=name)

    # Build the pytest command
    cmd = [
        python,
        "-m",
        "pytest",
        "--tb=short",
        "-q",
        "--no-header",
    ]

    # If test files exist on disk, use them directly; else fall back to marker
    test_files = [str(root / f) for f in cat["test_files"] if (root / f).exists()]
    if test_files:
        cmd.extend(test_files)
    else:
        # Fallback: run marker-based selection across entire test tree
        cmd.extend(["-m", cat["markers"], str(root / "tests")])

    cmd.extend(cat.get("pytest_args", []))

    print(f"  {_DIM}$ {' '.join(cmd)}{_RESET}")

    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    elapsed = time.monotonic() - t0

    combined_output = proc.stdout + proc.stderr
    counts = _parse_pytest_short_summary(combined_output)

    result.passed = counts["passed"]
    result.failed = counts["failed"]
    result.errors = counts["errors"]
    result.skipped = counts["skipped"]
    result.duration_s = round(elapsed, 2)
    result.exit_code = proc.returncode
    result.output = combined_output
    result.error_details = _collect_failure_lines(combined_output)

    return result


# ── Summary rendering ──────────────────────────────────────────────────
def _print_summary(results: list[CategoryResult], total_time: float) -> None:
    print(_heading("Test Suite Summary"))

    max_label = max(len(CATEGORIES[r.name]["label"]) for r in results)

    for r in results:
        label = CATEGORIES[r.name]["label"].ljust(max_label)
        status = _ok("PASS") if r.ok else _fail("FAIL")
        timing = f"{_DIM}{r.duration_s:6.2f}s{_RESET}"
        counts_str = (
            f"{_GREEN}{r.passed} passed{_RESET}"
            + (f"  {_RED}{r.failed} failed{_RESET}" if r.failed else "")
            + (f"  {_RED}{r.errors} errors{_RESET}" if r.errors else "")
            + (f"  {_YELLOW}{r.skipped} skipped{_RESET}" if r.skipped else "")
        )
        print(f"  {status}  {label}  {timing}  {counts_str}")
        for detail in r.error_details[:5]:
            print(f"        {_RED}{detail}{_RESET}")

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_errors = sum(r.errors for r in results)
    total_skipped = sum(r.skipped for r in results)

    print(f"\n  {_BOLD}Totals{_RESET}: "
          f"{total_passed} passed, {total_failed} failed, "
          f"{total_errors} errors, {total_skipped} skipped")
    print(f"  {_BOLD}Wall time{_RESET}: {total_time:.2f}s\n")


def _write_json_report(
    results: list[CategoryResult],
    total_time: float,
    report_dir: Path,
) -> Path:
    """Persist results as JSON for CI or downstream tooling."""
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "test_results.json"

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_wall_time_s": round(total_time, 2),
        "overall_pass": all(r.ok for r in results),
        "categories": {
            r.name: {
                "label": CATEGORIES[r.name]["label"],
                "passed": r.passed,
                "failed": r.failed,
                "errors": r.errors,
                "skipped": r.skipped,
                "total": r.total,
                "duration_s": r.duration_s,
                "exit_code": r.exit_code,
                "error_details": r.error_details,
            }
            for r in results
        },
    }

    report_path.write_text(json.dumps(payload, indent=2) + "\n")
    return report_path


# ── CLI entrypoint ──────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Solar Platform – comprehensive test-suite runner",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip performance tests for faster feedback.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help=(
            "Comma-separated list of categories to run "
            f"(choices: {', '.join(CATEGORIES)}). Default: all."
        ),
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="Python interpreter to use (default: current interpreter).",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Directory for the JSON report (default: tests/reports/).",
    )
    args = parser.parse_args(argv)

    root = _resolve_root()

    # Determine which categories to run
    if args.category:
        requested = [c.strip() for c in args.category.split(",")]
        unknown = [c for c in requested if c not in CATEGORIES]
        if unknown:
            print(_fail(f"Unknown categories: {', '.join(unknown)}"))
            print(f"  Available: {', '.join(CATEGORIES)}")
            return 2
        run_order = requested
    else:
        run_order = list(CATEGORIES)

    if args.quick and "performance" in run_order:
        run_order.remove("performance")
        print(_warn("Skipping performance tests (--quick)"))

    if not run_order:
        print(_warn("No categories selected – nothing to run."))
        return 0

    # Resolve report directory
    report_dir = Path(args.report_dir) if args.report_dir else root / "tests" / "reports"

    # ── Run each category ───────────────────────────────────────────
    results: list[CategoryResult] = []
    t_start = time.monotonic()

    for cat_name in run_order:
        print(_heading(CATEGORIES[cat_name]["label"]))
        result = run_category(cat_name, root, python=args.python)
        results.append(result)

        if result.ok:
            print(f"  {_ok(f'{result.passed} passed in {result.duration_s:.2f}s')}")
        else:
            print(f"  {_fail(f'{result.failed + result.errors} failures in {result.duration_s:.2f}s')}")

    total_time = time.monotonic() - t_start

    # ── Summary & report ────────────────────────────────────────────
    _print_summary(results, total_time)

    report_path = _write_json_report(results, total_time, report_dir)
    print(f"  {_DIM}Report written to {report_path}{_RESET}\n")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
