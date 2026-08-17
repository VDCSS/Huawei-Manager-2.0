"""auth_service.py — Authentication and session management service.

Provides ``AuthService`` with login/verify/logout, password change,
and session timeout management. Integrates with ``UserRepository``
for user storage and ``SessionTracker`` for RBAC role tracking.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from huawei_manager.sdn_controller.authz import Role, SessionTracker
from huawei_manager.user_repository import User, UserRepository

log = logging.getLogger("huawei.auth_service")


@dataclass
class AuthSession:
    """Active authentication session."""

    username: str
    role: Role
    started_at: float
    last_touch: float
    user_id: int = 0

    @property
    def is_expired(self) -> bool:
        return False  # expiry handled by AuthService.timeout_secs


class AuthService:
    """Authentication and session management.

    Args:
        repo: UserRepository for user CRUD operations.
        timeout_secs: Inactivity timeout before session resets to USER.
            Set to 0 to disable timeout.
    """

    # Lockout policy
    MAX_ATTEMPTS = 3
    LOCKOUT_SECS = 300

    def __init__(
        self,
        repo: UserRepository,
        timeout_secs: int | float = 300,
    ) -> None:
        self._repo = repo
        self._timeout_secs = timeout_secs
        self._session: AuthSession | None = None
        self._tracker = SessionTracker(timeout_secs=timeout_secs)
        self._attempts: dict[str, tuple[int, float]] = {}

    @property
    def current_user(self) -> User | None:
        """Current authenticated user, or None if not logged in."""
        if self._session is None:
            return None
        # Check timeout
        if self._timeout_secs > 0:
            elapsed = time.time() - self._session.last_touch
            if elapsed > self._timeout_secs:
                self._session = None
                self._tracker.set_role(Role.USER)
                log.info("Session expired due to inactivity")
                return None
        return User(
            id=self._session.user_id,
            username=self._session.username,
            role=self._session.role.value,
        )

    @property
    def is_authenticated(self) -> bool:
        """True if a user is currently authenticated."""
        return self._session is not None and self.current_user is not None

    @property
    def current_role(self) -> Role:
        """Current RBAC role (respects timeout)."""
        return self._tracker.current_role

    @property
    def session_tracker(self) -> SessionTracker:
        """Expose the underlying SessionTracker for compatibility."""
        return self._tracker

    def login(self, username: str, password: str) -> bool:
        """Authenticate a user by username/password.

        Returns True on success, False on failure.
        Implements lockout after MAX_ATTEMPTS failed attempts.

        Args:
            username: Username to authenticate.
            password: Plaintext password (verified against bcrypt hash).
        """
        # Check lockout
        if self._is_locked_out(username):
            remaining = self._lockout_remaining(username)
            log.warning(
                "login: locked out for %s (%ds remaining)", username, remaining
            )
            raise PermissionError(
                f"Account locked. Try again in {remaining}s."
            )

        user = self._repo.verify_password(username, password)
        if user is None:
            self._register_failed_attempt(username)
            log.warning("login: failed for %s", username)
            return False

        # Success — clear attempts
        self._attempts.pop(username, None)

        role = Role.from_string(user.role)
        self._session = AuthSession(
            username=user.username,
            role=role,
            started_at=time.time(),
            last_touch=time.time(),
            user_id=user.id,
        )
        self._tracker.set_role(role)
        log.info("login: success for %s (role=%s)", username, role.value)
        return True

    def logout(self) -> None:
        """End the current session, resetting to USER role."""
        self._session = None
        self._tracker.set_role(Role.USER)
        log.info("logout: session ended")

    def change_password(self, username: str, current_password: str,
                        new_password: str) -> bool:
        """Change a user's password after verifying the current one.

        Returns True on success. Raises PermissionError if current
        password is wrong or user not found.
        """
        user = self._repo.verify_password(username, current_password)
        if user is None:
            raise PermissionError("Current password is incorrect")
        if not new_password:
            raise ValueError("New password cannot be empty")
        self._repo.change_password(user.id, new_password)
        log.info("change_password: success for %s", username)
        return True

    def touch(self) -> None:
        """Update last activity timestamp for the current session."""
        if self._session is not None:
            self._session.last_touch = time.time()
            self._tracker.touch()

    def require_role(self, min_role: Role | str) -> bool:
        """Check if current session meets the minimum role requirement.

        Returns True if authenticated and role is sufficient.
        """
        if not self.is_authenticated:
            return False
        from huawei_manager.sdn_controller.authz import role_meets
        cur = self._session.role.value if self._session else "user"
        return role_meets(cur, min_role if isinstance(min_role, str) else min_role.value)

    def _is_locked_out(self, username: str) -> bool:
        """Check if username is currently locked out."""
        info = self._attempts.get(username)
        if info is None:
            return False
        attempts, lockout_time = info
        if lockout_time > 0:
            # In lockout period
            if time.time() < lockout_time:
                return True
            # Lockout expired — reset
            self._attempts.pop(username, None)
        return False

    def _lockout_remaining(self, username: str) -> int:
        info = self._attempts.get(username)
        if info is None:
            return 0
        return int(info[1] - time.time())

    def _register_failed_attempt(self, username: str) -> None:
        """Track failed attempts, triggering lockout after MAX_ATTEMPTS."""
        info = self._attempts.get(username)
        if info is None:
            count = 1
        else:
            count = info[0] + 1
        if count >= self.MAX_ATTEMPTS:
            lockout_until = time.time() + self.LOCKOUT_SECS
            self._attempts[username] = (count, lockout_until)
            log.warning("login: %s locked out for %ds", username, self.LOCKOUT_SECS)
        else:
            self._attempts[username] = (count, 0)
