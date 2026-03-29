"""
Model router for copilot AI features.

Chooses between Claude Haiku (fast, cheap) and Claude Sonnet (complex reasoning)
based on the task type.

Usage:
    from solar_platform.services.copilot.model_router import select_model

    model = select_model("draft_email")      # → HAIKU
    model = select_model("diagnose_issue")   # → SONNET
"""

# Model IDs
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# Tasks handled by Haiku — simple classification, extraction, or short text generation
_SIMPLE_TASKS: frozenset[str] = frozenset({
    "classify_alert",
    "extract_field",
    "short_summary",
    "triage_severity",
    "draft_email",         # Short, templated email drafts
    "format_output",
})


def select_model(task: str) -> str:
    """
    Return the appropriate Claude model ID for a given task name.

    Args:
        task: A short task key (see _SIMPLE_TASKS for Haiku-eligible tasks).
              Any unrecognised or complex task defaults to Sonnet.

    Returns:
        A Claude model ID string suitable for use with the Anthropic SDK.
    """
    return HAIKU if task in _SIMPLE_TASKS else SONNET
