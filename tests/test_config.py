"""Tests for _config.py — initialisation, secrets helper, credentials."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_config():
    """Reset _config module state before each test.

    Ensures each test starts with a clean slate—INITIALIZED=False,
    no secrets backend, all constants defaulted.
    """
    import huawei_manager._config as _cfg

    _cfg._INITIALIZED = False
    _cfg._secrets = None
    _cfg.audit = None
    _cfg.log = None
    _cfg.HOST = ""
    _cfg.PORT = 22
    _cfg.AUDIT_HMAC_KEY = ""

    yield

    # Best-effort cleanup of root logger handlers so other tests are
    # not polluted by the RotatingFileHandler / StreamHandler we add.
    import logging

    _root = logging.getLogger("huawei")
    for h in list(_root.handlers):
        _root.removeHandler(h)
        h.close()
    _root.setLevel(logging.WARNING)


# ── _s() helper ───────────────────────────────────────────────────────


def test_s_with_secrets(monkeypatch):
    """_s delegates to the secrets backend when initialised."""
    import huawei_manager._config as _cfg

    _cfg._secrets = None
    assert _cfg._s("MISSING", "fallback") == "fallback"
    assert _cfg._s("MISSING") == ""


def test_s_returns_default_when_secrets_none():
    """_s returns default when _secrets is None (not initialised)."""
    import huawei_manager._config as _cfg

    # _secrets is already None from the autouse fixture
    assert _cfg._s("ANY_KEY", "default_val") == "default_val"


# ── init() ─────────────────────────────────────────────────────────────


def test_init_idempotent():
    """Calling init() twice only executes setup once."""
    import huawei_manager._config as _cfg

    vals = {
        "ROUTER_HOST": "10.0.0.1",
        "ROUTER_PORT": "22",
        "ROUTER_USERNAME": "admin",
        "ROUTER_PASSWORD": "x",
        "ROUTER_SSH_KEY": "",
        "ROUTER_HOSTKEY_VERIFY": "off",
    }

    def fake_s(key: str, default: str = "") -> str:
        return vals.get(key, default)

    with patch.object(_cfg, "_s", side_effect=fake_s):
        _cfg.init()
        _INITIALIZED_1 = _cfg._INITIALIZED
        _cfg.init()
        _INITIALIZED_2 = _cfg._INITIALIZED

    assert _INITIALIZED_1 is True
    assert _INITIALIZED_2 is True  # idempotent: still True, no crash


def test_init_sets_module_level_constants():
    """init() populates HOST, PORT, USER, PASS, SSH_KEY, etc."""
    import huawei_manager._config as _cfg

    env_vals = {
        "ROUTER_HOST": "192.168.1.1",
        "ROUTER_PORT": "22",
        "ROUTER_USERNAME": "admin",
        "ROUTER_PASSWORD": "secret",
        "ROUTER_SSH_KEY": "~/.ssh/test_key",
        "ROUTER_HOSTKEY_VERIFY": "tofu",
        "AUDIT_HMAC_KEY": "hmac-key-123",
    }

    def fake_s(key: str, default: str = "") -> str:
        return env_vals.get(key, default)

    with patch.object(_cfg, "_s", side_effect=fake_s):
        _cfg.init()

    assert _cfg.HOST == "192.168.1.1"
    assert _cfg.PORT == 22
    assert _cfg.USER == "admin"
    assert _cfg.PASS == "secret"
    assert _cfg.HK_VERIFY == "tofu"
    assert _cfg.AUDIT_HMAC_KEY == "hmac-key-123"


def test_init_hk_verify_defaults_to_strict():
    """Invalid or missing HOSTKEY_VERIFY falls back to 'strict'."""
    import huawei_manager._config as _cfg

    def fake_s(key: str, default: str = "") -> str:
        vals = {"ROUTER_HOSTKEY_VERIFY": "bogus"}
        return vals.get(key, default)

    with patch.object(_cfg, "_s", side_effect=fake_s):
        _cfg.init()

    assert _cfg.HK_VERIFY == "strict"


def test_init_secrets_fallback():
    """When get_backend raises, init falls back to EnvBackend."""
    import huawei_manager._config as _cfg

    with patch.object(_cfg, "get_backend", side_effect=RuntimeError("no vault")):
        _cfg.init()

    assert _cfg._secrets is not None


# ── Auth tests removed ────────────────────────────────────────────────
# Credentials are now managed via UserRepository in the database.
# See tests/test_user_repository.py for auth-related tests.
