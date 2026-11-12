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

from netmiko.base_connection import (  # pyright: ignore[reportMissingTypeStubs]
    BaseConnection as NetmikoConnection,
)
from netmiko.exceptions import (  # pyright: ignore[reportMissingTypeStubs]
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from huawei_manager.audit_log import AuditLogger
from huawei_manager.basic_config.vrp_version import VrpVersion, detect_vrp_version
from huawei_manager.exceptions import (
    SdnAuthError,
    SdnCommandError,
    SdnConnectionError,
    SdnError,
    SdnValidationError,
)
from huawei_manager.sdn_controller.validator import CommandValidator, ValidationResult
from huawei_manager.security_redaction import redact_config_text, redact_secrets
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

    def send_config_block(
        self,
        commands: list[str],
        *,
        save: bool = False,
        allow_patterns: list[str] | None = None,
        secrets: list[str] | None = None,
        vrp_version: VrpVersion | None = None,
    ) -> tuple[bool, str]:
        """Aplica um bloco hierárquico em uma única sessão system-view.

        Implementação padrão conservadora para protocolos alternativos:
        delega ao ``send_config`` legado. ``SSHSouthbound`` sobrescreve com
        validação admin-only, ``cmd_verify=False`` e detecção de erros VRP.
        """
        return self.send_config(commands)

    def save_running_config(
        self, vrp_version: VrpVersion | None = None
    ) -> tuple[bool, str]:
        """Persiste a running-config na startup-config (visão exec).

        Separado de ``send_config_block`` para permitir o fluxo
        *aplica → verifica → persiste*: a persistência só deve ocorrer
        depois que a configuração foi confirmada no ``running-config``.
        """
        return False, "Backend não suporta persistência na startup-config."

    @abstractmethod
    def is_alive(self) -> bool:
        """Retorna True se a conexao esta ativa."""

    @abstractmethod
    def invalidate_connection(self) -> None:
        """Invalida o cache de conexao e marca como desconectado."""

    @abstractmethod
    def set_access_role(self, role: str) -> None:
        """Atualiza o papel de acesso usado pelo validator."""

    @abstractmethod
    def send_service_commands(
        self,
        commands: list[str],
        config_mode: bool = False,
        requires_privilege: bool = False,
    ) -> str:
        """Executa comandos de servico (show ou config) e retorna o output."""

    @property
    def connection(self) -> NetmikoConnection | None:
        """Handle Netmiko bruto da sessao ativa (somente leitura).

        Exposto apenas para o backend NAPALM reaproveitar a conexao SSH ja
        aberta (nenhuma segunda autenticacao, nenhum segredo novo manipulado).
        Padrao ``None`` (fail-closed): implementacoes que nao expoem a
        conexao seguem bloqueando o caminho NAPALM.
        """
        return None


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
        # Versão VRP detectada (cache por conexão) — usada para decidir
        # commit/save automático quando o chamador não informa.
        self._vrp_version: VrpVersion | None = None

    def detect_vrp_version(self) -> VrpVersion:
        """Detecta a versão VRP do device (cacheado até reconectar).

        Sem versão identificada assume-se ``UNKNOWN``, que
        :func:`requires_commit` trata como *commit obrigatório*
        (fail-closed) — melhor commitar do que deixar a configuração
        pendente no device.
        """
        if self._vrp_version is not None:
            return self._vrp_version
        try:
            output = self.send_command("display version")
        except Exception:
            # justificativa: a detecção é best-effort; falha aqui não pode
            # impedir a operação — o commit será assumido (fail-closed).
            output = ""
        text = output if isinstance(output, str) else ""
        version = detect_vrp_version(text)
        self._vrp_version = version
        return version

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
        self._vrp_version = None

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
        self._vrp_version = None

    @property
    def connection(self) -> NetmikoConnection | None:
        """Handle Netmiko bruto da sessao ativa (somente leitura).

        O backend NAPALM (``HW_BACKEND=napalm``) reutiliza essa conexao para
        preview/apply sem abrir um segundo SSH. Nao expoe credenciais — o
        objeto Netmiko as retira do ``SecretsBackend`` sob demanda.
        """
        return self._session.connection

    def set_access_role(self, role: str) -> None:
        """Atualiza o papel de acesso usado pelo validator."""
        self._access_role = role

    def send_command(
        self, command: str, read_timeout: int | None = None
    ) -> str:
        """Envia um comando show e retorna o output.

        Se um ``validator`` foi configurado, valida o comando antes
        de executar. Comandos negados disparam ``SdnAuthError``;
        falhas de execucao disparam ``SdnCommandError``.

        ``read_timeout`` opcional (segundos); None preserva o default do
        caminho manual (120s). O polling passa um valor menor por comando.
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
            if read_timeout is None:
                return self._session.run_cli_rpc(command)
            return self._session.run_cli_rpc(command, read_timeout=read_timeout)
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_command failed: %s", sanitized)
            raise SdnCommandError(sanitized) from exc

    def send_config(
        self, commands: list[str], save: bool = False
    ) -> tuple[bool, str]:
        """Envia comandos de configuracao.

        Se um ``validator`` foi configurado, valida cada comando
        individualmente antes de executar. Comandos negados disparam
        ``SdnAuthError``.

        Falhas de execucao nao levantam: retornam ``(False, mensagem)``
        com a mensagem sanitizada (sem credenciais).

        ``save=True`` persiste na startup-config (mudanca duradoura);
        por padrao a config e aplicada apenas na running-config.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        if self._validator is not None:
            for cmd in commands:
                vr = self._validator.validate(cmd, self._access_role)
                if not vr.allowed:
                    msg = f"Config denied by policy: {vr.reason}"
                    log.warning("send_config blocked: %s — %s", cmd[:60], vr.reason)
                    raise SdnAuthError(msg)
        config_text = "\n".join(commands)
        try:
            ok, msg = self._session.edit_config(config_text, target="running", save=save)
            # Sanitizar TAMBÉM o sucesso: a saída do device pode ecoar uma
            # senha configurada em outra etapa.
            return ok, redact_config_text(msg)
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("send_config failed: %s", sanitized)
            return False, sanitized

    def send_config_block(
        self,
        commands: list[str],
        *,
        save: bool = False,
        allow_patterns: list[str] | None = None,
        secrets: list[str] | None = None,
        vrp_version: VrpVersion | None = None,
    ) -> tuple[bool, str]:
        """Aplica um bloco de configuração admin-only em uma sessão única.

        Diferenças deliberadas em relação a ``send_config`` legado:

        * ``validate_config_block`` exige admin e rejeita separadores
          escondidos (``;``/``\\r``/``\\n`` dentro de uma linha);
        * o bloco inteiro vai para um único ``send_config_set``
          (``cmd_verify=False``), preservando a hierarquia VRP;
        * erros de sintaxe VRP são detectados e retornados como falha;
        * o commit/save é tratado automaticamente conforme a versão VRP
          detectada (VRP8: commit automático + save all virtual-systems;
          outras: save genérico);
        * segredos são redigidos na mensagem e no session log.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        if self._validator is not None:
            vr = self._validator.validate_config_block(
                commands, self._access_role, allow_patterns=allow_patterns
            )
            if not vr.allowed:
                msg = f"Config block denied by policy: {vr.reason}"
                log.warning("send_config_block blocked: %s", vr.reason)
                raise SdnAuthError(msg)
        if vrp_version is None:
            # Sem versão informada: detecta (cacheado) — o commit/save é
            # decidido automaticamente conforme a VRP do device.
            vrp_version = self.detect_vrp_version()
        config_text = "\n".join(commands)
        try:
            ok, msg = self._session.edit_config(
                config_text,
                target="running",
                save=save,
                cmd_verify=False,
                detect_errors=True,
                secrets=secrets,
                vrp_version=vrp_version,
            )
            return ok, redact_secrets(msg, secrets)
        except SdnError:
            raise
        except Exception as exc:
            sanitized = redact_secrets(str(exc), secrets)
            log.error("send_config_block failed: %s", sanitized)
            return False, sanitized

    def save_running_config(
        self, vrp_version: VrpVersion | None = None
    ) -> tuple[bool, str]:
        """Persiste a running-config na startup-config (visão exec).

        Executa ``save all virtual-systems`` (VRP8) ou ``save`` (demais VRP)
        fora do system-view e responde ``y`` ao prompt de confirmação.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        try:
            ok, msg = self._session.save_config(vrp_version)
        except SdnError:
            raise
        except Exception as exc:
            sanitized = _sanitize(str(exc))
            log.error("save_running_config failed: %s", sanitized)
            return False, sanitized
        return ok, msg

    def send_service_commands_detailed(
        self,
        commands: list[str],
        config_mode: bool = False,
        requires_privilege: bool = False,
        read_timeout: int | None = None,
    ) -> list[tuple[str, str]]:
        """Executa comandos de servico e devolve ``(comando, output)``.

        Mesma semantica de ``send_service_commands`` (system-view/quit,
        validacao, invalidacao da conexao em ``SdnError``), mas preserva a
        granularidade por comando. O polling adaptativo usa essa granularidade
        para distinguir um comando nao suportado pelo device (ex.: BGP/OSPF
        ausente) de uma falha real de conexao.
        """
        if not self._connected:
            raise SdnConnectionError("Not connected")
        # Configuração é um bloco hierárquico: um único send_config_set em
        # uma única sessão system-view. O caminho antigo enviava cada linha
        # separadamente e perdia o contexto (ex.: IP fora da interface).
        if config_mode:
            if not commands:
                return []
            _ok, msg = self.send_config_block(commands)
            return [(commands[0], msg)]

        need_sysview = requires_privilege
        if need_sysview:
            self._session.run_cli_rpc("system-view")

        results: list[tuple[str, str]] = []
        try:
            for cmd in commands:
                results.append(
                    (cmd, self.send_command(cmd, read_timeout=read_timeout))
                )
        except SdnError:
            self.invalidate_connection()
            raise
        finally:
            if need_sysview:
                self._session.run_cli_rpc("return")

        return results

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
        parts: list[str] = []
        for cmd, out in self.send_service_commands_detailed(
            commands,
            config_mode=config_mode,
            requires_privilege=requires_privilege,
        ):
            label = "Config applied" if config_mode else cmd
            parts.append(f">  {label}\n{'─' * 40}\n{out}")
        return "\n\n".join(parts)
