# solar-platform — Context

**Status:** Active (primary platform)
**Branch:** `codex/copilot-triage-publish-run` (ahead of main — feature work in progress)
**Last updated:** 2026-03-15

## Purpose
Core solar asset management platform. Ingests inverter data from Juggle, SolarEdge, Solis APIs; syncs to Notion; runs AI copilot audits; sends monthly email reports.

## Key Entry Points
| Script | Purpose |
|--------|---------|
| `tools/inverter-data-juggle/notion_sync.py` | Main daily sync — run by GitHub Actions |
| `tools/inverter-data-juggle/copilot_audit.py` | AI performance audit |
| `jobs/inverter-daily-checks/inverter_monitor.py` | Local daemon entry point |

## GitHub Actions (all on `main`, all passing)
| Workflow | Schedule | Purpose |
|----------|----------|---------|
| Daily Notion Pull | 04:00 UK | Sync inverter data to Notion |
| Inverter Monitor | Hourly | Health checks |
| Site Onboarding to O&M Sync | On push | New site setup |
| Weekly Email Queue | Monday | Weekly summary email |
| Monthly Email Queue | Triggered by Daily Notion Pull on 1st | Monthly investor report |
| Copilot Asset Audit | Schedule only (no dispatch) | AI portfolio audit |

## Secrets Required
All stored in GitHub repo secrets:
`JUGGLE_API_KEY`, `NOTION_TOKEN`, `NOTION_PAGE_ID`, `SOLAREDGE_KEYS_JSON`,
`SOLIS_API_URL`, `SOLIS_KEY_ID`, `SOLIS_KEY_SECRET`,
`SYNC_SMTP_*`, `SYNC_EMAIL_*`, `MONTHLY_EMAIL_RECIPIENTS`

## Architecture
```
tools/inverter-data-juggle/   Main sync and audit logic
jobs/                         Background job runners
platform/                     Shared models and services
api/                          REST API layer
app/                          Web frontend
cli/                          Command line interface
```

## Known Issues
- Branch `codex/copilot-triage-publish-run` is not yet merged to `main`
- Monthly Email Queue requires `MONTHLY_EMAIL_RECIPIENTS` secret — fails if triggered manually without input
