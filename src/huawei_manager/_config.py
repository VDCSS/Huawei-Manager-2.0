"""Module-level setup: logging, secrets, audit, config constants."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from huawei_manager.audit_log import AuditLogger
from huawei_manager.vault import SecretsBackend, _set_ts_path, get_backend

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR: Path = PROJECT_ROOT / "logs"
_set_ts_path(PROJECT_ROOT / ".ssh_rotation_ts")

# ─── Module-level names (initialized lazily via init()) ──────────────
_INITIALIZED: bool = False
_secrets: SecretsBackend | None = None
audit: AuditLogger | None = None
log: logging.Logger | None = None

HOST: str = ""
PORT: int = 22
USER: str = ""
PASS: str = ""
SSH_KEY: str = ""
HK_VERIFY: str = "strict"

ADMIN_USERNAME: str = ""
ADMIN_PASSWORD: str = ""
TECNICO_USERNAME: str = ""
TECNICO_PASSWORD: str = ""
AUDIT_HMAC_KEY: str = ""


# ─── INIT: called once from __init__.py:main() ──────────────────────
def init() -> None:
    """Inicializa logging, secrets backend e audit logger.

    Idempotente — pode ser chamada múltiplas vezes com segurança.
    Deve ser chamada antes de qualquer outro módulo que importe
    as constantes deste módulo.
    """
    global _INITIALIZED
    global _secrets, audit, log
    global HOST, PORT, USER, PASS, SSH_KEY, HK_VERIFY
    global ADMIN_USERNAME, ADMIN_PASSWORD
    global TECNICO_USERNAME, TECNICO_PASSWORD, AUDIT_HMAC_KEY

    if _INITIALIZED:
        return
    _INITIALIZED = True

    # ── Logging setup ───────────────────────────────────────────────
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

    # ── Secrets / Audit ─────────────────────────────────────────────
    try:
        _secrets = get_backend(project_root=str(PROJECT_ROOT))
    except Exception as _e:
        log.error("Falha ao inicializar secrets backend: %s \u2014 usando fallback env", _e)
        from huawei_manager.vault import EnvBackend
        _secrets = EnvBackend(env_path=PROJECT_ROOT / ".env")

    HOST      = _s("ROUTER_HOST")
    PORT      = int(_s("ROUTER_PORT", "22"))
    USER      = _s("ROUTER_USERNAME")
    PASS      = _s("ROUTER_PASSWORD")
    SSH_KEY   = os.path.expanduser(_s("ROUTER_SSH_KEY", "~/.ssh/huawei_ed25519"))
    _hk_raw = _s("ROUTER_HOSTKEY_VERIFY", "strict").lower().strip()
    HK_VERIFY = _hk_raw if _hk_raw in ("strict", "tofu", "off") else "strict"

    ADMIN_USERNAME     = _s("ADMIN_USERNAME")
    ADMIN_PASSWORD     = _s("ADMIN_PASSWORD")
    TECNICO_USERNAME   = _s("TECNICO_USERNAME")
    TECNICO_PASSWORD   = _s("TECNICO_PASSWORD")
    AUDIT_HMAC_KEY     = _s("AUDIT_HMAC_KEY", "")

    audit = AuditLogger(
        filename=str(PROJECT_ROOT / "logs" / "huawei_audit_structured.jsonl"),
        hmac_key=AUDIT_HMAC_KEY,
    )


def _s(key: str, default: str = "") -> str:
    """Lê um valor do backend de secrets com fallback para default."""
    if _secrets is None:
        return default
    return _secrets.get(key, default)


def get_credentials(role: str) -> tuple[str, str]:
    """Retorna (username, password) para o papel solicitado.

    Args:
        role: ``"admin"`` ou ``"tecnico"``.

    Returns:
        Tupla (username, password). Retorna ("", "") se o papel for
        desconhecido.

    Nota: ponto de controle único para acesso a credenciais.
          Em produção, substituir por chamada a vault externo.
    """
    if role == "admin":
        return ADMIN_USERNAME, ADMIN_PASSWORD
    if role == "tecnico":
        return TECNICO_USERNAME, TECNICO_PASSWORD
    return "", ""
