"""Southbound Abstraction Layer.

Define o protocolo abstrato ``SouthboundProtocol`` e a implementacao
``SSHSouthbound`` que wrappa ``NetmikoSession`` com retry, timeout,
e sanitizacao de credenciais em logs/exceptions.
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod

from huawei_manager.audit_log import AuditLogger
from huawei_manager.session import NetmikoSession
from huawei_manager.vault import SecretsBackend

log = logging.getLogger("huawei.southbound")

# Padrao para detectar credenciais em mensagens de erro
_CRED_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|auth)\s*['\"]?\S+['\"]?"
)


class SouthboundProtocol(ABC):
    """Interface abstrata para comunicacao southbound com dispositivos."""

    @abstractmethod
    def connect(self) -> None:
        """Estabelece conexao com o dispositivo."""

    @abstractmethod
    def disconnect(self) -> None:
        """Encerra a conexao com o dispositivo."""

    @abstractmethod
    def send_command(self, command: str) -> str:
        """Envia um comando show e retorna o output."""

    @abstractmethod
    def send_config(
        self, commands: list[str]
    ) -> tuple[bool, str]:
        """Envia comandos de configuracao. Retorna (sucesso, mensagem)."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Retorna True se a conexao esta ativa."""


def _sanitize(msg: str) -> str:
    """Substitui valores suspeitos de serem credenciais por ``[REDACTED]``."""
    return _CRED_PATTERN.sub(r"\1 [REDACTED]", msg)


class SSHSouthbound(SouthboundProtocol):
    """Implementacao southbound via SSH/Netmiko com retry e timeout.

    Args:
        backend: Backend de secrets para credenciais.
        audit_logger: Logger de auditoria.
        timeout: Timeout de conexao em segundos (padrao 30).
        max_retries: Numero maximo de tentativas de conexao (padrao 2).
    """

    def __init__(
        self,
        backend: SecretsBackend,
        audit_logger: AuditLogger,
        timeout: int = 30,
        max_retries: int = 2,
    ) -> None:
        self._session = NetmikoSession(backend, audit_logger)
        self._timeout = timeout
        self._max_retries = max_retries
        self._connected = False

    def connect(self) -> None:
        """Tenta conectar com retry em caso de falha transiente."""
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._session.connect(timeout=self._timeout)
                self._connected = True
                return
            except Exception as exc:
                sanitized = _sanitize(str(exc))
                log.warning(
                    "Connect attempt %d/%d failed: %s",
                    attempt, self._max_retries, sanitized,
                )
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(1.0 * attempt)  # backoff simples
        msg = f"After {self._max_retries} retries, connect failed"
        if last_exc:
            raise RuntimeError(
                f"{msg}: {_sanitize(str(last_exc))}"
            ) from last_exc
        raise RuntimeError(msg)

    def disconnect(self) -> None:
        """Encerra a sessao SSH."""
        self._session.disconnect()
        self._connected = False

    def is_alive(self) -> bool:
        """Retorna True se a sessao esta conectada."""
        return self._connected

    def send_command(self, command: str) -> str:
        """Envia um comando show e retorna o output."""
        if not self._connected:
            raise RuntimeError("Not connected")
        try:
            return self._session.run_cli_rpc(command)
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_command failed: %s", sanitized)
            raise RuntimeError(sanitized) from exc

    def send_config(
        self, commands: list[str]
    ) -> tuple[bool, str]:
        """Envia comandos de configuracao."""
        if not self._connected:
            raise RuntimeError("Not connected")
        config_text = "\n".join(commands)
        try:
            ok, msg = self._session.edit_config(config_text, target="running")
            return ok, _sanitize(msg) if not ok else msg
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_config failed: %s", sanitized)
            return False, sanitized
