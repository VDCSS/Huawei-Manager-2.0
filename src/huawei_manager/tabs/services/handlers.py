"""Execução de serviços — handlers da aba Serviços (F2-services).

Extraído de ``handlers/services.py`` (``ServicesMixin``, a última mixin
grande) do plano ``plano-abas-independentes.md``: a classe injetada
:class:`ServicesHandlers` ``(ctx, state)`` lê só o :class:`TabContext`
e escreve via ``_ui.write``/``_ui.loading`` (agendamento na thread GUI
vem do ``dispatch`` do TabContext).
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from huawei_manager.audit_log import AuditLogger
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SnapshotError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_NAPALM,
    NapalmVRPBackend,
    resolve_backend,
)
from huawei_manager.sdn_controller.validator import _DEFAULT_DENY_PATTERNS
from huawei_manager.services import ServiceDef, execute_service
from huawei_manager.services.ui_bridge import ask_from_worker
from huawei_manager.tabs import _ui
from huawei_manager.utils import sanitize_command

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.services.state import ServicesState

log = logging.getLogger(__name__)


def _template_to_pattern(tpl: str) -> re.Pattern[str]:
    """Converte um template de serviço em regex de allowlist.

    Placeholders ``<x>`` viram ``.+`` (aceitam valores multi-word, ex.:
    ``description <text>``); o texto literal é escapado.
    O template pode conter ``|`` como alternância de comandos possíveis
    (ex.: ``"shutdown | undo shutdown"``).
    """
    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"<[^>]*>", tpl):
        parts.append(re.escape(tpl[pos:m.start()]))
        parts.append(r".+")
        pos = m.end()
    parts.append(re.escape(tpl[pos:]))
    return re.compile(r"^" + "".join(parts) + r"\s*$", re.IGNORECASE)


def _build_service_allow_patterns(svc: ServiceDef) -> list[re.Pattern[str]]:
    """Monta a allowlist a partir do template (description) e comandos concretos.

    Cada template entra como padrão literal (``<x>`` → ``.+``) E é quebrado em
    ``|`` como alternância de comandos possíveis (ex.: ``"shutdown | undo
    shutdown"``). O padrão literal é necessário para templates que usam ``|``
    como filtro de CLI (ex.: ``display current-configuration | include sysname``),
    onde a quebra por ``|`` produziria alternativas inúteis.
    """
    patterns: list[re.Pattern[str]] = []
    for tpl in [svc.description, *svc.cli_commands]:
        patterns.append(_template_to_pattern(tpl))
        for alt in tpl.split("|"):
            alt = alt.strip()
            if alt:
                patterns.append(_template_to_pattern(alt))
    return patterns


def _audit_napalm_blocked(audit: AuditLogger | None, *, user: str,
                          host: str, session_id: str | None,
                          service: str, reason: str) -> None:
    """Registra no AuditLogger um bloqueio do caminho NAPALM.

    Preserva o schema de auditoria (``op``/``user``/``host``/``status``/
    ``session_id``/``category``); ``reason``/``backend``/``service`` entram no
    ``extra``. Auditoria nunca pode derrubar a operação (fail-closed).
    """
    if audit is None:
        return
    try:
        audit.log_operation(
            "config_apply",
            user=user,
            host=host,
            status="blocked",
            session_id=session_id,
            category="config",
            backend=BACKEND_NAPALM,
            service=service,
            reason=reason,
        )
    except Exception:  # justificativa: auditoria nunca derruba a operação
        log.exception("audit de bloqueio NAPALM falhou")


class ServicesHandlers:
    """Execução de serviços (mock/cli/NAPALM) — só TabContext + ServicesState."""

    def __init__(self, ctx: TabContext, state: ServicesState) -> None:
        self._ctx = ctx
        self._state = state

    def run_service(self, svc: ServiceDef,
                    final_svc: ServiceDef | None = None) -> None:
        """Executa um servico no modo mock ou cli, com substituicao de parametros e sanitizacao."""
        _DENY_COMPILED = [re.compile(p, re.IGNORECASE)
                          for p in _DEFAULT_DENY_PATTERNS]
        _DENY_COMPILED = _DENY_COMPILED + [
            re.compile(r"^shutdown(?:\s|$)", re.IGNORECASE)]
        prova_cmds = [final_svc.cli_commands] if final_svc else [svc.cli_commands]
        destrutivo = svc.config_mode and any(
            p.search(cmd) for cmds in prova_cmds for cmd in cmds
            for p in _DENY_COMPILED
        )
        if destrutivo:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "Confirmar operação destrutiva",
                f"O serviço '{svc.name}' executa: {chr(10).join(svc.cli_commands)}\n\n"
                "Continuar?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                _ui.write(self._state.output, "Operação cancelada pelo usuário.",
                          self._ctx.dispatch)
                return

        mode = self._ctx.svc_mode()
        device = self._ctx.device()
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if device:
            label += f"  |  Alvo: {device.name} ({device.host})"
        device_lbl = self._state.device_lbl
        if device_lbl is not None:
            device_lbl.setText(label)

        _REJECT_PARAM = re.compile(r"[;&|`$(){}]")

        final_svc = svc
        if svc.config_mode and self._state.param_entries:
            cmd = svc.description
            # Substituição posicional: usa o texto REAL do placeholder (ex.:
            # `<permit|deny>`, que o label de UI exibe como `permit/deny`) e
            # substitui apenas a 1ª ocorrência de cada um, preservando
            # placeholders repetidos (ex.: dois `<ip>` em NAT server).
            placeholders = re.findall(r"<[^>]+>", cmd)
            entries = list(self._state.param_entries.values())
            if len(placeholders) != len(entries):
                _ui.write(
                    self._state.output,
                    "✘  Servico inconsistente: "
                    f"{len(placeholders)} placeholder(s) para {len(entries)} "
                    "campo(s). Nada foi executado.",
                    self._ctx.dispatch)
                return
            for placeholder, entry in zip(placeholders, entries):
                val = entry.text().strip()
                if _REJECT_PARAM.search(val):
                    _ui.write(
                        self._state.output,
                        f"✘  Parametro '{placeholder}' contem caracteres "
                        "invalidos (& ; | ` $ ( ) { }).",
                        self._ctx.dispatch)
                    return
                cmd = cmd.replace(placeholder, val, 1)
            final_svc = ServiceDef(
                id=svc.id, name=svc.name, description=svc.description,
                category=svc.category, device_types=svc.device_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        rejected = self.validate_service(svc, final_svc.cli_commands)
        if rejected:
            for cmd, reason in rejected:
                _ui.write(self._state.output,
                          f"✘  Comando bloqueado ({reason}): {cmd}",
                          self._ctx.dispatch)
            logger = self._ctx.audit
            if logger is not None:
                session = self._ctx.session
                logger.log_operation(
                    "command_denied",
                    user=getattr(session, "_user", "unknown"),
                    host=getattr(session, "_host", "unknown"),
                    status="blocked",
                    service=svc.name,
                    rejected=[c for c, _ in rejected],
                )
            return

        if mode == "cli":
            if self._ctx.ensure_device_ready(
                    f"executar o servico '{svc.name}'") is None:
                return

        def _do():
            """Executa o servico selecionado (mock ou SSH real)."""
            _ui.loading(self._state.output,
                        f"Executando: {svc.name} ({mode})…",
                        self._ctx.dispatch)

            if mode == "mock":
                result = execute_service(final_svc, session_type="mock")
                _ui.write(self._state.output, result, self._ctx.dispatch)
                self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                              source="service",
                                              payload=CommandExecutedPayload(
                                                  command=svc.name,
                                                  data={"mode": "mock"},
                                              )))
                return

            if not self._ctx.sb.is_alive():
                _ui.write(self._state.output,
                          "✘  Sem sessao SSH ativa. Conecte-se primeiro.",
                          self._ctx.dispatch)
                return

            if mode == "cli":
                # Caminho NAPALM (flag HW_BACKEND=napalm): preview → diff →
                # confirmação do usuário → apply → auditoria. Devolve True
                # quando assumiu (sucesso OU recusa explícita, sem fallback
                # silencioso); False → caminho Netmiko padrão.
                if self.run_service_napalm(svc, final_svc):
                    return
                if final_svc.config_mode:
                    # Serviço de configuração altera estado: Command pattern
                    # com snapshot pré-mudança (fail-closed — sem snapshot,
                    # nada é aplicado) + rollback via paleta de comandos.
                    session = self._ctx.session
                    user = getattr(session, "_user", "unknown")
                    host = getattr(session, "_host", "unknown")
                    session_id = getattr(session, "_session_id", None)
                    audit: AuditLogger | None = self._ctx.audit
                    service_cmd = ConfigCommand(
                        final_svc.cli_commands,
                        read_state=lambda: self._ctx.sb.send_command(
                            "display current-configuration"),
                        apply_fn=lambda lines: (
                            True,
                            self._ctx.sb.send_service_commands(
                                lines,
                                config_mode=final_svc.config_mode,
                                requires_privilege=(
                                    final_svc.requires_privilege),
                            ),
                        ),
                        dry_run=self._ctx.dry_run,
                    )
                    try:
                        svc_result = service_cmd.execute()
                    except SnapshotError as exc:
                        self._ctx.sb.invalidate_connection()
                        _ui.write(self._state.output,
                                  f"✘  {exc} — nada foi aplicado.",
                                  self._ctx.dispatch)
                        audit_config_op(
                            audit, op="config_apply", user=user, host=host,
                            session_id=session_id, status="blocked",
                            reason="snapshot falhou", service=svc.name,
                            backend="netmiko",
                        )
                        return
                    except SdnError as exc:
                        # Conexão pode ter caído no meio da mutação:
                        # invalida e mantém o snapshot p/ rollback posterior.
                        self._ctx.sb.invalidate_connection()
                        self._ctx.set_last_config_command(service_cmd)
                        _ui.write(self._state.output,
                                  f"✘  Falha SSH: {exc}",
                                  self._ctx.dispatch)
                        audit_config_op(
                            audit, op="config_apply", user=user, host=host,
                            session_id=session_id, status="error",
                            reason="falha ssh", service=svc.name,
                            backend="netmiko",
                        )
                        return
                    self._ctx.set_last_config_command(service_cmd)
                    _ui.write(self._state.output, svc_result.message,
                              self._ctx.dispatch)
                    audit_config_op(
                        audit, op="config_apply", user=user, host=host,
                        session_id=session_id, status=svc_result.status,
                        duration_ms=svc_result.duration_ms,
                        service=svc.name, backend="netmiko",
                    )
                    self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                                  source="service",
                                                  payload=CommandExecutedPayload(
                                                      command=svc.name,
                                                      data={"mode": "cli"},
                                                  )))
                    return
                result = self._ctx.sb.send_service_commands(
                    final_svc.cli_commands,
                    config_mode=final_svc.config_mode,
                    requires_privilege=final_svc.requires_privilege,
                )
                _ui.write(self._state.output, result, self._ctx.dispatch)
                self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                              source="service",
                                              payload=CommandExecutedPayload(
                                                  command=svc.name,
                                                  data={"mode": "cli"},
                                              )))
                return

            _ui.write(self._state.output, f"Modo desconhecido: {mode}",
                      self._ctx.dispatch)

        self._ctx.spawn_io(_do)

    def run_service_napalm(self, svc: ServiceDef,
                           final_svc: ServiceDef) -> bool:
        """Caminho NAPALM do servico (modo cli): preview → diff → confirmação
        do usuário → apply → auditoria.

        Chamado apenas da branch ``mode == "cli"`` de ``run_service``. O modo
        mock e os serviços de leitura (``config_mode=False``) nunca passam por
        aqui — o caminho Netmiko padrão permanece bit a bit igual ao de hoje.

        Returns:
            ``False`` quando o caminho Netmiko padrão deve ser usado (backend
            efetivo != napalm OU serviço sem ``config_mode``). ``True`` quando
            o caminho NAPALM assumiu — sucesso **ou** recusa explícita (preview
            falhou / diff vazio / usuário cancelou); recusa nunca cai no
            Netmiko silenciosamente (o usuário optou por NAPALM via flag —
            fail-closed).
        """
        backend, warning = resolve_backend()
        if warning:
            log.warning("resolve_backend: %s", warning)
        if backend != BACKEND_NAPALM or not final_svc.config_mode:
            return False

        session = self._ctx.session
        user = getattr(session, "_user", "unknown")
        host = getattr(session, "_host", "unknown")
        session_id = getattr(session, "_session_id", None)
        audit: AuditLogger | None = self._ctx.audit
        conn = self._ctx.sb.connection
        if conn is None:
            # Sem handle Netmiko bruto não há como fazer preview/apply via
            # NAPALM: recusa auditada, nunca fallback silencioso para o Netmiko
            # (o usuário optou pela flag — falhar fechado).
            _ui.write(self._state.output,
                      "✘  NAPALM: sem sessao Netmiko ativa — nada foi aplicado.",
                      self._ctx.dispatch)
            _audit_napalm_blocked(audit, user=user, host=host,
                                  session_id=session_id, service=svc.name,
                                  reason="sem conexao Netmiko exposta")
            return True
        executor = NapalmVRPBackend(
            conn,  # sessão Netmiko existente (sem 2º SSH)
            user=user, host=host, session_id=session_id, audit=audit,
        )

        # 1) dry-run: diff running × candidate. Falha → recusa visível auditada.
        try:
            # sanitize_command: defesa em profundidade — o diff é derivado da
            # configuração running, que pode conter senha/secret/key/token.
            diff = sanitize_command(executor.preview(final_svc.cli_commands))
        except Exception as exc:
            # justificativa (exceção genérica): fronteira com o driver NAPALM
            # de terceiros — qualquer erro vira recusa auditada e parada;
            # nunca exceção silenciosa nem fallback para Netmiko.
            err = sanitize_command(str(exc))
            _ui.write(self._state.output,
                      f"✘  NAPALM: preview (dry-run) falhou — nada foi "
                      f"aplicado.\n{err}",
                      self._ctx.dispatch)
            _audit_napalm_blocked(audit, user=user, host=host,
                                  session_id=session_id, service=svc.name,
                                  reason=f"preview falhou: {err}")
            return True

        # 2) diff vazio: nada mudaria — encerra sem apply e sem diálogo.
        if not diff.strip():
            _ui.write(self._state.output, "Sem mudancas a aplicar.",
                      self._ctx.dispatch)
            return True

        # 3) confirmação do usuário com o diff na tela (thread-safe via
        #    UiBridge). Sem bridge (app sem GUI / testes headless) aplica sem
        #    confirmação: comportamento nunca pior que hoje (hoje não há diff).
        bridge = self._ctx.ui_bridge()
        if bridge is None:
            log.warning("NAPALM: sem UiBridge — aplicando '%s' sem confirmacao",
                        svc.name)
            approved = True
        else:
            approved = ask_from_worker(bridge,
                                       title=f"Aplicar '{svc.name}'?",
                                       message=diff)
        if not approved:
            _ui.write(self._state.output,
                      "Cancelado pelo usuario — nada foi aplicado.",
                      self._ctx.dispatch)
            _audit_napalm_blocked(audit, user=user, host=host,
                                  session_id=session_id, service=svc.name,
                                  reason="cancelado pelo usuario")
            return True

        # 4) apply com snapshot pré-mudança (capturado pelo próprio backend).
        try:
            result = executor.apply(final_svc.cli_commands)
        except SdnError as exc:
            # o backend já auditou (status blocked/error) — só reporta aqui.
            _ui.write(self._state.output,
                      f"✘  NAPALM: aplicacao recusada pelo dispositivo — "
                      f"alteracoes descartadas.\n{sanitize_command(str(exc))}",
                      self._ctx.dispatch)
            return True
        except Exception as exc:
            # justificativa (exceção genérica): o snapshot é capturado fora do
            # try interno do backend e o driver de terceiros pode levantar erro
            # cru — vira recusa auditada, nunca fallback Netmiko.
            err = sanitize_command(str(exc))
            _ui.write(self._state.output,
                      f"✘  NAPALM: falha ao aplicar — nada foi "
                      f"confirmado.\n{err}",
                      self._ctx.dispatch)
            _audit_napalm_blocked(audit, user=user, host=host,
                                  session_id=session_id, service=svc.name,
                                  reason=f"apply falhou: {err}")
            return True

        _ui.write(self._state.output,
                  f">  NAPALM: {len(final_svc.cli_commands)} comando(s) "
                  f"aplicado(s) em {result.duration_ms:.0f} ms  |  "
                  f"snapshot pre-mudanca: "
                  f"{len(result.snapshot.splitlines())} linha(s)\n"
                  f"{'─' * 40}\n{result.output}",
                  self._ctx.dispatch)
        self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                      source="service",
                                      payload=CommandExecutedPayload(
                                          command=svc.name,
                                          data={"mode": "cli",
                                                "backend": BACKEND_NAPALM},
                                      )))
        return True

    def validate_service(self, svc: ServiceDef,
                         final_cmds: list[str]) -> list[tuple[str, str]]:
        """Valida comandos finais do serviço contra allowlist e deny-list.

        Args:
            svc: Definição do serviço (template + comandos concretos).
            final_cmds: Comandos finais pós-substituição de parâmetros.

        Returns:
            Lista de ``(cmd, reason)`` rejeitados; vazia = todos ok.
        """
        allow_patterns = _build_service_allow_patterns(svc)
        deny_patterns = [re.compile(p, re.IGNORECASE)
                         for p in _DEFAULT_DENY_PATTERNS]
        rejected: list[tuple[str, str]] = []
        for c in final_cmds:
            allowed = any(p.search(c) for p in allow_patterns)
            denied = any(p.search(c) for p in deny_patterns)
            if denied or not allowed:
                rejected.append((c, "destrutivo" if denied
                                 else "fora do template do serviço"))
        return rejected
