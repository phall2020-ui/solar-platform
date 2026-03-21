# solar-platform — Actions

**Status:** Active primary platform. Branch `codex/copilot-triage-publish-run` is ahead of `main` with unmerged feature work.

## Remaining / in-progress

- [ ] Merge branch `codex/copilot-triage-publish-run` into `main` once tested
- [ ] Fix `Monthly Email Queue` — fails if triggered manually without `MONTHLY_EMAIL_RECIPIENTS` input
- [ ] Complete Morpheus site onboarding (Benelux/Iberia/UK sites post-acquisition)
- [ ] Add Holcim (Obourg) 31.15 MWp floating solar to site config once PAC issued
- [ ] Verify all 45+ portfolio sites are mapped in `tools/geocode_sites.py` with correct `juggle_uid`

## Suggested actions

- [ ] Add `requirements.txt` / `pyproject.toml` to top-level for consistent dependency management across jobs and tools
- [ ] Add Juggle API client to `tools/inverter-data-juggle/` to supplement SolarEdge and Solis
- [ ] Implement PR performance vs irradiance baseline in `copilot_audit.py`
- [ ] Add Metris billing data ingestion once portal access is confirmed
- [ ] Set up monitoring for GitHub Actions failures — currently no alerting if daily sync workflow fails
- [ ] Write a `CONTRIBUTING.md` or `DEVELOPMENT.md` covering the multi-component architecture
- [ ] Add `.env.example` at repo root documenting all required secrets
- [ ] Archive or remove the `platform/reports/away_day_2026/` one-off scripts from the main codebase
