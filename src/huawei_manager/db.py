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

_DB_META_DDL = """\
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_ALL_DDL = [_DEVICES_DDL, _USERS_DDL, _DB_META_DDL]


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
    """Create all 3 tables if they don't exist. Idempotent."""
    for ddl in _ALL_DDL:
        conn.execute(ddl)
    conn.commit()
    log.debug("init_database: schema OK")


# ── Default admin seeding ──────────────────────────────────────────────

def ensure_default_admin(conn: sqlite3.Connection | None = None) -> str | None:
    """Seed a default admin user if the users table is empty.

    Idempotent — safe to call multiple times. Uses argon2 for password hashing.
    The password is randomly generated (secrets) and returned to the caller
    (e.g. install.sh) so it can be shown on the terminal — never logged.

    Args:
        conn: SQLite connection. If None, opens and closes one.

    Returns:
        The generated password, or None if users already existed or seeding failed.
    """
    if conn is None:
        conn = get_connection()
        should_close = True
    else:
        should_close = False

    try:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if row and row[0] > 0:
            log.debug("ensure_default_admin: users already exist, skipping")
            return None

        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(16))

        from argon2 import PasswordHasher
        ph = PasswordHasher()
        hashed = ph.hash(password)

        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("user_admin", hashed, "admin"),
        )
        conn.commit()
        log.info("ensure_default_admin: created default admin user (user_admin)")
        return password
    except Exception as exc:
        log.warning("ensure_default_admin: failed: %s", exc)
        return None
    finally:
        if should_close:
            conn.close()
