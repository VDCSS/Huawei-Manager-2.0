"""Tests for AuthService (authentication + session management)."""
from __future__ import annotations

import sqlite3
import time

import pytest

from huawei_manager.auth_service import AuthService
from huawei_manager.db import get_connection, init_database
from huawei_manager.sdn_controller.authz import Role
from huawei_manager.user_repository import UserRepository

# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    db_file = tmp_path / "test_auth.db"
    c = get_connection(str(db_file))
    init_database(c)
    yield c
    c.close()


@pytest.fixture
def repo(conn: sqlite3.Connection) -> UserRepository:
    return UserRepository(conn)


@pytest.fixture
def auth_service(repo: UserRepository) -> AuthService:
    return AuthService(repo=repo, timeout_secs=300)


@pytest.fixture
def admin_user(repo: UserRepository):
    return repo.create_user("admin1", "adminpass", role="admin")


@pytest.fixture
def tecnico_user(repo: UserRepository):
    return repo.create_user("tech1", "techpass", role="tecnico")


@pytest.fixture
def regular_user(repo: UserRepository):
    return repo.create_user("user1", "userpass", role="user")


# ── login ────────────────────────────────────────────────────────────────

class TestLogin:
    def test_successful_login_admin(self, auth_service, admin_user):
        assert auth_service.login("admin1", "adminpass") is True
        assert auth_service.is_authenticated

    def test_successful_login_tecnico(self, auth_service, tecnico_user):
        assert auth_service.login("tech1", "techpass") is True
        assert auth_service.current_role == Role.TECNICO

    def test_successful_login_user(self, auth_service, regular_user):
        assert auth_service.login("user1", "userpass") is True
        assert auth_service.current_role == Role.USER

    def test_failed_login_wrong_password(self, auth_service, admin_user):
        assert auth_service.login("admin1", "wrongpass") is False
        assert not auth_service.is_authenticated

    def test_failed_login_nonexistent_user(self, auth_service):
        assert auth_service.login("ghost", "anypass") is False
        assert not auth_service.is_authenticated

    def test_lockout_after_max_attempts(self, auth_service, admin_user):
        # 3 failed attempts should trigger lockout
        for _ in range(3):
            auth_service.login("admin1", "wrongpass")
        # 4th attempt should raise PermissionError (locked out)
        with pytest.raises(PermissionError, match="Account locked"):
            auth_service.login("admin1", "adminpass")

    def test_successful_login_clears_attempts(self, auth_service, admin_user):
        auth_service.login("admin1", "wrongpass")
        auth_service.login("admin1", "wrongpass")
        assert auth_service.login("admin1", "adminpass") is True
        auth_service.logout()
        auth_service.login("admin1", "wrongpass")
        auth_service.login("admin1", "wrongpass")
        assert auth_service.login("admin1", "adminpass") is True


# ── logout ───────────────────────────────────────────────────────────────

class TestLogout:
    def test_logout_clears_session(self, auth_service, admin_user):
        auth_service.login("admin1", "adminpass")
        assert auth_service.is_authenticated
        auth_service.logout()
        assert not auth_service.is_authenticated
        assert auth_service.current_role == Role.USER

    def test_logout_without_login_is_noop(self, auth_service):
        auth_service.logout()
        assert not auth_service.is_authenticated


# ── current_user ─────────────────────────────────────────────────────────

class TestCurrentUser:
    def test_none_when_not_authenticated(self, auth_service):
        assert auth_service.current_user is None

    def test_returns_user_after_login(self, auth_service, admin_user):
        auth_service.login("admin1", "adminpass")
        user = auth_service.current_user
        assert user is not None
        assert user.username == "admin1"
        assert user.role == "admin"


# ── session_timeout ──────────────────────────────────────────────────────

class TestSessionTimeout:
    def test_session_expires_after_timeout(self, repo):
        svc = AuthService(repo=repo, timeout_secs=1)
        repo.create_user("admin1", "adminpass", role="admin")
        svc.login("admin1", "adminpass")
        assert svc.is_authenticated
        # Wait for timeout (1s)
        time.sleep(1.5)
        assert not svc.is_authenticated
        assert svc.current_role == Role.USER

    def test_session_not_expired_with_no_timeout(self, repo):
        svc = AuthService(repo=repo, timeout_secs=0)
        repo.create_user("admin1", "adminpass", role="admin")
        svc.login("admin1", "adminpass")
        assert svc.is_authenticated
        # Even after sleeping, should still be authenticated
        time.sleep(0.5)
        assert svc.is_authenticated

    def test_touch_extends_session(self, repo):
        svc = AuthService(repo=repo, timeout_secs=2)
        repo.create_user("admin1", "adminpass", role="admin")
        svc.login("admin1", "adminpass")
        time.sleep(1.5)
        svc.touch()  # extend session
        time.sleep(1.5)
        assert svc.is_authenticated  # should still be valid


# ── require_role ─────────────────────────────────────────────────────────

class TestRequireRole:
    def test_admin_meets_any_requirement(self, auth_service, admin_user):
        auth_service.login("admin1", "adminpass")
        assert auth_service.require_role("admin") is True
        assert auth_service.require_role("tecnico") is True
        assert auth_service.require_role("user") is True

    def test_tecnico_meets_user_and_tecnico_but_not_admin(self, auth_service, tecnico_user):
        auth_service.login("tech1", "techpass")
        assert auth_service.require_role("user") is True
        assert auth_service.require_role("tecnico") is True
        assert auth_service.require_role("admin") is False

    def test_user_meets_only_user_requirement(self, auth_service, regular_user):
        auth_service.login("user1", "userpass")
        assert auth_service.require_role("user") is True
        assert auth_service.require_role("tecnico") is False
        assert auth_service.require_role("admin") is False

    def test_not_authenticated_fails(self, auth_service):
        assert auth_service.require_role("admin") is False


# ── change_password ──────────────────────────────────────────────────────

class TestChangePassword:
    def test_change_password_success(self, auth_service, admin_user):
        assert auth_service.change_password("admin1", "adminpass", "newpass456") is True
        # Old password should fail
        assert auth_service.login("admin1", "adminpass") is False
        # New password should work
        assert auth_service.login("admin1", "newpass456") is True

    def test_wrong_current_password_raises(self, auth_service, admin_user):
        with pytest.raises(PermissionError):
            auth_service.change_password("admin1", "wrongpass", "newpass456")

    def test_empty_new_password_raises(self, auth_service, admin_user):
        with pytest.raises(ValueError):
            auth_service.change_password("admin1", "adminpass", "")
