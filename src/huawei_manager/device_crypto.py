"""device_crypto.py — Fernet encryption helpers for device secrets.

Fail-closed: nunca degradar para plaintext.
- ``_encrypt_val`` propaga ``ValueError`` se VNF_ENCRYPT_KEY nao existir.
- ``_decrypt_val`` propaga erro se a chave nao existir ou o ciphertext
  for invalido. Fallback HMAC (AUDIT_HMAC_KEY) foi descontinuado.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet

from huawei_manager import _config

log = logging.getLogger("huawei.topology")


def _get_fernet_encrypt() -> Fernet:
    """Retorna Fernet para *criptografia* — exige VNF_ENCRYPT_KEY, SEM fallback.

    Raises:
        ValueError: Se VNF_ENCRYPT_KEY nao estiver configurada.
    """
    raw = _config._s("VNF_ENCRYPT_KEY")
    if not raw:
        log.warning(
            "VNF_ENCRYPT_KEY nao configurada — segredos Device nao serao salvos "
            "(fail-closed). Defina VNF_ENCRYPT_KEY no .env (gere com: "
            "python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\")"
        )
        raise ValueError("VNF_ENCRYPT_KEY nao configurada")
    try:
        return Fernet(raw.encode())
    except Exception as exc:
        log.warning("VNF_ENCRYPT_KEY invalida: %s", exc)
        raise


def _get_fernet_decrypt() -> Fernet | None:
    """Retorna Fernet para *descriptografia* — apenas VNF_ENCRYPT_KEY.

    Fallback HMAC (via AUDIT_HMAC_KEY) foi descontinuado por seguranca:
    se a chave nao existir ou for invalida, retorna ``None`` e o
    chamador deve falhar em vez de degradar silenciosamente.
    """
    raw = _config._s("VNF_ENCRYPT_KEY")
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except Exception:
        log.warning("VNF_ENCRYPT_KEY invalida")
        return None


def _encrypt_val(text: str) -> str:
    """Criptografa valor com VNF_ENCRYPT_KEY — fail-closed.

    Raises:
        ValueError: Se a chave nao existir (nunca salva plaintext).
    """
    f = _get_fernet_encrypt()
    try:
        return f.encrypt(text.encode()).decode()
    except Exception as exc:
        log.error("Falha ao criptografar senha Device: %s", exc)
        raise


def _decrypt_val(enc: str) -> str:
    """Descriptografa valor com VNF_ENCRYPT_KEY — fail-closed.

    Raises:
        ValueError: Se VNF_ENCRYPT_KEY nao estiver configurada.
        cryptography.fernet.InvalidToken: Se o ciphertext for invalido
            (chave errada ou dado corrompido).

    Nunca retorna ciphertext tratado como plaintext.
    """
    f = _get_fernet_decrypt()
    if f is None:
        raise ValueError(
            "VNF_ENCRYPT_KEY nao configurada — impossivel descriptografar segredo Device"
        )
    try:
        return f.decrypt(enc.encode()).decode()
    except Exception as exc:
        log.error("Falha ao descriptografar senha Device: %s", exc)
        raise


def ensure_encrypt_key() -> str:
    """Garante VNF_ENCRYPT_KEY: gera e persiste no secrets backend se ausente.

    Raises:
        RuntimeError: Se a persistência falhar (fail-closed explícito).
    """
    raw = _config._s("VNF_ENCRYPT_KEY")
    if raw:
        return raw

    key = Fernet.generate_key().decode()

    if _config._secrets is None:
        raise RuntimeError("secrets backend nao inicializado")

    try:
        _config._secrets.put("VNF_ENCRYPT_KEY", key)
    except Exception as exc:
        log.warning("VNF_ENCRYPT_KEY gerada mas nao persistida (%s) — fail-closed mantido", exc)
        raise

    log.info("VNF_ENCRYPT_KEY gerada e persistida no secrets backend")
    return key
