"""user_repository.py — SQLite CRUD repository for User objects.

Stores users with hashed passwords (Argon2) and RBAC roles.
Schema mirrors the ``users`` table defined in ``db.py``.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
except ImportError:  # pragma: no cover
    PasswordHasher = None  # type: ignore[assignment,misc]
    VerifyMismatchError = type("VerifyMismatchError", (Exception,), {})
    InvalidHashError = type("InvalidHashError", (Exception,), {})

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.sdn_controller.authz import Role

log = logging.getLogger("huawei.user_repo")


_ph = None


def _get_password_hasher():  # type: ignore[no-untyped-def]
    """Get or create PasswordHasher instance."""
    global _ph
    if _ph is None:
        if PasswordHasher is None:
            raise RuntimeError("argon2-cffi is required for password hashing")
        _ph = PasswordHasher()
    return _ph


def _hash_password(password: str) -> str:
    """Hash a password using Argon2 (fail-closed if argon2-cffi unavailable)."""
    ph = _get_password_hasher()
    return ph.hash(password)


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against an Argon2 hash."""
    ph = _get_password_hasher()
    if not hashed:
        return False
    try:
        ph.verify(hashed, password)
        return True
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


@dataclass
class User:
    """User model for RBAC authentication."""

    id: int = 0
    username: str = ""
    password: str = ""  # argon2 hash
    role: str = "user"  # "user" | "tecnico" | "admin"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> User | None:
        if row is None:
            return None
        return cls(
            id=row["id"],
            username=row["username"],
            password=row["password"],
            role=row["role"],
        )


class UserRepository:
    """CRUD repository for User objects in SQLite.

    Args:
        conn: SQLite connection (thread-safe with check_same_thread=False).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_user(
        self, username: str, password: str, role: str = "user"
    ) -> User:
        """Create a new user with hashed password.

        Raises:
            ValueError: If username or password is empty, or role is invalid.
            sqlite3.IntegrityError: If username already exists.
        """
        if not username.strip():
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")
        try:
            Role.from_string(role)
        except SdnValidationError:
            valid = ", ".join(r.value for r in Role)
            raise ValueError(f"Invalid role: {role!r}. Valid roles: {valid}")

        hashed = _hash_password(password)
        cur = self._conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role),
        )
        self._conn.commit()
        user_id = cur.lastrowid or 0
        log.debug("create_user: %s (id=%s, role=%s)", username, user_id, role)
        return User(id=user_id, username=username, password=hashed, role=role)

    def get_user_by_id(self, user_id: int) -> User | None:
        """Fetch a user by primary key."""
        row = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return User.from_row(row)

    def get_user_by_username(self, username: str) -> User | None:
        """Fetch a user by username (case-sensitive)."""
        row = self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return User.from_row(row)

    def list_users(self) -> list[User]:
        """List all users ordered by username."""
        rows = self._conn.execute(
            "SELECT * FROM users ORDER BY username"
        ).fetchall()
        return [u for u in (User.from_row(r) for r in rows) if u is not None]

    def update_user(
        self, user_id: int, username: str | None = None,
        password: str | None = None, role: str | None = None,
    ) -> User | None:
        """Update a user's fields. Raises ValueError on invalid role.

        Returns the updated User, or None if the user doesn't exist.
        """
        user = self.get_user_by_id(user_id)
        if user is None:
            return None

        updates: dict[str, object] = {}
        if username is not None:
            updates["username"] = username
        if password is not None:
            updates["password"] = _hash_password(password)
        if role is not None:
            try:
                Role.from_string(role)
            except SdnValidationError:
                valid = ", ".join(r.value for r in Role)
                raise ValueError(f"Invalid role: {role!r}. Valid roles: {valid}")
            updates["role"] = role

        if updates:
            set_clauses = [f"{k} = ?" for k in updates]
            params = list(updates.values()) + [user_id]
            self._conn.execute(
                f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            self._conn.commit()
            log.debug("update_user: id=%s updates=%s", user_id, list(updates))

        return self.get_user_by_id(user_id)

    def change_password(self, user_id: int, new_password: str) -> bool:
        """Change a user's password. Returns True if updated, False if user not found."""
        if not new_password:
            raise ValueError("New password is required")
        user = self.get_user_by_id(user_id)
        if user is None:
            return False
        hashed = _hash_password(new_password)
        self._conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hashed, user_id),
        )
        self._conn.commit()
        log.debug("change_password: id=%s", user_id)
        return True

    def delete_user(self, user_id: int) -> bool:
        """Delete a user. Returns True if deleted, False if not found."""
        cur = self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self._conn.commit()
        if cur.rowcount > 0:
            log.debug("delete_user: id=%s", user_id)
            return True
        return False

    def verify_password(self, username: str, password: str) -> User | None:
        """Authenticate a user by username+password.

        Returns the User (without password) if valid, None otherwise.
        Fail-closed: returns None on any error.
        """
        user = self.get_user_by_username(username)
        if user is None or not user.password:
            return None
        if _verify_password(password, user.password):
            return user
        log.warning("verify_password: failed for user=%s", username)
        return None

    def seed_default_users(self) -> None:
        """Seed default users if none exist.

        Creates admin, tecnico, and operador users with default passwords.
        Idempotent - safe to call multiple times.
        """
        if self.list_users():
            return  # Users already exist

        default_users = [
            ("user_admin", "123mudar", "admin", "Administrador do Sistema"),
            ("user_tecnico", "123tec", "tecnico", "Técnico de Rede"),
            ("user_user", "123op", "user", "Operador Padrão"),
        ]

        for username, password, role, full_name in default_users:
            try:
                self.create_user(username, password, role=role)
                log.info("seed_default_users: created %s", username)
            except (ValueError, sqlite3.IntegrityError):
                log.debug("seed_default_users: %s already exists", username)
