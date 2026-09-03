"""Southbound Abstraction Layer.

Define o protocolo abstrato ``SouthboundProtocol`` e a implementacao
``SSHSouthbound`` que wrappa ``NetmikoSession`` com retry, timeout,
e sanitizacao de credenciais em logs/exceptions.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from abc import ABC, abstractmethod

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from huawei_manager.audit_log import AuditLogger
from huawei_manager.exceptions import (
    SdnAuthError,
    SdnCommandError,
    SdnConnectionError,
    SdnValidationError,
)
from huawei_manager.sdn_controller.validator import CommandValidator, ValidationResult
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
        timeout: Timeout de conexao em segundos (padrao: _config.SSH_TIMEOUT).
        max_retries: Numero maximo de tentativas de conexao (padrao 2).
        session: Sessao Netmiko existente (opcional).
        validator: Validador de comandos (opcional).
        access_role: Papel de acesso usado pelo validator (padrao "user").
    """

    def __init__(
        self,
        backend: SecretsBackend,
        audit_logger: AuditLogger,
        timeout: int | None = None,
        max_retries: int = 2,
        session: NetmikoSession | None = None,
        validator: CommandValidator | None = None,
        access_role: str = "user",
    ) -> None:
        if timeout is None:
            from huawei_manager._config import SSH_TIMEOUT
            timeout = SSH_TIMEOUT
        self._session = session if session is not None else NetmikoSession(backend, audit_logger)
        self._timeout = timeout
        self._max_retries = max_retries
        self._connected = False
        self._alive_cache: tuple[bool, float] = (False, 0.0)
        self._lock = threading.Lock()
        self._validator = validator
        self._access_role = access_role

    def connect(self) -> None:
        """Tenta conectar com retry em caso de falha transiente.

        Exceções determinísticas (SdnValidationError, NetmikoAuthenticationException)
        propagam imediatamente sem retry.
        NetmikoTimeoutException faz retry e, ao esgotar, relança o tipo original.
        Outras exceções fazem retry e wrap em SdnConnectionError.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._session.connect(timeout=self._timeout)
                with self._lock:
                    self._connected = True
                    self._alive_cache = (True, time.time())
                return
            except SdnValidationError:
                # Erro determinístico de config — sem retry, sem wrap
                raise
            except NetmikoAuthenticationException:
                # Credencial inválida não muda em 1s — sem retry, sem wrap
                raise
            except NetmikoTimeoutException as exc:
                # Transiente — faz retry, mas ao esgotar relança tipo original
                sanitized = _sanitize(str(exc))
                log.warning(
                    "Connect attempt %d/%d failed: %s",
                    attempt, self._max_retries, sanitized,
                )
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(1.0 * attempt)
            except Exception as exc:
                # Genérico — retry + wrap em SdnConnectionError
                sanitized = _sanitize(str(exc))
                log.warning(
                    "Connect attempt %d/%d failed: %s",
                    attempt, self._max_retries, sanitized,
                )
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(1.0 * attempt)

        # Retries esgotados
        if isinstance(last_exc, NetmikoTimeoutException):
            raise last_exc  # tipo original
        msg = f"After {self._max_retries} retries, connect failed"
        if last_exc:
            raise SdnConnectionError(
                f"{msg}: {_sanitize(str(last_exc))}"
            ) from last_exc
        raise SdnConnectionError(msg)

    def disconnect(self) -> None:
        """Encerra a sessao SSH."""
        self._session.disconnect()
        with self._lock:
            self._connected = False
            self._alive_cache = (False, time.time())

    def is_alive(self) -> bool:
        """Retorna True se a sessao esta conectada (com cache de 2s).

        Usa cache para evitar I/O de rede na main thread
        (chamado pelo dashboard timer a cada 5s).
        Delegado a NetmikoSession.is_connected() que verifica
        o estado real da conexao.
        """
        with self._lock:
            now = time.time()
            if now - self._alive_cache[1] < 2.0:
                return self._alive_cache[0]
        alive = self._session.is_connected
        with self._lock:
            self._alive_cache = (alive, time.time())
            self._connected = alive
        return alive

    def invalidate_connection(self) -> None:
        """Invalida o cache de conexao e marca como desconectado.

        Chamado apos detectar que a sessao SSH esta morta
        (ex: RuntimeError em send_command/send_config).
        """
        with self._lock:
            self._alive_cache = (False, time.time())
            self._connected = False

    def set_access_role(self, role: str) -> None:
        """Atualiza o papel de acesso usado pelo validator."""
        self._access_role = role

    def send_command(self, command: str) -> str:
        """Envia um comando show e retorna o output.

        Se um ``validator`` foi configurado, valida o comando antes
        de executar. Comandos negados disparam ``RuntimeError``.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        if self._validator is not None:
            vr: ValidationResult = self._validator.validate(command, self._access_role)
            if not vr.allowed:
                msg = f"Command denied by policy: {vr.reason}"
                log.warning("send_command blocked: %s — %s", command[:60], vr.reason)
                raise SdnAuthError(msg)
        try:
            return self._session.run_cli_rpc(command)
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_command failed: %s", sanitized)
            raise SdnCommandError(sanitized) from exc

    def send_config(
        self, commands: list[str]
    ) -> tuple[bool, str]:
        """Envia comandos de configuracao.

        Se um ``validator`` foi configurado, valida cada comando
        antes de executar. Comandos negados disparam ``RuntimeError``.
        A validacao e feita no comando completo (join por newline).
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        if self._validator is not None:
            full_cmd = "\n".join(commands)
            vr = self._validator.validate(full_cmd, self._access_role)
            if not vr.allowed:
                msg = f"Config denied by policy: {vr.reason}"
                log.warning("send_config blocked: %s — %s", full_cmd[:60], vr.reason)
                raise SdnAuthError(msg)
        config_text = "\n".join(commands)
        try:
            ok, msg = self._session.edit_config(config_text, target="running")
            return ok, _sanitize(msg) if not ok else msg
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_config failed: %s", sanitized)
            return False, sanitized

    def send_service_commands(
        self,
        commands: list[str],
        config_mode: bool = False,
        requires_privilege: bool = False,
    ) -> str:
        """Executa comandos de servico (show ou config) com suporte a
        system-view/quit, ideal para o catalogo de servicos.

        Args:
            commands: Lista de comandos a executar.
            config_mode: Se True, entra em system-view antes e sai apos.
            requires_privilege: Se True, entra em system-view (igual).

        Returns:
            Output concatenado dos comandos executados.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        need_sysview = config_mode or requires_privilege

        if need_sysview:
            self._session.run_cli_rpc("system-view")

        parts: list[str] = []
        for cmd in commands:
            if config_mode:
                ok, msg = self.send_config([cmd])
                parts.append(f">  Config applied:\n{'─' * 40}\n{msg}")
            else:
                out = self.send_command(cmd)
                parts.append(f">  {cmd}\n{'─' * 40}\n{out}")

        if need_sysview:
            self._session.run_cli_rpc("quit")

        return "\n\n".join(parts)
