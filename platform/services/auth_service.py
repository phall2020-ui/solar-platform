"""
Authentication Service for Solar Portfolio Manager.
Provides user authentication, role-based access control, and session management.
"""
import hashlib
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import streamlit as st

logger = logging.getLogger(__name__)


class User:
    """User model."""
    def __init__(self, user_id: int, username: str, email: str, full_name: str,
                 role: str, is_active: bool = True):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.full_name = full_name
        self.role = role
        self.is_active = is_active

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission based on role."""
        role_permissions = {
            "admin": ["read", "write", "delete", "manage_users", "manage_settings", "export"],
            "manager": ["read", "write", "export"],
            "analyst": ["read", "write", "export"],
            "viewer": ["read"],
        }
        return permission in role_permissions.get(self.role, [])

    def to_dict(self) -> dict:
        """Convert user to dictionary."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
        }


class AuthService:
    """Authentication service for managing users and sessions."""

    # Rate limiting constants
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15

    def __init__(self, db_path: Path | None = None):
        """Initialize authentication service."""
        if db_path is None:
            db_path = Path.home() / ".solar_toolkit" / "users.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # In-memory rate limiting: {username: [(timestamp, ...), ...]}
        self._failed_attempts: dict[str, list[datetime]] = {}
        self._init_database()
        self._create_default_admin()

    def _init_database(self):
        """Initialize the user database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    preferences TEXT
                )
            """)

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Audit log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    resource TEXT,
                    details TEXT,
                    ip_address TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

    def _create_default_admin(self):
        """Create default admin user if no users exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                # Generate a secure random password — change this immediately after first login
                default_password = secrets.token_urlsafe(16)
                password_hash = self._hash_password(default_password)
                cursor.execute("""
                    INSERT INTO users (username, email, full_name, password_hash, role)
                    VALUES (?, ?, ?, ?, ?)
                """, ("admin", "admin@ampyr.com", "Administrator", password_hash, "admin"))
                # Print the generated password so the admin can note it on first run
                print(f"[AUTH] Default admin user created. Username: admin | Password: {default_password}")
                print("[AUTH] *** Change this password immediately after first login! ***")
                logger.warning("Default admin user created with auto-generated password. Change immediately.")

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify a password against a stored hash.

        Supports both bcrypt and legacy SHA-256 hashes.
        If a legacy SHA-256 hash matches, it is auto-upgraded to bcrypt.
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        except (ValueError, TypeError):
            # Fallback: stored_hash may be a legacy SHA-256 hex digest
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            if secrets.compare_digest(legacy_hash, stored_hash):
                # Auto-upgrade to bcrypt
                return True
            return False

    def _upgrade_password_hash(self, user_id: int, password: str):
        """Upgrade a legacy password hash to bcrypt."""
        new_hash = self._hash_password(password)
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, user_id))
        logger.info(f"Upgraded password hash to bcrypt for user_id={user_id}")

    def _check_rate_limit(self, username: str) -> bool:
        """Check if a user is allowed to attempt login.

        Returns True if the user can attempt login, False if locked out.
        After MAX_FAILED_ATTEMPTS failures within LOCKOUT_DURATION_MINUTES,
        the account is locked for LOCKOUT_DURATION_MINUTES.
        """
        now = datetime.now()
        cutoff = now - timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)

        # Prune old attempts
        if username in self._failed_attempts:
            self._failed_attempts[username] = [
                ts for ts in self._failed_attempts[username] if ts > cutoff
            ]

        recent = self._failed_attempts.get(username, [])
        return len(recent) < self.MAX_FAILED_ATTEMPTS

    def _record_failed_attempt(self, username: str):
        """Record a failed login attempt for rate limiting."""
        if username not in self._failed_attempts:
            self._failed_attempts[username] = []
        self._failed_attempts[username].append(datetime.now())

    def _clear_failed_attempts(self, username: str):
        """Clear failed login attempts after a successful login."""
        self._failed_attempts.pop(username, None)

    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate a user with username and password."""
        # Check rate limit before attempting authentication
        if not self._check_rate_limit(username):
            self._log_action(None, "login_locked", "system",
                           details=f"Account locked due to too many failed attempts: {username}")
            return None

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_id, username, email, full_name, role, is_active, password_hash
                FROM users
                WHERE username = ? AND is_active = 1
            """, (username,))

            row = cursor.fetchone()

        if row:
            user_data = row[:6]
            stored_hash = row[6]

            if self._verify_password(password, stored_hash):
                user = User(*user_data)
                # Auto-upgrade legacy SHA-256 hash to bcrypt
                if not stored_hash.startswith('$2'):
                    self._upgrade_password_hash(user.user_id, password)
                self._clear_failed_attempts(username)
                self._update_last_login(user.user_id)
                self._log_action(user.user_id, "login", "system")
                return user

        # Authentication failed
        self._record_failed_attempt(username)
        self._log_action(None, "login_failed", "system", details=f"Failed login for: {username}")
        return None

    def _update_last_login(self, user_id: int):
        """Update last login timestamp."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?
            """, (user_id,))

    def create_user(self, username: str, email: str, full_name: str,
                   password: str, role: str = "viewer") -> bool:
        """Create a new user."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()

                password_hash = self._hash_password(password)
                cursor.execute("""
                    INSERT INTO users (username, email, full_name, password_hash, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, email, full_name, password_hash, role))

            return True
        except sqlite3.IntegrityError:
            return False

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user details."""
        allowed_fields = ['email', 'full_name', 'role', 'is_active']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return False

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [user_id]

            cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        return True

    def change_password(self, user_id: int, new_password: str) -> bool:
        """Change user password."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            password_hash = self._hash_password(new_password)
            cursor.execute("""
                UPDATE users SET password_hash = ? WHERE user_id = ?
            """, (password_hash, user_id))

        self._log_action(user_id, "password_change", "user")
        return True

    def get_user_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_id, username, email, full_name, role, is_active
                FROM users WHERE user_id = ?
            """, (user_id,))

            row = cursor.fetchone()

        if row:
            return User(*row)
        return None

    def list_users(self) -> list[User]:
        """List all users."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_id, username, email, full_name, role, is_active
                FROM users ORDER BY username
            """)

            users = [User(*row) for row in cursor.fetchall()]
        return users

    def delete_user(self, user_id: int) -> bool:
        """Soft delete a user by deactivating."""
        return self.update_user(user_id, is_active=False)

    def _log_action(self, user_id: int | None, action: str, resource: str,
                   details: str = None):
        """Log user action to audit log."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO audit_log (user_id, action, resource, details)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, resource, details))

    def get_audit_log(self, user_id: int | None = None,
                     limit: int = 100) -> list[dict]:
        """Get audit log entries."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    SELECT log_id, user_id, action, resource, details, timestamp
                    FROM audit_log WHERE user_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT log_id, user_id, action, resource, details, timestamp
                    FROM audit_log
                    ORDER BY timestamp DESC LIMIT ?
                """, (limit,))

            logs = []
            for row in cursor.fetchall():
                logs.append({
                    "log_id": row[0],
                    "user_id": row[1],
                    "action": row[2],
                    "resource": row[3],
                    "details": row[4],
                    "timestamp": row[5],
                })

        return logs


# Streamlit integration helpers
def init_session_auth():
    """Initialize authentication in Streamlit session state."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "auth_service" not in st.session_state:
        st.session_state.auth_service = AuthService()


def get_current_user() -> User | None:
    """Get currently logged-in user."""
    init_session_auth()
    return st.session_state.get("user")


def require_login():
    """Require user to be logged in. Redirect to login if not."""
    init_session_auth()
    if st.session_state.user is None:
        from components.auth_ui import render_login_page
        render_login_page()
        st.stop()


def require_permission(permission: str):
    """Require user to have specific permission."""
    user = get_current_user()
    if user is None or not user.has_permission(permission):
        st.error(f"You do not have permission to {permission}")
        st.stop()


def logout():
    """Log out current user."""
    if st.session_state.user:
        st.session_state.auth_service._log_action(
            st.session_state.user.user_id, "logout", "system"
        )
    st.session_state.user = None
