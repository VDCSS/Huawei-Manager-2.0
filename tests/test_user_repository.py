"""Tests for UserRepository (SQLite-backed user CRUD with Argon2)."""
from __future__ import annotations

import sqlite3

import pytest

from huawei_manager.db import get_connection, init_database
from huawei_manager.user_repository import User, UserRepository

# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    """Fresh temporary SQLite database."""
    db_file = tmp_path / "test_users.db"
    c = get_connection(str(db_file))
    init_database(c)
    yield c
    c.close()


@pytest.fixture
def repo(conn: sqlite3.Connection) -> UserRepository:
    return UserRepository(conn)


@pytest.fixture
def admin_user(repo: UserRepository) -> User:
    return repo.create_user("admin1", "adminpass", role="admin")


# ── create_user ─────────────────────────────────────────────────────────

class TestCreateUser:
    def test_creates_user_with_hashed_password(self, repo, admin_user):
        assert admin_user.id > 0
        assert admin_user.username == "admin1"
        assert admin_user.role == "admin"
        assert admin_user.password != "adminpass"
        assert len(admin_user.password) > 20  # argon2 hash is long

    def test_password_is_hashed_not_plaintext(self, repo):
        user = repo.create_user("testuser", "mypassword", role="user")
        assert user.password != "mypassword"
        assert user.password.startswith("$argon2")  # argon2 prefix

    def test_duplicate_username_raises(self, repo, admin_user):
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_user("admin1", "otherpass", role="user")

    def test_empty_username_raises(self, repo):
        with pytest.raises(ValueError, match="Username is required"):
            repo.create_user("", "pass123", role="user")

    def test_empty_password_raises(self, repo):
        with pytest.raises(ValueError, match="Password is required"):
            repo.create_user("newuser", "", role="user")

    def test_invalid_role_raises(self, repo):
        with pytest.raises(ValueError, match="Invalid role"):
            repo.create_user("newuser", "pass123", role="superadmin")

    def test_default_role_is_user(self, repo):
        user = repo.create_user("regular", "pass123")
        assert user.role == "user"


# ── get_user_by_id ───────────────────────────────────────────────────────

class TestGetUserById:
    def test_returns_user_by_id(self, repo, admin_user):
        user = repo.get_user_by_id(admin_user.id)
        assert user is not None
        assert user.username == "admin1"
        assert user.role == "admin"

    def test_returns_none_for_nonexistent_id(self, repo):
        assert repo.get_user_by_id(99999) is None


# ── get_user_by_username ─────────────────────────────────────────────────

class TestGetUserByUsername:
    def test_returns_user_by_username(self, repo, admin_user):
        user = repo.get_user_by_username("admin1")
        assert user is not None
        assert user.id == admin_user.id

    def test_returns_none_for_nonexistent(self, repo):
        assert repo.get_user_by_username("ghost") is None


# ── list_users ───────────────────────────────────────────────────────────

class TestListUsers:
    def test_empty_list_when_no_users(self, repo):
        assert repo.list_users() == []

    def test_returns_all_users_sorted_by_username(self, repo):
        repo.create_user("charlie", "pass1", role="user")
        repo.create_user("alice", "pass2", role="admin")
        repo.create_user("bob", "pass3", role="tecnico")
        users = repo.list_users()
        assert len(users) == 3
        assert [u.username for u in users] == ["alice", "bob", "charlie"]


# ── update_user ──────────────────────────────────────────────────────────

class TestUpdateUser:
    def test_updates_username(self, repo, admin_user):
        updated = repo.update_user(admin_user.id, username="newadmin")
        assert updated is not None
        assert updated.username == "newadmin"

    def test_updates_password(self, repo, admin_user):
        updated = repo.update_user(admin_user.id, password="newpass456")
        assert updated is not None
        # Should be re-hashed
        assert updated.password != "newpass456"
        # Verify new password works
        user = repo.verify_password("admin1", "newpass456")
        assert user is not None
        # Old password should fail
        assert repo.verify_password("admin1", "adminpass") is None

    def test_updates_role(self, repo, admin_user):
        updated = repo.update_user(admin_user.id, role="tecnico")
        assert updated is not None
        assert updated.role == "tecnico"

    def test_invalid_role_raises(self, repo, admin_user):
        with pytest.raises(ValueError, match="Invalid role"):
            repo.update_user(admin_user.id, role="superadmin")

    def test_returns_none_for_nonexistent(self, repo):
        assert repo.update_user(99999, username="ghost") is None

    def test_no_changes_returns_user(self, repo, admin_user):
        updated = repo.update_user(admin_user.id)
        assert updated is not None
        assert updated.username == "admin1"


# ── delete_user ──────────────────────────────────────────────────────────

class TestDeleteUser:
    def test_deletes_existing_user(self, repo, admin_user):
        assert repo.delete_user(admin_user.id) is True
        assert repo.get_user_by_id(admin_user.id) is None

    def test_returns_false_for_nonexistent(self, repo):
        assert repo.delete_user(99999) is False


# ── verify_password ──────────────────────────────────────────────────────

class TestVerifyPassword:
    def test_valid_credentials_return_user(self, repo, admin_user):
        user = repo.verify_password("admin1", "adminpass")
        assert user is not None
        assert user.username == "admin1"

    def test_invalid_password_returns_none(self, repo, admin_user):
        assert repo.verify_password("admin1", "wrongpass") is None

    def test_nonexistent_user_returns_none(self, repo):
        assert repo.verify_password("ghost", "anypass") is None


# ── seed_default_users ─────────────────────────────────────────────────────

class TestSeedDefaultUsers:
    def test_creates_three_default_users(self, repo):
        repo.seed_default_users()
        users = repo.list_users()
        assert len(users) == 3
        usernames = {u.username for u in users}
        assert usernames == {"user_admin", "user_tecnico", "user_user"}

    def test_idempotent_on_multiple_calls(self, repo):
        repo.seed_default_users()
        repo.seed_default_users()
        assert len(repo.list_users()) == 3

    def test_admin_can_authenticate(self, repo):
        repo.seed_default_users()
        user = repo.verify_password("user_admin", "123mudar")
        assert user is not None
        assert user.role == "admin"

    def test_tecnico_can_authenticate(self, repo):
        repo.seed_default_users()
        user = repo.verify_password("user_tecnico", "123tec")
        assert user is not None
        assert user.role == "tecnico"

    def test_operador_can_authenticate(self, repo):
        repo.seed_default_users()
        user = repo.verify_password("user_user", "123op")
        assert user is not None
        assert user.role == "user"

    def test_wrong_password_fails(self, repo):
        repo.seed_default_users()
        assert repo.verify_password("user_admin", "wrongpass") is None
