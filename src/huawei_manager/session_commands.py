from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, cast

from huawei_manager.basic_config.vrp_version import (
    VrpVersion,
    requires_commit,
    save_command,
)
from huawei_manager.exceptions import SdnCommandError, SdnConnectionError
from huawei_manager.sdn_controller.vrp_errors import detect_vrp_errors
from huawei_manager.security_redaction import redact_secrets
from huawei_manager.session_helpers import resolve_filter
from huawei_manager.utils import clean_output, sanitize_command

if TYPE_CHECKING:
    import threading

    from netmiko.base_connection import BaseConnection as NetmikoConnection  # pyright: ignore[reportMissingTypeStubs]

    from huawei_manager.audit_log import AuditLogger

log = logging.getLogger("huawei.session")

# Padrões de prompt interativo do dispositivo VRP que exigem confirmação [Y/N].
# Inclui o formato do NE40E/VRP8: "[Y(yes)/N(no)/C(cancel)]".
_INTERACTIVE_PROMPT_RE = re.compile(
    r"\[Y/N\]|\[Y\(yes\)/N\(no\)/C\(cancel\)\]|\[Y\(yes\)/N\(no\)\]|Please choose|confirm|\[yes/no\]",
    re.IGNORECASE,
)

# Linhas que são apenas eco/resposta de prompt interativo e não erros reais
# de configuração. São filtradas antes de passar por detect_vrp_errors.
_INTERACTIVE_NOISE_RE = re.compile(
    r"\[Y/N\]|\[Y\(yes\)/N\(no\)/C\(cancel\)\]|\[Y\(yes\)/N\(no\)\]|Please choose|Error: Please choose|Press enter",
    re.IGNORECASE,
)

# Erros de transporte/prompt do Netmiko que indicam que a sessão perdeu o
# padrão de prompt (ex.: device saiu do config mode de forma inesperada).
_NETMIKO_PROMPT_ERROR_RE = re.compile(
    r"pattern not detected|pattern not found|timed out|connection.*closed",
    re.IGNORECASE,
)


class SessionCommandsMixin:
    """Mixin for NetmikoSession command execution methods."""

    if TYPE_CHECKING:
        # Membros do NetmikoSession (self é implícito: a classe precisa deles
        # declarados; NetmikoSession não é supertipo do mixin, então self
        # anotado com a classe concreta é rejeitado pelo pyright).
        _conn: NetmikoConnection | None
        _lock: threading.Lock
        _audit: AuditLogger

        @property
        def _host(self) -> str: ...

        @property
        def _user(self) -> str: ...

        @property
        def _session_id(self) -> str | None: ...

        def _protect_session_log(self, secrets: Iterable[str] | None = None) -> None: ...

        def _write_raw(self, data: str) -> None: ...

        def _read_raw_timing(self) -> str: ...

    # ── executa comando CLI ──────────────────────────────────────────
    def _cmd(self, command: str, read_timeout: int = 120) -> str:
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        try:
            out = self._conn.send_command(command, read_timeout=read_timeout)
            return clean_output(str(out))
        except Exception as e:
            log.exception("Comando falhou: %s", command)
            raise SdnCommandError(sanitize_command(str(e))) from e

    def run_cli_timing(self, cmd: str) -> str:
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-timing", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                out = self._conn.send_command_timing(cmd, read_timeout=120)
                ctx.set_status("ok")
                return clean_output(str(out))

    # ── get config via CLI ────────────────────────────────────────────
    def get_config(
        self,
        filter_xml: str | None = None,
        source: str = "running",
    ) -> str:
        cmd = resolve_filter(filter_xml) or "display current-configuration"
        with self._lock:
            with self._audit.timed(
                "get-config", user=self._user, host=self._host,
                datastore=source, session_id=self._session_id,
            ) as ctx:
                result = self._cmd(cmd)
                ctx.set_status("ok")
                return result

    # ── get estado operacional via CLI ────────────────────────────────
    def get(self, filter_xml: str | None = None) -> str:
        cmd = resolve_filter(filter_xml) or "display ip routing-table"
        with self._lock:
            with self._audit.timed(
                "get", user=self._user, host=self._host,
                session_id=self._session_id,
            ) as ctx:
                result = self._cmd(cmd)
                ctx.set_status("ok")
                return result

    # ── edit config via CLI ───────────────────────────────────────────
    def edit_config(
        self,
        config: str,
        target: str = "running",
        save: bool = False,
        *,
        cmd_verify: bool = True,
        read_timeout: int = 120,
        detect_errors: bool = False,
        secrets: Iterable[str] | None = None,
        vrp_version: VrpVersion | None = None,
    ) -> tuple[bool, str]:
        """Aplica um bloco de configuração em uma única sessão system-view.

        O caminho de configuração básica usa ``detect_errors=True``: a saída
        é limpa, segredos são redigidos e qualquer marcador de erro VRP
        transforma o resultado em falha.

        ``cmd_verify=False`` é necessário em blocos que contêm senha: o
        device mascara o comando ecoado e a verificação exata do Netmiko
        esperaria para sempre.

        Fluxo canônico (VRP8/NE40E):

        1. ``send_config_set`` com todo o bloco (system-view).
        2. Saída do system-view via ``Ctrl+Z`` (byte bruto \\x1a) — nunca
           ``send_command("return")``, porque o prompt de commit do VRP8
           quebra o prompt matching do Netmiko.
        3. Se VRP8 (``requires_commit``): responde ``y\\n`` ao prompt
           ``[Y(yes)/N(no)/C(cancel)]`` → commit.
        4. Se ``save=True``: envia ``save_cmd`` em exec view (fora do
           system-view) e responde ``y\\n`` ao prompt de confirmação → save.
        5. Nunca salva se commit não foi confirmado.
        """
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        save_cmd = save_command(vrp_version) if vrp_version is not None else "save"
        commit_required = requires_commit(vrp_version) if vrp_version is not None else False

        with self._lock:
            with self._audit.timed(
                "edit-config", user=self._user, host=self._host,
                datastore=target, session_id=self._session_id,
            ) as ctx:
                lines = [line.strip() for line in config.splitlines() if line.strip()]
                if detect_errors:
                    self._protect_session_log(secrets)
                try:
                    # ── 1. Bloco de configuração no system-view ──
                    output = cast(
                        str,
                        clean_output(
                            str(
                                self._conn.send_config_set(
                                    lines,
                                    read_timeout=read_timeout,
                                    cmd_verify=cmd_verify,
                                    exit_config_mode=False,
                                )
                            )
                        ),
                    )

                    # ── Detecção imediata de erros VRP no bloco enviado ──
                    # Se o próprio bloco de configuração foi rejeitado, não
                    # prossegue para saída/save. Ainda tenta deixar o device
                    # em exec view (best effort) antes de retornar o erro.
                    if detect_errors:
                        output_for_check = redact_secrets(output, secrets)
                        errors = detect_vrp_errors(output_for_check)
                        if errors:
                            try:
                                self._write_raw("\x1a")
                                self._read_raw_timing()
                            except Exception:
                                pass
                            ctx.set_status("error")
                            return False, (
                                "Configuração recusada pela VRP: "
                                + "; ".join(errors[:5])
                            )

                    # ── 2. Saída do system-view via Ctrl+Z (byte bruto) ──
                    # Ctrl+Z é alias de 'return' na VRP, mas enviado como byte
                    # cru não depende de prompt matching — funciona mesmo quando
                    # o device responde com o prompt de commit em vez do prompt
                    # de exec view.
                    try:
                        self._write_raw("\x1a")
                        exit_output = cast(str, self._read_raw_timing())
                    except Exception:
                        # Fallback: se o canal bruto falhar, tenta 'return'
                        # e depois 'quit' via send_command (prompt matching).
                        try:
                            exit_output = self._conn.send_command(
                                "return", read_timeout=read_timeout
                            )
                        except Exception:
                            try:
                                exit_output = self._conn.send_command(
                                    "quit", read_timeout=read_timeout
                                )
                            except Exception:
                                self._exit_config_best_effort()
                                raise
                    output += "\n" + cast(str, exit_output)

                    # ── 3. Commit VRP8 (configs não-commitadas) ──
                    # O Ctrl+Z dispara o mesmo prompt que 'return':
                    # "[Y(yes)/N(no)/C(cancel)]". Responder 'y' commita.
                    # O prompt pode aparecer tanto na saída do send_config_set
                    # (se o Netmiko sair do config mode automaticamente) quanto
                    # na saída do Ctrl+Z — por isso verificamos a saída combinada.
                    # Se não houver prompt de commit, nada a confirmar (commit_confirmed=True).
                    commit_confirmed = True
                    if commit_required and _INTERACTIVE_PROMPT_RE.search(output):
                        commit_response = self._conn.send_command_timing(
                            "y\n", read_timeout=read_timeout
                        )
                        commit_response_clean = clean_output(str(commit_response))
                        output += "\n" + commit_response_clean
                        # Commit confirmado somente se, após 'y', não houver mais
                        # prompt interativo (i.e. estamos na exec view).
                        commit_confirmed = not bool(
                            _INTERACTIVE_PROMPT_RE.search(commit_response_clean)
                        )

                    # ── 4. Save na startup-config (apenas em exec view) ──
                    if save:
                        if not commit_confirmed:
                            ctx.set_status("error")
                            return False, (
                                "Commit não confirmado — save cancelado para evitar "
                                "persistir configuração parcial."
                            )
                        try:
                            save_output = self._conn.send_command_timing(
                                save_cmd, read_timeout=read_timeout
                            )
                            save_output_clean = clean_output(str(save_output))
                            output += "\n" + save_output_clean
                            # Responder 'y' ao prompt de confirmação do save
                            if _INTERACTIVE_PROMPT_RE.search(save_output_clean):
                                save_response = self._conn.send_command_timing(
                                    "y\n", read_timeout=read_timeout
                                )
                                output += "\n" + clean_output(str(save_response))
                            if detect_errors:
                                save_output_clean = redact_secrets(
                                    save_output_clean, secrets
                                )
                                save_errors = detect_vrp_errors(save_output_clean)
                                if save_errors:
                                    ctx.set_status("error")
                                    return False, (
                                        "Configuração aplicada, mas save falhou: "
                                        + "; ".join(save_errors[:5])
                                    )
                        except Exception:
                            if detect_errors:
                                self._exit_config_best_effort()
                            raise

                    # ── Detecção de erros VRP na saída combinada ──
                    clean = clean_output(str(output))
                    if detect_errors:
                        clean = redact_secrets(clean, secrets)
                        clean_for_error_check = "\n".join(
                            line
                            for line in clean.splitlines()
                            if not _INTERACTIVE_NOISE_RE.search(line)
                        )
                        errors = detect_vrp_errors(clean_for_error_check)
                        if errors:
                            ctx.set_status("error")
                            return False, (
                                "Configuração recusada pela VRP: "
                                + "; ".join(errors[:5])
                            )
                    ctx.set_status("ok")
                    saved = " e salva" if save else " (running-config)"
                    return True, f"OK Configuracao aplicada{saved}\n{clean}"
                except Exception as exc:
                    # Cleanup sempre: tenta sair do system-view antes de propagar.
                    self._exit_config_best_effort()
                    exc_text = str(exc)
                    if _NETMIKO_PROMPT_ERROR_RE.search(exc_text):
                        sanitized = sanitize_command(exc_text) or exc_text
                        log.warning(
                            "send_config_set falhou (prompt não detectado): %s",
                            sanitized,
                        )
                        return False, (
                            "Falha de comunicação com o device: "
                            f"{sanitized}. "
                            "Verifique se o dispositivo está acessível e "
                            "se o prompt de comando é o esperado."
                        )
                    raise

    def save_config(
        self, vrp_version: VrpVersion | None = None
    ) -> tuple[bool, str]:
        """Persiste a running-config na startup-config (visão exec).

        Usado pelo fluxo que **verifica antes de persistir**: a configuração
        é aplicada (e commitada no VRP8) primeiro; só depois de confirmada
        no ``running-config`` a persistência é solicitada.

        O comando é ``save all virtual-systems`` (VRP8) ou ``save`` (demais
        VRP), executado **fora** do system-view, com resposta ``y`` ao
        prompt de confirmação ``[Y/N]``.
        """
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        cmd = save_command(vrp_version) if vrp_version is not None else "save"
        with self._lock:
            try:
                raw = self._conn.send_command_timing(cmd, read_timeout=120)
            except Exception as exc:
                sanitized = sanitize_command(str(exc)) or str(exc)
                log.warning("save falhou: %s", sanitized)
                return False, f"Falha ao salvar a configuração: {sanitized}"
            output = clean_output(str(raw))
            if _INTERACTIVE_PROMPT_RE.search(output):
                try:
                    answer = self._conn.send_command_timing("y\n", read_timeout=120)
                    output += "\n" + clean_output(str(answer))
                except Exception as exc:
                    sanitized = sanitize_command(str(exc)) or str(exc)
                    log.warning("confirmacao de save falhou: %s", sanitized)
                    return False, (
                        f"Falha ao confirmar o save: {sanitized}"
                    )
            errors = detect_vrp_errors(output)
            if errors:
                return False, (
                    "Save recusado pela VRP: " + "; ".join(errors[:5])
                )
            return True, f"Configuração salva na startup-config ({cmd})."

    def _exit_config_best_effort(self) -> None:
        """Tenta sair do system-view após uma exceção de envio."""
        try:
            conn = self._conn
            if conn is None:
                return
            check = getattr(conn, "check_config_mode", None)
            if callable(check) and check():
                conn.exit_config_mode()
        except Exception:  # justificativa: cleanup nunca mascara o erro original
            log.exception("Falha ao sair do config mode")

    # ── comando CLI livre ─────────────────────────────────────────────
    def run_cli_rpc(self, cmd: str, read_timeout: int = 120) -> str:
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-rpc", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                result = self._cmd(cmd, read_timeout)
                ctx.set_status("ok")
                return result
