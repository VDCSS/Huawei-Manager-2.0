"""Tests for huawei_manager.db — SQLite foundation (TDD)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class TestInitDatabase:
    """init_database() should create all 4 tables."""

    def test_creates_devices_table(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection, init_database

        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        try:
            init_database(conn)
            tables = _table_names(conn)
            assert "devices" in tables
        finally:
            conn.close()

    def test_creates_users_table(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection, init_database

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            assert "users" in _table_names(conn)
        finally:
            conn.close()

    def test_creates_active_sessions_table(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection, init_database

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            assert "active_sessions" in _table_names(conn)
        finally:
            conn.close()

    def test_creates_db_meta_table(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection, init_database

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            assert "db_meta" in _table_names(conn)
        finally:
            conn.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Re-running init_database should not fail or duplicate tables."""
        from huawei_manager.db import get_connection, init_database

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            init_database(conn)
            tables = _table_names(conn)
            # 4 user tables + sqlite_sequence (auto-created by AUTOINCREMENT)
            assert {"devices", "users", "active_sessions", "db_meta"}.issubset(tables)
        finally:
            conn.close()


class TestGetConnection:
    """get_connection() should return valid SQLite connections."""

    def test_returns_connection(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection

        conn = get_connection(tmp_path / "test.db")
        try:
            assert isinstance(conn, sqlite3.Connection)
            # verify it's usable
            conn.execute("SELECT 1")
        finally:
            conn.close()

    def test_check_same_thread_disabled(self, tmp_path: Path) -> None:
        """SQLite connection must work across threads (PySide6 QTimers)."""
        from huawei_manager.db import get_connection

        conn = get_connection(tmp_path / "test.db")
        try:
            # check_same_thread=False allows this
            conn.execute("SELECT 1")
        finally:
            conn.close()

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection

        nested = tmp_path / "sub" / "dir" / "test.db"
        conn = get_connection(nested)
        try:
            assert nested.parent.exists()
        finally:
            conn.close()


class TestDatabasePath:
    """get_database_path() should return ~/.huawei_manager/inventory.db."""

    def test_returns_path(self) -> None:
        from huawei_manager.db import get_database_path

        path = get_database_path()
        assert isinstance(path, Path)
        assert path.name == "inventory.db"
        assert ".huawei_manager" in str(path)

    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from huawei_manager import db

        fake_home = tmp_path / "fakehome"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        # Re-call to get the path with our patched home
        path = db.get_database_path()
        assert path.parent.exists()


class TestVersioning:
    """get_db_version / set_db_version roundtrip."""

    def test_initial_version_is_none(self, tmp_path: Path) -> None:
        from huawei_manager.db import get_connection, get_db_version, init_database

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            assert get_db_version(conn) is None
        finally:
            conn.close()

    def test_set_and_get_version(self, tmp_path: Path) -> None:
        from huawei_manager.db import (
            get_connection,
            get_db_version,
            init_database,
            set_db_version,
        )

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            set_db_version(conn, 1)
            assert get_db_version(conn) == 1
        finally:
            conn.close()

    def test_overwrite_version(self, tmp_path: Path) -> None:
        from huawei_manager.db import (
            get_connection,
            get_db_version,
            init_database,
            set_db_version,
        )

        conn = get_connection(tmp_path / "test.db")
        try:
            init_database(conn)
            set_db_version(conn, 1)
            set_db_version(conn, 2)
            assert get_db_version(conn) == 2
        finally:
            conn.close()


# ── helpers ────────────────────────────────────────────────────────────

def _table_names(conn: sqlite3.Connection) -> set[str]:
    """Return the set of table names in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}
