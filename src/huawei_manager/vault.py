"""
vault.py — Bridge de compatibilidade.
Importa de huawei_manager.vault_backends para manter compatibilidade.
"""
from huawei_manager.vault_backends import (
    AWSBackend,
    CryptoEnvBackend,
    EnvBackend,
    SecretsBackend,
    SopsBackend,
    VaultBackend,
    _set_ts_path,
    get_backend,
    rotate_ssh_key,
)

__all__ = [
    "AWSBackend",
    "CryptoEnvBackend",
    "EnvBackend",
    "SecretsBackend",
    "SopsBackend",
    "VaultBackend",
    "_set_ts_path",
    "get_backend",
    "rotate_ssh_key",
]
