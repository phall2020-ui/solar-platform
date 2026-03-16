# Solar Copilot Operations Triage Plan

> Research input synthesized from a parallel agent focused on analyst-facing solar operations copilots.

## Goal
Build the next copilot iteration as an internal operations triage assistant that turns daily telemetry, asset metadata, and source-health checks into ranked issues, evidence packs, and concise recommended actions for analysts.

## Product Shape
- Audience: internal solar operations analysts, not customers.
- Core loop: ingest telemetry and source health, detect issues, assemble evidence, draft AI recommendations, route for analyst review.
- Safety model: human-in-the-loop by default; autonomous actions are out of scope for this phase.
- Delivery model: write curated triage outputs into a separate Notion database so AI can draft AM-ready emails using asset-register context.

## Milestone 1: Data Health And Asset Context
- Inputs: Notion asset metadata, Juggle and inverter-source telemetry, commissioning dates, site capacity, platform mappings, weather context where available.
- Outputs: unified asset context, recent telemetry snapshot, data-presence score, stale-data flag, missing-source flag.
- Decision rules:
  - mark `missing_data` when no readings exist for the target day
  - mark `stale_data` when latest reading lags the expected cadence materially
  - suppress production-performance claims when data quality is insufficient
- Acceptance:
  - every audited asset has a deterministic data-health classification
  - source coverage is visible per asset and per source
  - Notion metadata and external IDs are cached and reproducible

## Milestone 2: Daily Detection Engine
- Inputs: yesterday dataset, trailing 7-day window, expected generation context, peer/sibling comparisons where available.
- Outputs: issue types for `no_data`, `stale_data`, `underperformance`, `curtailment_candidate`, and `source_conflict`.
- Decision rules:
  - underperformance only triggers when expected-vs-actual gap persists and source quality is adequate
  - curtailment candidates require production suppression during good irradiance or similar evidence
  - unresolved mappings degrade confidence and are surfaced explicitly
- Acceptance:
  - each issue has severity, confidence, affected source set, and quantified impact where possible
  - issue generation is deterministic for the same input dataset

## Milestone 3: Evidence Pack And AI Summary
- Inputs: issue records, recent telemetry, weather overlays, historical comparisons, prior match/mapping metadata.
- Outputs: evidence pack per asset with summary facts, charts/table-ready values, likely root cause hints, and next action recommendation.
- Decision rules:
  - every AI summary must cite structured evidence fields from the pack
  - if evidence is incomplete, the summary must say that directly and lower confidence
  - recommendations must stay analyst-facing: inspect, verify, escalate, or dispatch
- Acceptance:
  - analysts can review one issue in under two minutes
  - every summary includes confidence, reason, and recommended next step

## Milestone 4: Notion Triage Database And AM Email Drafting
- Inputs: evidence packs, asset-register metadata, AM ownership fields, portfolio/grouping fields, commercial-priority fields, and site/customer labels from the asset register.
- Outputs: one row per asset/day/issue in a new Notion triage database with structured fields plus an AI-written AM-facing draft email.
- Decision rules:
  - keep the asset register as system-of-record metadata and write copilot outputs to a separate Notion database
  - each triage row must include asset reference, target date, issue type, severity, confidence, source coverage, evidence summary, recommended action, and email draft
  - email drafts must use the AM and customer-facing fields already present in the asset register where available
  - drafts are review-first in v1 and are not sent automatically
  - generated prose must always be traceable back to structured evidence stored on the same Notion row
- Acceptance:
  - every actionable issue can be pushed into the triage database with a deterministic schema
  - AM draft emails are concise, asset-specific, and grounded in the stored evidence pack
  - analysts can edit or approve drafts without losing the underlying structured fields

## Milestone 5: Feedback And Learning Loop
- Inputs: analyst corrections, confirmed fault outcomes, updated Notion mappings, workflow execution history.
- Outputs: corrected labels, mapping refinements, prompt improvements, and benchmark cases for regression testing.
- Decision rules:
  - analyst overrides become structured feedback, not free-text only
  - newly confirmed site mappings update the canonical `Data Source Match` field
  - prompt or classifier changes require regression checks against known cases
- Acceptance:
  - the copilot improves from analyst feedback without changing raw historical evidence
  - known issue examples remain reproducible as test fixtures

## Recommended Metrics
- data availability by source and asset
- issue precision by type
- analyst agreement rate with AI summaries
- percent of triage issues successfully written to the Notion output database
- percent of AM drafts approved with minor or no edits
- time from audit completion to analyst disposition
- percent of issues with quantified energy impact
- percent of issues blocked by missing metadata or credentials

## Immediate Build Sequence
1. Stabilize mapping resolution and source-health auditing.
2. Add trailing-window telemetry fetches and deterministic issue classification.
3. Build evidence-pack serialization as a first-class output.
4. Add the separate Notion triage database schema and write path.
5. Layer AI summaries and AM email drafts on top of the evidence pack with strict confidence handling.
6. Capture analyst feedback and convert it into regression fixtures.
