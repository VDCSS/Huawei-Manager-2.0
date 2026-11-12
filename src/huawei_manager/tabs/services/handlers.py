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
from huawei_manager.basic_config.vrp_version import VrpVersion, detect_vrp_version
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SdnValidationError, SnapshotError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_NAPALM,
    NapalmVRPBackend,
    resolve_backend,
)
from huawei_manager.sdn_controller.validator import _DEFAULT_DENY_PATTERNS
from huawei_manager.services import ServiceDef, execute_service
from huawei_manager.services.form_registry import (
    check_anchors,
    get_form_spec,
    render_form,
    rollback_lines,
)
from huawei_manager.services.form_spec import RenderedForm
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


def _destructive_lines(lines: list[str]) -> list[str]:
    """Linhas do bloco que casam com a deny-list de política."""
    patterns = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_DENY_PATTERNS]
    return [line for line in lines if any(p.search(line) for p in patterns)]


def _matches_any(line: str, patterns: tuple[str, ...]) -> bool:
    """A linha casa com algum dos padrões (regex, case-insensitive)?"""
    return any(re.search(p, line, re.IGNORECASE) for p in patterns)


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

        # Gate de permissão estrito: configuração de dispositivo exige papel admin
        if svc.config_mode and not self._ctx.require_access("admin"):
            _ui.write(
                self._state.output,
                "✘  Permissão negada: configuração de dispositivo exige papel admin.",
                self._ctx.dispatch,
            )
            return

        # Aviso e bloqueio explícito para modo NAPALM em serviços de configuração
        if mode == "napalm" and svc.config_mode:
            _ui.write(
                self._state.output,
                "✘  Modo NAPALM não suporta aplicação de blocos VRP neste serviço. Alterne para o modo CLI/SSH padrão.",
                self._ctx.dispatch,
            )
            return

        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if device:
            label += f"  |  Alvo: {device.name} ({device.host})"
        device_lbl = self._state.device_lbl
        if device_lbl is not None:
            device_lbl.setText(label)

        # ── Serviços com formulário composto (ACL, rota estática) ──
        # Fluxo próprio: formulário → render validado → ConfigCommand
        # (snapshot → apply → verify → rollback), com commit automático
        # conforme a VRP detectada e save opcional (checkbox).
        if svc.form_kind:
            self._run_composite_service(svc, mode)
            return

        _REJECT_PARAM = re.compile(r"[;&|`$(){}]")

        final_svc = svc
        if svc.config_mode and self._state.param_entries:
            if svc.config_template is not None and svc.params:
                # Caminho tipado F1: valida cada ParamSpec e renderiza o ConfigTemplate
                val_map: dict[str, str] = {}
                for spec in svc.params:
                    entry = self._state.param_entries.get(spec.label)
                    val_map[spec.key] = entry.text().strip() if entry is not None else ""
                try:
                    rendered_lines = svc.config_template.render(svc.params, val_map)
                except SdnValidationError as err:
                    _ui.write(
                        self._state.output,
                        f"✘  Parâmetro inválido: {err}",
                        self._ctx.dispatch,
                    )
                    return
                final_svc = ServiceDef(
                    id=svc.id,
                    name=svc.name,
                    description=svc.description,
                    category=svc.category,
                    device_types=svc.device_types,
                    cli_commands=rendered_lines,
                    config_mode=svc.config_mode,
                    params=svc.params,
                    config_template=svc.config_template,
                )
            else:
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
                    allow_patterns = [
                        re.escape(c) for c in final_svc.cli_commands
                    ] if final_svc.config_template else None

                    def _apply_lines(lines: list[str]) -> tuple[bool, str]:
                        if final_svc.config_template is not None:
                            # A versão VRP é detectada para que o commit
                            # automático funcione também nos serviços
                            # legados (VRP8 exige 'commit' ao sair do
                            # system-view — sem isso a config fica pendente).
                            return self._ctx.sb.send_config_block(
                                lines,
                                save=False,
                                allow_patterns=allow_patterns,
                                vrp_version=self._detect_vrp_version(),
                            )
                        return (
                            True,
                            self._ctx.sb.send_service_commands(
                                lines,
                                config_mode=final_svc.config_mode,
                                requires_privilege=final_svc.requires_privilege,
                            ),
                        )

                    service_cmd = ConfigCommand(
                        final_svc.cli_commands,
                        read_state=lambda: self._ctx.sb.send_command(
                            "display current-configuration"
                        ),
                        apply_fn=_apply_lines,
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

    # ── Formulários compostos (ACL, rota estática) ──────────────────
    def preview_form(self, svc: ServiceDef) -> None:
        """Mostra o bloco que seria enviado — não aplica nada."""
        rendered = self._render_form_or_report(svc)
        if rendered is None:
            return
        lines = list(rendered.lines)
        body = "\n".join(f"  {line}" for line in lines)
        _ui.write(
            self._state.output,
            f"Pré-visualização — {svc.name} ({len(lines)} linha(s)):\n"
            f"{'─' * 40}\n{body}\n{'─' * 40}\n"
            "Nada foi aplicado ao dispositivo.",
            self._ctx.dispatch,
        )

    def consult_form(self, svc: ServiceDef) -> None:
        """Consulta o estado já aplicado no device (somente leitura)."""
        if not svc.form_kind:
            return
        spec = get_form_spec(svc.form_kind)
        command = spec.consult_command
        if not command:
            _ui.write(
                self._state.output,
                f"✘  '{svc.name}' não possui comando de consulta.",
                self._ctx.dispatch,
            )
            return
        if not self._ctx.sb.is_alive():
            _ui.write(self._state.output,
                      "✘  Sem sessao SSH ativa. Conecte-se primeiro.",
                      self._ctx.dispatch)
            return

        def _do() -> None:
            _ui.loading(self._state.output, f"Consultando: {command}…",
                        self._ctx.dispatch)
            try:
                output = self._ctx.sb.send_command(command)
            except SdnError as exc:
                _ui.write(self._state.output,
                          f"✘  Falha na consulta: {exc}",
                          self._ctx.dispatch)
                return
            _ui.write(
                self._state.output,
                f">  {command}\n{'─' * 40}\n{output}",
                self._ctx.dispatch,
            )

        self._ctx.spawn_io(_do)

    def _render_form_or_report(self, svc: ServiceDef) -> RenderedForm | None:
        """Renderiza o formulário; em caso de erro, reporta na saída."""
        form = self._state.form_state
        if form is None:
            _ui.write(
                self._state.output,
                "✘  Formulário indisponível — selecione o serviço novamente.",
                self._ctx.dispatch,
            )
            return None
        try:
            return render_form(svc.form_kind or "", form.values())
        except SdnValidationError as err:
            _ui.write(
                self._state.output,
                f"✘  Formulário inválido: {err}",
                self._ctx.dispatch,
            )
            return None

    def _run_composite_service(self, svc: ServiceDef, mode: str) -> None:
        """Aplica um serviço de formulário composto (fase de renderização)."""
        rendered = self._render_form_or_report(svc)
        if rendered is None:
            return
        lines = list(rendered.lines)
        spec = get_form_spec(svc.form_kind or "")

        # ── Política: deny-list = bloqueio (não só confirmação) ──────
        denied = _destructive_lines(lines)
        if denied:
            _ui.write(
                self._state.output,
                "✘  Comando bloqueado pela política de segurança:\n"
                + "\n".join(denied)
                + "\nNada foi aplicado ao dispositivo.",
                self._ctx.dispatch,
            )
            session = self._ctx.session
            audit = self._ctx.audit
            if audit is not None:
                audit.log_operation(
                    "command_denied",
                    user=getattr(session, "_user", "unknown"),
                    host=getattr(session, "_host", "unknown"),
                    status="blocked",
                    service=svc.name,
                    rejected=denied,
                )
            return

        # ── Linhas sensíveis (ex.: ACL que pode cortar o próprio acesso)
        sensitive = [ln for ln in lines if _matches_any(ln, spec.confirm_patterns)]
        if sensitive:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "Confirmar aplicação de política",
                f"O serviço '{svc.name}' aplica política de acesso:\n"
                + "\n".join(sensitive)
                + "\n\nUma regra 'deny' pode interromper o seu próprio acesso "
                "ao dispositivo.\nContinuar?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                _ui.write(self._state.output,
                          "Operação cancelada pelo usuário.",
                          self._ctx.dispatch)
                return

        # Modo mock: mostra o bloco, não toca no dispositivo.
        if mode == "mock":
            self.preview_form(svc)
            return

        if not self._ctx.sb.is_alive():
            _ui.write(self._state.output,
                      "✘  Sem sessao SSH ativa. Conecte-se primeiro.",
                      self._ctx.dispatch)
            return

        if self._ctx.ensure_device_ready(
                f"aplicar o servico '{svc.name}'") is None:
            return

        save_enabled = self._save_enabled()
        self._ctx.spawn_io(
            lambda: self._apply_composite(svc, rendered, lines, save_enabled)
        )

    def _apply_composite(
        self,
        svc: ServiceDef,
        rendered: RenderedForm,
        lines: list[str],
        save_enabled: bool,
    ) -> None:
        """Executa o bloco composto na sessão CLI (thread de trabalho).

        Fluxo: **aplica** (commit automático conforme a VRP) → **verifica**
        no running-config → **persiste** na startup-config (só quando o
        operador marcou a opção de save e a verificação passou).
        """
        session = self._ctx.session
        user = getattr(session, "_user", "unknown")
        host = getattr(session, "_host", "unknown")
        session_id = getattr(session, "_session_id", None)
        audit: AuditLogger | None = self._ctx.audit
        version = self._detect_vrp_version()
        spec = get_form_spec(svc.form_kind or "")
        # Allowlist declarada no formulário (não derivada das linhas
        # renderizadas): qualquer linha fora do padrão é bloqueada.
        allow_patterns = list(spec.allow_patterns) or None

        def _apply_lines(block: list[str]) -> tuple[bool, str]:
            return self._ctx.sb.send_config_block(
                block,
                save=False,
                allow_patterns=allow_patterns,
                vrp_version=version,
            )

        def _verify() -> tuple[bool, str]:
            try:
                running = self._ctx.sb.send_command(
                    "display current-configuration")
            except SdnError as exc:
                return False, f"falha ao ler o running-config: {exc}"
            missing = check_anchors(running, rendered.anchors)
            if missing:
                return False, (
                    "linha(s) não encontrada(s) no running-config: "
                    + "; ".join(missing[:5])
                )
            return True, "configuração confirmada no running-config"

        service_cmd = ConfigCommand(
            lines,
            read_state=lambda: self._ctx.sb.send_command(
                "display current-configuration"),
            apply_fn=_apply_lines,
            dry_run=self._ctx.dry_run,
            verify_fn=_verify,
            rollback_fn=lambda snapshot: rollback_lines(rendered, snapshot),
        )

        _ui.loading(self._state.output,
                    f"Aplicando: {svc.name}…",
                    self._ctx.dispatch)
        try:
            result = service_cmd.execute()
        except SnapshotError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(self._state.output,
                      f"✘  {exc} — nada foi aplicado.",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply", user=user, host=host,
                session_id=session_id, status="blocked",
                reason="snapshot falhou", service=svc.name,
                backend="netmiko", form_kind=svc.form_kind,
                vrp_version=str(version), saved=False,
            )
            return
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            self._ctx.set_last_config_command(service_cmd)
            _ui.write(self._state.output,
                      f"✘  Falha SSH: {exc}",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply", user=user, host=host,
                session_id=session_id, status="error",
                reason="falha ssh", service=svc.name,
                backend="netmiko", form_kind=svc.form_kind,
                vrp_version=str(version), saved=False,
            )
            return

        self._ctx.set_last_config_command(service_cmd)
        message = result.message

        # ── Persistência: só depois da verificação ──────────────────
        saved = False
        if save_enabled and result.ok:
            try:
                ok_save, save_msg = self._ctx.sb.save_running_config(version)
            except SdnError as exc:
                ok_save, save_msg = False, f"falha ao salvar: {exc}"
            saved = bool(ok_save)
            message = f"{message}\n{save_msg}"
            if not ok_save:
                result_status = "error"
            else:
                result_status = result.status
        else:
            result_status = result.status

        _ui.write(self._state.output, message, self._ctx.dispatch)
        audit_config_op(
            audit, op="config_apply", user=user, host=host,
            session_id=session_id, status=result_status,
            duration_ms=result.duration_ms, service=svc.name,
            backend="netmiko", form_kind=svc.form_kind,
            vrp_version=str(version), saved=saved,
        )
        self._ctx.event_bus.put(Event(
            EventType.CONFIG_CHANGED, source="service",
            payload=CommandExecutedPayload(
                command=svc.name,
                data={
                    "mode": "cli",
                    "form_kind": svc.form_kind,
                    "status": result_status,
                    "saved": saved,
                },
            )))

    def rollback_last(self) -> None:
        """Desfaz a última configuração aplicada (rollback do snapshot).

        O rollback roda apenas na running-config — para persistir a
        reversão, marque "Salvar" e aplique novamente.
        """
        last_cmd = self._ctx.get_last_config_command()
        if last_cmd is None:
            _ui.write(
                self._state.output,
                "✘  Nenhuma configuração anterior para reverter.",
                self._ctx.dispatch,
            )
            return

        def _do() -> None:
            _ui.loading(self._state.output, "Executando rollback…",
                        self._ctx.dispatch)
            try:
                res = last_cmd.rollback()
            except SdnError as exc:
                _ui.write(self._state.output,
                          f"✘  Falha durante o rollback: {exc}",
                          self._ctx.dispatch)
                return
            _ui.write(
                self._state.output,
                f"{res.message}\n(A reversão vale apenas para a "
                "running-config — marque 'Salvar' e aplique novamente para "
                "persistir.)",
                self._ctx.dispatch,
            )
            self._ctx.event_bus.put(Event(
                EventType.CONFIG_CHANGED, source="service",
                payload=CommandExecutedPayload(
                    command="service-rollback",
                    data={"status": res.status, "rollback": True},
                )))

        self._ctx.spawn_io(_do)

    def _detect_vrp_version(self) -> VrpVersion:
        """Detecta a versão VRP do device (cache por host)."""
        session = self._ctx.session
        host = getattr(session, "_host", None)
        state = self._state
        if state.vrp_version is not None and state.vrp_host == host:
            return state.vrp_version
        try:
            output = self._ctx.sb.send_command("display version")
        except Exception:
            # justificativa: a detecção é best-effort; sem versão identificada
            # o fluxo assume VRP8 (fail-closed no commit) — ver
            # requires_commit(UNKNOWN).
            output = ""
        version = detect_vrp_version(output or "")
        state.vrp_version = version
        state.vrp_host = host
        return version

    def _save_enabled(self) -> bool:
        """Persistência na startup-config — desmarcada por padrão."""
        chk = self._state.save_chk
        return bool(chk.isChecked()) if chk is not None else False

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
        if svc.config_template is not None:
            # Em serviços com template tipado, a validação de formato e tipagem
            # já foi concluída pelo ConfigTemplate; checamos deny patterns e allow
            deny_patterns = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_DENY_PATTERNS]
            rejected: list[tuple[str, str]] = []
            for c in final_cmds:
                if any(p.search(c) for p in deny_patterns):
                    rejected.append((c, "destrutivo"))
            return rejected

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
