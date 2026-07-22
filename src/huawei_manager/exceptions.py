"""Hierarquia de exceções do Huawei Manager.

Todas as exceções do sistema herdam de ``SdnError``, permitindo que
camadas superiores capturem qualquer erro específico do domínio sem
depender de exceções genéricas do Python.
"""

from __future__ import annotations


class SdnError(Exception):
    """Base de todas as exceções do Huawei Manager."""


class SdnConnectionError(SdnError):
    """Falha de conexão com o dispositivo (SSH, rede, timeout)."""


class SdnAuthError(SdnError):
    """Falha de autenticação ou autorização."""


class SdnCommandError(SdnError):
    """Falha na execução de um comando CLI."""


class SdnConfigError(SdnError):
    """Falha na aplicação de configuração no dispositivo."""


class SdnValidationError(SdnError):
    """Falha de validação de dados, credenciais ou parâmetros."""
