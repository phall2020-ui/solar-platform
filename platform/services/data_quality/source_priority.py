"""Source priority management for multi-source solar data.

Defines a global priority ranking for data sources and a per-plant override
mechanism.  Higher numbers indicate higher trust / priority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("data_quality.source_priority")


# Global default priorities (higher = more trusted).
SOURCE_PRIORITY: dict[str, int] = {
    "scada": 10,
    "monitoring_portal": 9,
    "api": 8,
    "inverter": 8,
    "meter": 9,
    "satellite": 5,
    "manual": 4,
    "estimated": 2,
    "interpolated": 3,
    "gap_detector": 1,
    "unknown": 1,
}


def pick_best_source(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the candidate dict with the highest source priority.

    Each candidate must have a ``"source"`` key.  Ties are broken by
    choosing the first one encountered.

    Returns ``None`` if *candidates* is empty.
    """
    if not candidates:
        return None

    def _key(c: dict[str, Any]) -> int:
        src = str(c.get("source", "unknown")).lower()
        return SOURCE_PRIORITY.get(src, 0)

    return max(candidates, key=_key)


@dataclass
class SourcePriorityManager:
    """Manage source priorities with optional per-plant overrides.

    Usage::

        mgr = SourcePriorityManager()
        mgr.set_override("PLANT-001", {"satellite": 7, "scada": 10})
        best = mgr.pick_best("PLANT-001", candidates)
    """

    overrides: dict[str, dict[str, int]] = field(default_factory=dict)

    def get_priority(self, plant_uid: str, source: str) -> int:
        """Return the effective priority for *source* at *plant_uid*."""
        source_lower = source.lower()
        plant_overrides = self.overrides.get(plant_uid, {})
        if source_lower in plant_overrides:
            return plant_overrides[source_lower]
        return SOURCE_PRIORITY.get(source_lower, 0)

    def set_override(self, plant_uid: str, priorities: dict[str, int]) -> None:
        """Set per-plant source priority overrides."""
        self.overrides[plant_uid] = {k.lower(): v for k, v in priorities.items()}
        logger.info("source_priority_override_set", plant_uid=plant_uid, overrides=priorities)

    def clear_override(self, plant_uid: str) -> None:
        """Remove any overrides for *plant_uid*."""
        self.overrides.pop(plant_uid, None)

    def pick_best(
        self,
        plant_uid: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Pick the best candidate considering per-plant overrides."""
        if not candidates:
            return None

        def _key(c: dict[str, Any]) -> int:
            src = str(c.get("source", "unknown")).lower()
            return self.get_priority(plant_uid, src)

        return max(candidates, key=_key)

    def rank_sources(self, plant_uid: str) -> list[tuple[str, int]]:
        """Return all known sources ranked by priority (descending) for a plant."""
        merged = dict(SOURCE_PRIORITY)
        merged.update(self.overrides.get(plant_uid, {}))
        return sorted(merged.items(), key=lambda kv: kv[1], reverse=True)
