# Contributing to Solar-Platform

Welcome! This document outlines the architecture and contribution guidelines for the `solar-platform` project.

## Architecture Overview

The `solar-platform` is a multi-component asset management platform designed to ingest, audit, and report on solar plant performance.

### Core Components

1.  **Notion Sync (`tools/inverter-data-juggle/`)**:
    *   `notion_sync.py`: The primary engine for daily data synchronization to Notion.
    *   `juggle_api.py`, `solis_api.py`, `solaredge_api.py`: API clients for respective monitoring platforms.
    *   `sites_mapping.json`: Configuration mapping sites across different platforms.

2.  **AI Audits (`tools/inverter-data-juggle/copilot_audit.py`)**:
    *   Runs performance audits against benchmark data using LLM-based logic.
    *   Triages and publishes findings to Notion.

3.  **Reporting Jobs (`jobs/`)**:
    *   `inverter-daily-checks`: Background jobs for health monitoring and alerts.

4.  **GitHub Actions**:
    *   Automated workflows for daily syncs, weekly/monthly reporting, and AI audits.

## Development Setup

1.  **Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r tools/inverter-data-juggle/requirements.txt
    ```

2.  **Configuration**:
    Copy `.env.example` to `.env` and fill in the required secrets (Notion, Juggle, Solis, etc.).

3.  **Testing**:
    Run smoke tests to verify the environment:
    ```bash
    pytest tests/test_smoke.py
    ```

## Adding New Sites

1.  Update `tools/inverter-data-juggle/sites_mapping.json`.
2.  If the site is on a new platform, implement a corresponding API client in `tools/inverter-data-juggle/`.
3.  Ensure the `Platform` select field in the Notion database includes the new platform name.

## Branching Strategy

*   `main`: Stable production code.
*   `feature/*`: New features and platform integrations.
*   `fix/*`: Bug fixes.
*   `codex/*`: AI-assisted experiments and triage logic.

Please ensure all PRs pass the existing test suite before merging.
