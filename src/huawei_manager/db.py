"""db.py — SQLite foundation: ConnectionManager, schema init, versioning.

Thread-safe (check_same_thread=False) for PySide6 QTimer compatibility.
Database path: ~/.huawei_manager/inventory.db
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("huawei.db")

# ── Schema ─────────────────────────────────────────────────────────────

_DEVICES_DDL = """\
CREATE TABLE IF NOT EXISTS devices (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER DEFAULT 22,
    type            TEXT DEFAULT 'ROUTER',
    status          TEXT DEFAULT 'unknown',
    version         TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    username        TEXT DEFAULT '',
    password        TEXT DEFAULT '',
    password_env    TEXT DEFAULT '',
    ssh_key         TEXT DEFAULT '',
    extra_metadata  TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
"""

_USERS_DDL = """\
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    role        TEXT DEFAULT 'user',
    created_at  TEXT DEFAULT (datetime('now')),
    last_login  TEXT
);
"""

_ACTIVE_SESSIONS_DDL = """\
CREATE TABLE IF NOT EXISTS active_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    started_at  TEXT DEFAULT (datetime('now')),
    last_touch  TEXT DEFAULT (datetime('now'))
);
"""

_DB_META_DDL = """\
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_ALL_DDL = [_DEVICES_DDL, _USERS_DDL, _ACTIVE_SESSIONS_DDL, _DB_META_DDL]


# ── Connection ─────────────────────────────────────────────────────────

def get_database_path() -> Path:
    """Return ~/.huawei_manager/inventory.db, creating the directory if needed."""
    db_dir = Path.home() / ".huawei_manager"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "inventory.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with check_same_thread=False.

    Args:
        db_path: Path to the database file. If None, uses get_database_path().
    """
    if db_path is None:
        db_path = get_database_path()
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema init ────────────────────────────────────────────────────────

def init_database(conn: sqlite3.Connection) -> None:
    """Create all 4 tables if they don't exist. Idempotent."""
    for ddl in _ALL_DDL:
        conn.execute(ddl)
    conn.commit()
    log.debug("init_database: schema OK")


# ── Versioning ─────────────────────────────────────────────────────────

def get_db_version(conn: sqlite3.Connection) -> int | None:
    """Return the current schema version, or None if never set."""
    row = conn.execute(
        "SELECT value FROM db_meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0]) if row else None


def set_db_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the schema version (upsert)."""
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )
    conn.commit()
