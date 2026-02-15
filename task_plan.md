# Task Plan: Solargis Monthly Aggregator + Away Day Deck

## Goal
Ingest the Solargis “67 sites (3)” site list + any new irradiance files from Google Drive into the monthly aggregator DB, and produce an ADE-style Away Day presentation (deck plan + initial slides) grounded in the project context found in Notion.

## Current Phase
Phase 5 (Initial deck delivered)

## Phases

### Phase 1: Requirements & Discovery
- [x] Locate the “67 sites (3)” file in Google Drive (format, columns, latest revision date)
- [x] Identify the Solargis / monthly aggregator DB location + schema
- [x] Identify where irradiance files live (Drive folder(s), naming conventions, file types)
- [x] Identify ADE presentation style source (template deck or brand guidelines) and Away Day project page in Notion
- [ ] Capture findings in `findings.md`
- **Status:** complete

### Phase 2: Ingestion Plan (Drive → Staging → DB)
- [x] Decide ingestion approach (Drive API vs manual download vs local folder sync)
- [x] Define idempotent upsert rules for sites + irradiance rows (keys, dedupe)
- [x] Define “new file” detection (by modified time, checksum, or filename pattern)
- [x] Write a small verification checklist (counts, spot checks)
- **Status:** complete

### Phase 3: Implement + Run DB Updates
- [x] Implement/extend ingestion code to import “67 sites (3)” into the monthly aggregator DB
- [x] Implement/extend ingestion code to import all new irradiance files and attach to sites
- [x] Run ingestion end-to-end locally; record results in `progress.md`
- **Status:** complete

### Phase 4: Notion Research + Slide Outline (ADE Style)
- [x] Find the Away Day presentation project page(s) in Notion
- [x] Extract goals, audience, narrative, key metrics, and current status
- [x] Produce a slide-by-slide outline (headlines, bullets, visuals, speaker notes)
- [x] Confirm ADE style constraints from a template deck or Notion guidelines
- **Status:** complete

### Phase 5: Build Initial Slides + Verify
- [x] Create a deck artifact (prefer `.pptx`) aligned to ADE style
- [x] Generate thumbnails and visually verify layout
- [ ] Summarize what changed (DB + deck) and list next actions/questions
- **Status:** in_progress

## Key Questions
1. Where is the “Solargis / monthly aggregator” DB (SQLite file? Postgres? other) and what are the target tables?
2. What is the authoritative key for a “site” (Solargis site_id? name? lat/lon?) and how should duplicates be handled?
3. How do we detect “new” irradiance files (Drive modified time vs filename month vs checksum)?
4. What does “ADE style” mean operationally (existing PPT template file, brand colors/fonts, layout rules)?
5. What is the Away Day audience + goal (exec update, working session, strategy, training) and desired deck length?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use Google Drive local sync paths as ingestion source | Fastest + avoids Drive API auth plumbing |
| Store “All Sites January.xlsx” into DuckDB `solar_data` keyed by (Site, Date) | Matches existing monthly aggregator table + safe upserts |
| Persist SolarGIS aggregates into DuckDB `solargis_monthly` | Speeds Notion sync/reporting + makes refresh explicit |
| Build Away Day deck by duplicating a “content layout” slide from ADE template | Keeps ADE style without re-creating theme/layout from scratch |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Notion sync output redirected to file showed empty while running | 1 | Process still running; output appeared on completion |
| `pptx` tooling missing deps (`PIL`, `python-pptx`) | 1 | Installed into repo `.venv` via pip |
