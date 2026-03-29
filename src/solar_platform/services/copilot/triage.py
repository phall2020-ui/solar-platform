"""Triage issue assessment and AM email draft generation."""

from __future__ import annotations

import os
from typing import Any

from solar_platform.services.copilot.mapping import _build_evidence_summary
from solar_platform.services.copilot.models import SUPPORTED_SOURCES, TriageAssessment


def _assess_triage_issue(row: dict[str, Any]) -> TriageAssessment:
    checked_sources = [source for source in str(row.get("checked_sources", "")).split(",") if source]
    statuses = {source: row.get(f"{source}_status", "") for source in SUPPORTED_SOURCES}
    error_sources = sorted(source for source, status in statuses.items() if status == "error")
    missing_identifier_sources = sorted(
        source for source, status in statuses.items() if status == "missing_identifier"
    )
    unconfigured_sources = sorted(
        source for source in checked_sources if statuses.get(source) == "unconfigured"
    )

    if row.get("match_method") == "unresolved":
        return TriageAssessment(
            issue_type="mapping_unresolved",
            severity="medium",
            confidence=0.95,
            recommended_action="Confirm the external monitoring site name and update Data Source Match in the asset register.",
            issue_summary="No canonical mapping is available, so the audit could not resolve an external data source.",
        )
    if error_sources:
        joined = ", ".join(error_sources)
        return TriageAssessment(
            issue_type="source_error",
            severity="high",
            confidence=0.85,
            recommended_action=f"Check the {joined} API response and credentials, then rerun the audit.",
            issue_summary=f"The audit hit API errors while checking {joined}.",
        )
    if unconfigured_sources and not row.get("has_any_data"):
        joined = ", ".join(unconfigured_sources)
        return TriageAssessment(
            issue_type="source_unconfigured",
            severity="medium",
            confidence=0.8,
            recommended_action=f"Configure credentials for {joined} in the local environment or GitHub Actions and rerun the audit.",
            issue_summary=f"The mapped source {joined} could not be checked because credentials are missing.",
        )
    if missing_identifier_sources and not row.get("has_any_data"):
        joined = ", ".join(missing_identifier_sources)
        return TriageAssessment(
            issue_type="missing_identifier",
            severity="medium",
            confidence=0.8,
            recommended_action=f"Add the missing external identifier for {joined} or confirm the Data Source Match mapping.",
            issue_summary=f"The audit knows which source to query but does not have identifiers for {joined}.",
        )
    if not row.get("has_any_data"):
        return TriageAssessment(
            issue_type="no_data",
            severity="high",
            confidence=0.7,
            recommended_action="Review telemetry availability, site communications, and inverter portal data for the target day.",
            issue_summary="The audit found no source data for the target day despite a resolved mapping.",
        )
    return TriageAssessment(
        issue_type="healthy_data_present",
        severity="info",
        confidence=0.9,
        recommended_action="No immediate action required.",
        issue_summary="At least one source reported data for the target day.",
    )


def _build_email_subject(asset_name: str, issue_type: str, target_date: str) -> str:
    return f"{asset_name}: {issue_type} for {target_date}"


def _build_email_draft(
    *,
    asset_name: str,
    target_date: str,
    assessment: TriageAssessment,
    context: dict[str, str],
    row: dict[str, Any],
) -> str:
    fallback = _build_fallback_email_draft(
        asset_name=asset_name,
        target_date=target_date,
        assessment=assessment,
        context=context,
        row=row,
    )
    api_key = str(os.getenv("ANTHROPIC_API_KEY", "")).strip()
    if not api_key:
        return fallback

    try:
        import anthropic
        from solar_platform.services.copilot.model_router import select_model

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Write a concise internal asset-manager email draft. "
            "Keep it factual, specific, and grounded only in the provided evidence. "
            "Do not invent telemetry or causes. Mention uncertainty explicitly when needed.\n\n"
            f"Asset: {asset_name}\n"
            f"Project: {context.get('project_name', '')}\n"
            f"Customer: {context.get('customer_name', '')}\n"
            f"SPV: {context.get('spv', '')}\n"
            f"Priority: {context.get('priority', '')}\n"
            f"Target date: {target_date}\n"
            f"Issue type: {assessment.issue_type}\n"
            f"Severity: {assessment.severity}\n"
            f"Confidence: {assessment.confidence:.2f}\n"
            f"Evidence summary: {_build_evidence_summary(row, context)}\n"
            f"Recommended action: {assessment.recommended_action}\n"
        )
        message = client.messages.create(
            model=select_model("draft_email"),
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text if message.content else ""
        return str(content).strip() or fallback
    except Exception:
        return fallback


def _build_fallback_email_draft(
    *,
    asset_name: str,
    target_date: str,
    assessment: TriageAssessment,
    context: dict[str, str],
    row: dict[str, Any],
) -> str:
    contact = context.get("am_contact_name") or "team"
    project_name = context.get("project_name") or asset_name
    customer = context.get("customer_name") or "the customer"
    source_coverage = row.get("checked_sources", "no sources")
    preferred_source = row.get("preferred_source", "") or "none"
    return (
        f"Hi {contact},\n\n"
        f"The solar copilot triage for {project_name} ({customer}) flagged a {assessment.issue_type} issue for "
        f"{target_date}.\n\n"
        f"Summary: {assessment.issue_summary}\n"
        f"Evidence: {row.get('resolution_notes', '') or 'The current mapping and source audit were used.'}\n"
        f"Sources checked: {source_coverage}. Preferred source with data: {preferred_source}.\n\n"
        f"Recommended action: {assessment.recommended_action}\n\n"
        f"Regards,\nSolar Copilot"
    )


def _severity_sort_key(value: Any) -> int:
    from solar_platform.services.copilot.models import SEVERITY_RANK
    return SEVERITY_RANK.get(str(value or "").strip().casefold(), -1)
