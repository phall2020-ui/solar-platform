"""Tests for the AuthService — password hashing, verification, and rate limiting.

All database interactions are mocked so no real SQLite files are created.
"""
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import bcrypt
import pytest


# ---------------------------------------------------------------------------
# Helpers to build an AuthService without touching the filesystem / DB
# ---------------------------------------------------------------------------

def _make_auth_service(tmp_path: Path):
    """Create an AuthService with DB init mocked out."""
    with patch("services.auth_service.st"):  # prevent streamlit import side-effects
        from solar_platform.services.auth import AuthService

        with patch.object(AuthService, "_init_database"), \
             patch.object(AuthService, "_create_default_admin"):
            svc = AuthService(db_path=tmp_path / "users.db")
    return svc


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestHashPassword:
    """Tests for AuthService._hash_password()."""

    def test_returns_bcrypt_hash(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        hashed = svc._hash_password("my_secret")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_different_passwords_produce_different_hashes(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        h1 = svc._hash_password("password_one")
        h2 = svc._hash_password("password_two")
        assert h1 != h2

    def test_same_password_produces_different_hashes_due_to_salt(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        h1 = svc._hash_password("same_pw")
        h2 = svc._hash_password("same_pw")
        assert h1 != h2  # bcrypt uses random salt


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------

class TestVerifyPassword:
    """Tests for AuthService._verify_password()."""

    def test_correct_password_returns_true(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        hashed = svc._hash_password("correct_pw")
        assert svc._verify_password("correct_pw", hashed) is True

    def test_wrong_password_returns_false(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        hashed = svc._hash_password("correct_pw")
        assert svc._verify_password("wrong_pw", hashed) is False

    def test_legacy_sha256_hash_is_accepted(self, tmp_path):
        """Backward compat: SHA-256 hex digest should verify correctly."""
        svc = _make_auth_service(tmp_path)
        password = "legacy_password"
        sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        assert svc._verify_password(password, sha256_hash) is True

    def test_legacy_sha256_wrong_password_returns_false(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        sha256_hash = hashlib.sha256(b"original").hexdigest()
        assert svc._verify_password("not_original", sha256_hash) is False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestCheckRateLimit:
    """Tests for AuthService._check_rate_limit()."""

    def test_allows_first_attempt(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        assert svc._check_rate_limit("alice") is True

    def test_allows_attempts_under_limit(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        # Record MAX_FAILED_ATTEMPTS - 1 failures
        for _ in range(svc.MAX_FAILED_ATTEMPTS - 1):
            svc._record_failed_attempt("bob")
        assert svc._check_rate_limit("bob") is True

    def test_blocks_after_max_failed_attempts(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        for _ in range(svc.MAX_FAILED_ATTEMPTS):
            svc._record_failed_attempt("charlie")
        assert svc._check_rate_limit("charlie") is False

    def test_lockout_expires_after_duration(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        # Backdate all failures beyond the lockout window
        old = datetime.now() - timedelta(minutes=svc.LOCKOUT_DURATION_MINUTES + 1)
        svc._failed_attempts["dave"] = [old] * svc.MAX_FAILED_ATTEMPTS
        assert svc._check_rate_limit("dave") is True

    def test_clear_failed_attempts_resets_counter(self, tmp_path):
        svc = _make_auth_service(tmp_path)
        for _ in range(svc.MAX_FAILED_ATTEMPTS):
            svc._record_failed_attempt("eve")
        assert svc._check_rate_limit("eve") is False
        svc._clear_failed_attempts("eve")
        assert svc._check_rate_limit("eve") is True


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:
    """Tests for the User dataclass-like model."""

    def test_admin_has_all_permissions(self):
        with patch("services.auth_service.st"):
            from solar_platform.services.auth import User
        user = User(1, "admin", "a@b.com", "Admin", "admin")
        for perm in ("read", "write", "delete", "manage_users", "manage_settings", "export"):
            assert user.has_permission(perm) is True

    def test_viewer_has_read_only(self):
        with patch("services.auth_service.st"):
            from solar_platform.services.auth import User
        user = User(2, "viewer", "v@b.com", "Viewer", "viewer")
        assert user.has_permission("read") is True
        assert user.has_permission("write") is False
        assert user.has_permission("delete") is False

    def test_to_dict_contains_all_fields(self):
        with patch("services.auth_service.st"):
            from solar_platform.services.auth import User
        user = User(3, "test", "t@b.com", "Test User", "analyst", True)
        d = user.to_dict()
        assert d["user_id"] == 3
        assert d["username"] == "test"
        assert d["role"] == "analyst"
        assert d["is_active"] is True
