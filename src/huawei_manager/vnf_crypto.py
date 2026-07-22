"""vnf_crypto.py — Fernet encryption helpers for VNF secrets."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from huawei_manager import _config

log = logging.getLogger("huawei.topology")


def _get_fernet_encrypt() -> Fernet:
    """Retorna Fernet para *criptografia* — exige VNF_ENCRYPT_KEY, SEM fallback.

    Se VNF_ENCRYPT_KEY nao estiver configurada, dados sensiveis serao
    salvos em plaintext (log.warning).
    """
    raw = _config._s("VNF_ENCRYPT_KEY")
    if not raw:
        log.warning(
            "VNF_ENCRYPT_KEY nao configurada — senhas/chaves VNF "
            "serao salvas em plaintext! "
            "Defina VNF_ENCRYPT_KEY no .env (gere com: "
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
    """Retorna Fernet para *descriptografia* — tenta VNF_ENCRYPT_KEY,
    depois fallback HMAC (compatibilidade reversa com dados antigos)."""
    raw = _config._s("VNF_ENCRYPT_KEY")
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception:
            log.warning("VNF_ENCRYPT_KEY invalida, tentando fallback HMAC")
            raw = ""
    if not raw:
        raw = _config._s("AUDIT_HMAC_KEY", "")
    if raw:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))
    return None


def _encrypt_val(text: str) -> str:
    """Criptografa valor com VNF_ENCRYPT_KEY.

    Se a chave nao existir (ValueError), retorna plaintext com log.warning
    (design intencional — aceita chave opcional).
    Se a chave existir mas a criptografia falhar, PROPAGA o erro (fail fast).
    """
    try:
        f = _get_fernet_encrypt()
    except ValueError:
        return text
    try:
        return f.encrypt(text.encode()).decode()
    except Exception as exc:
        log.error("Falha ao criptografar senha VNF: %s", exc)
        raise


def _decrypt_val(enc: str) -> str:
    """Descriptografa valor; tenta VNF_ENCRYPT_KEY, fallback HMAC."""
    f = _get_fernet_decrypt()
    if f is None:
        log.warning("VNF_ENCRYPT_KEY ausente — dados descriptografados em plaintext")
        return enc
    try:
        return f.decrypt(enc.encode()).decode()
    except Exception:
        log.warning("Falha ao decriptar senha VNF — usando valor original")
        return enc
