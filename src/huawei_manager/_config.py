"""Module-level setup: logging, secrets, audit, config constants."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from huawei_manager.audit_log import AuditLogger
from huawei_manager.vault import SecretsBackend, _set_ts_path, get_backend

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
USER_CONFIG_DIR = Path.home() / ".config" / "huawei-manager"
USER_ENV_PATH = USER_CONFIG_DIR / ".env"
LOG_DIR: Path = PROJECT_ROOT / "logs"
_set_ts_path(PROJECT_ROOT / ".ssh_rotation_ts")

# ─── Ensure user .env exists ───────────────────────────────────────
_ENV_TEMPLATE = """\
# Huawei Manager 2.0 — Configuration

# --- SSH defaults -------------------------------------------------
ROUTER_SSH_KEY=
ROUTER_HOSTKEY_VERIFY=strict

# --- Crypto -------------------------------------------------------
VNF_ENCRYPT_KEY=
AUDIT_HMAC_KEY=

# --- Behavior -----------------------------------------------------
HW_ADAPTIVE_POLLING=0
SSH_TIMEOUT=90

# --- Secrets backend: env | crypto | sops | vault | aws -----------
SECRETS_BACKEND=env
"""


def _ensure_user_env() -> None:
    """Cria ~/.config/huawei-manager/.env com template se não existir."""
    if USER_ENV_PATH.exists():
        return
    try:
        import secrets
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        hmac_key = secrets.token_hex(32)
        template = _ENV_TEMPLATE.replace("AUDIT_HMAC_KEY=", f"AUDIT_HMAC_KEY={hmac_key}")
        USER_ENV_PATH.write_text(template, encoding="utf-8")
    except OSError:
        pass


# ─── Module-level names (initialized lazily via init()) ──────────────
_INITIALIZED: bool = False
_secrets: SecretsBackend | None = None
audit: AuditLogger | None = None
log: logging.Logger | None = None

SSH_TIMEOUT: int = 90

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
    global SSH_TIMEOUT, AUDIT_HMAC_KEY

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
    _ensure_user_env()
    if USER_ENV_PATH.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(USER_ENV_PATH, override=False)
        except ImportError:
            pass

    try:
        _secrets = get_backend(project_root=str(PROJECT_ROOT))
    except Exception as _e:
        log.error("Falha ao inicializar secrets backend: %s \u2014 usando fallback env", _e)
        from huawei_manager.vault import EnvBackend
        _secrets = EnvBackend(env_path=USER_ENV_PATH if USER_ENV_PATH.exists() else PROJECT_ROOT / ".env")

    SSH_TIMEOUT = int(_s("SSH_TIMEOUT", "90"))

    AUDIT_HMAC_KEY = _s("AUDIT_HMAC_KEY", "")

    audit = AuditLogger(
        filename=str(PROJECT_ROOT / "logs" / "huawei_audit_structured.jsonl"),
        hmac_key=AUDIT_HMAC_KEY,
    )


def _s(key: str, default: str = "") -> str:
    """Lê um valor do backend de secrets com fallback para default."""
    if _secrets is None:
        return default
    return _secrets.get(key, default)
