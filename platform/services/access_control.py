"""Granular access-control service.

Manages per-user plant access and feature-level permissions via DuckDB tables.
The helper :func:`get_current_permissions` integrates with Streamlit session
state when available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from services.database.engine import DuckDBEngine, get_engine

logger = structlog.get_logger("services.access_control")

_CREATE_PLANT_ACCESS_TABLE = """
CREATE TABLE IF NOT EXISTS user_plant_access (
    user_id     VARCHAR NOT NULL,
    plant_uid   VARCHAR NOT NULL,
    granted_by  VARCHAR,
    granted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, plant_uid)
)
"""

_CREATE_FEATURE_ACCESS_TABLE = """
CREATE TABLE IF NOT EXISTS user_feature_access (
    user_id     VARCHAR NOT NULL,
    feature     VARCHAR NOT NULL,
    granted_by  VARCHAR,
    granted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, feature)
)
"""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
@dataclass
class UserPermissions:
    """Resolved permission set for a single user."""

    user_id: str
    is_admin: bool = False
    accessible_plant_uids: list[str] = field(default_factory=list)
    accessible_features: list[str] = field(default_factory=list)

    def has_plant_access(self, plant_uid: str) -> bool:
        """Check whether the user may access *plant_uid*."""
        if self.is_admin:
            return True
        return plant_uid in self.accessible_plant_uids

    def filter_plants(self, plant_uids: list[str]) -> list[str]:
        """Return only those *plant_uids* the user may access."""
        if self.is_admin:
            return list(plant_uids)
        allowed = set(self.accessible_plant_uids)
        return [uid for uid in plant_uids if uid in allowed]

    def has_feature_access(self, feature: str) -> bool:
        """Check whether the user may use *feature*."""
        if self.is_admin:
            return True
        return feature in self.accessible_features


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class AccessControlService:
    """Manage user-level permissions stored in DuckDB."""

    def __init__(self, engine: DuckDBEngine | None = None):
        self.engine = engine or get_engine()
        self._ensure_tables()

    # ---- query -----------------------------------------------------------

    def get_permissions(self, user_id: str) -> UserPermissions:
        """Build the full permission set for *user_id*."""
        plant_uids = self._get_plant_access(user_id)
        features = self._get_feature_access(user_id)

        is_admin = "admin" in features

        return UserPermissions(
            user_id=user_id,
            is_admin=is_admin,
            accessible_plant_uids=plant_uids,
            accessible_features=features,
        )

    # ---- plant access ----------------------------------------------------

    def grant_plant_access(
        self,
        user_id: str,
        plant_uid: str,
        granted_by: str | None = None,
    ) -> None:
        """Grant *user_id* access to *plant_uid*."""
        data: dict[str, Any] = {
            "user_id": user_id,
            "plant_uid": plant_uid,
            "granted_by": granted_by,
            "granted_at": datetime.now(UTC),
        }
        self.engine.execute_upsert("user_plant_access", data, ["user_id", "plant_uid"])
        logger.info(
            "plant_access_granted",
            user_id=user_id,
            plant_uid=plant_uid,
            granted_by=granted_by,
        )

    def revoke_plant_access(self, user_id: str, plant_uid: str) -> None:
        """Revoke *user_id* access to *plant_uid*."""
        self.engine.execute(
            "DELETE FROM user_plant_access WHERE user_id = ? AND plant_uid = ?",
            (user_id, plant_uid),
        )
        logger.info("plant_access_revoked", user_id=user_id, plant_uid=plant_uid)

    # ---- feature access --------------------------------------------------

    def grant_feature_access(
        self,
        user_id: str,
        feature: str,
        granted_by: str | None = None,
    ) -> None:
        """Grant *user_id* access to *feature*."""
        data: dict[str, Any] = {
            "user_id": user_id,
            "feature": feature,
            "granted_by": granted_by,
            "granted_at": datetime.now(UTC),
        }
        self.engine.execute_upsert("user_feature_access", data, ["user_id", "feature"])
        logger.info("feature_access_granted", user_id=user_id, feature=feature)

    def revoke_feature_access(self, user_id: str, feature: str) -> None:
        """Revoke *user_id* access to *feature*."""
        self.engine.execute(
            "DELETE FROM user_feature_access WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        )
        logger.info("feature_access_revoked", user_id=user_id, feature=feature)

    # ---- internal --------------------------------------------------------

    def _get_plant_access(self, user_id: str) -> list[str]:
        rows = self.engine.execute(
            "SELECT plant_uid FROM user_plant_access WHERE user_id = ? ORDER BY plant_uid",
            (user_id,),
        )
        return [r[0] for r in rows]

    def _get_feature_access(self, user_id: str) -> list[str]:
        rows = self.engine.execute(
            "SELECT feature FROM user_feature_access WHERE user_id = ? ORDER BY feature",
            (user_id,),
        )
        return [r[0] for r in rows]

    def _ensure_tables(self) -> None:
        if not self.engine.table_exists("user_plant_access"):
            self.engine.execute(_CREATE_PLANT_ACCESS_TABLE)
            logger.info("table_created", table="user_plant_access")
        if not self.engine.table_exists("user_feature_access"):
            self.engine.execute(_CREATE_FEATURE_ACCESS_TABLE)
            logger.info("table_created", table="user_feature_access")


# ---------------------------------------------------------------------------
# Streamlit helper
# ---------------------------------------------------------------------------
def get_current_permissions() -> UserPermissions | None:
    """Read permissions from ``st.session_state`` if Streamlit is available.

    Returns ``None`` when Streamlit is not installed or no user is logged in.
    """
    try:
        import streamlit as st  # type: ignore[import-untyped]
    except ImportError:
        return None

    user_id = st.session_state.get("user_id") or st.session_state.get("username")
    if not user_id:
        return None

    # Cache in session state to avoid repeated DB calls
    cache_key = f"_acl_permissions_{user_id}"
    cached = st.session_state.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    svc = AccessControlService()
    perms = svc.get_permissions(str(user_id))
    st.session_state[cache_key] = perms
    return perms
