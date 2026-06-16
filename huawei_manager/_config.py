#!/usr/bin/env python3
"""Module-level setup: logging, secrets, audit, config constants."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from huawei_manager.audit_log import AuditLogger
from huawei_manager.vault import SecretsBackend, get_backend

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_fh = RotatingFileHandler(
    LOG_DIR / "huawei-manager.log",
    maxBytes=5_000_000,
    backupCount=3,
    encoding="utf-8",
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(name)s \u2014 %(message)s"
))

_sh = logging.StreamHandler()
_sh.setLevel(logging.INFO)
_sh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s \u2014 %(message)s",
    datefmt="%H:%M:%S"
))

_root = logging.getLogger("huawei")
_root.setLevel(logging.DEBUG)
_root.addHandler(_fh)
_root.addHandler(_sh)

log = logging.getLogger("huawei_manager")
log.info("Logging iniciado \u2014 %s", LOG_DIR.resolve())

# ─── SECRETS / AUDIT ─────────────────────────────────────────────────
try:
    _secrets: SecretsBackend = get_backend()
except Exception as _e:
    log.error("Falha ao inicializar secrets backend: %s \u2014 usando fallback env", _e)
    from huawei_manager.vault import EnvBackend
    _secrets = EnvBackend()

# ─── CONFIG ───────────────────────────────────────────────────────────
def _s(key: str, default: str = "") -> str:
    return _secrets.get(key, default)

HOST      = _s("ROUTER_HOST")
PORT      = int(_s("ROUTER_PORT", "2222"))
USER      = _s("ROUTER_USERNAME")
PASS      = _s("ROUTER_PASSWORD")
SSH_KEY   = os.path.expanduser(_s("ROUTER_SSH_KEY", "~/.ssh/huawei_ed25519"))
HK_VERIFY = _s("ROUTER_HOSTKEY_VERIFY", "true").lower() == "true"


ADMIN_USERNAME     = _s("ADMIN_USERNAME")
ADMIN_PASSWORD     = _s("ADMIN_PASSWORD")
TECNICO_USERNAME   = _s("TECNICO_USERNAME")
TECNICO_PASSWORD   = _s("TECNICO_PASSWORD")
AUDIT_HMAC_KEY     = _s("AUDIT_HMAC_KEY", "")

audit = AuditLogger(hmac_key=AUDIT_HMAC_KEY)
