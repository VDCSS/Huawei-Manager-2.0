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
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, NamedTuple

from huawei_manager.audit_log import AuditLogger
from huawei_manager.basic_config.vrp_version import VrpVersion, detect_vrp_version
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SdnValidationError, SnapshotError
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_NAPALM,
    NapalmVRPBackend,
    resolve_backend,
)
from huawei_manager.sdn_controller.validator import _DEFAULT_DENY_PATTERNS
from huawei_manager.services import ServiceDef, execute_service
from huawei_manager.services.acl_presets import (
    AclBlockProfile,
    delete_profile,
    device_key,
    load_profile,
    save_profile,
)
from huawei_manager.services.block_cli import (
    absence_check,
    anchors_for,
    chain_absence,
    chain_anchors,
    delete_chain_lines,
    preview_lines,
    preview_site_lines,
    rollback_for,
    site_anchors,
    site_rollback,
    suggested_chain,
    update_chain_lines,
)
from huawei_manager.services.device_precheck import (
    interfaces_in_block,
    missing_interfaces,
)
from huawei_manager.services.form_registry import (
    check_anchors,
    get_form_spec,
    render_form,
    rollback_lines,
)
from huawei_manager.services.form_spec import RenderedForm
from huawei_manager.services.traffic_policy import (
    TrafficPolicyChain,
    render_chain,
)
from huawei_manager.services.traffic_policy_presets import (
    TrafficPolicyPreset,
    delete_preset,
    load_preset,
    save_preset,
)
from huawei_manager.services.ui_bridge import ask_from_worker
from huawei_manager.tabs import _ui
from huawei_manager.utils import sanitize_command
from huawei_manager.widgets.block_dialog import (
    BlockInternetDecision,
    BlockInternetDialog,
    BlockSiteDecision,
    BlockSiteDialog,
)

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


def _chain_of(preset: TrafficPolicyPreset | None) -> TrafficPolicyChain | None:
    """Converte o preset persistido na cadeia usada pelo renderer/CLI."""
    if preset is None:
        return None
    return TrafficPolicyChain(
        classifier=preset.classifier,
        behavior=preset.behavior,
        policy=preset.policy,
        action=preset.behavior_action,
    )


def _preset_of(
    device_key: str,
    flow: str,
    *,
    acl_number: int,
    interface: str,
    direction: str,
    chain: TrafficPolicyChain,
    applied: bool,
    preexisting: bool,
) -> TrafficPolicyPreset:
    """Monta o preset (uma cadeia por device/fluxo) para persistência."""
    return TrafficPolicyPreset(
        device_key=device_key,
        flow=flow,
        classifier=chain.classifier,
        behavior=chain.behavior,
        policy=chain.policy,
        behavior_action=chain.action,
        acl_number=acl_number,
        interface=interface,
        direction=direction,
        applied=applied,
        preexisting=preexisting,
    )


class _ChainPlan(NamedTuple):
    """Bloco CLI + verificação + rollback de uma config de cadeia.

    ``anchors`` vazias = a verificação deve procurar **ausência** das
    linhas em ``absence`` (caso da exclusão); caso contrário exige a
    presença das âncoras no running-config.
    """

    lines: list[str]
    anchors: tuple[str, ...]
    absence: tuple[str, ...]
    rollback: Callable[[str], list[str]]


def _chain_plan(
    *,
    config_action: str,
    old: TrafficPolicyChain | None,
    new: TrafficPolicyChain,
    acl_number: int,
    interface: str,
    direction: str,
    preexisting: bool,
) -> _ChainPlan | None:
    """Plano CLI para ``update``/``delete`` de cadeia (``None`` = normal).

    Fail-closed: sem cadeia anterior persistida, nenhuma troca/remoção é
    planejada — o chamador deve abortar antes de tocar no dispositivo.
    """
    if config_action == "update" and old is not None:
        return _ChainPlan(
            lines=update_chain_lines(
                old, new, acl_number=acl_number, interface=interface,
                direction=direction, preexisting=preexisting,
            ),
            anchors=chain_anchors(
                new, acl_number=acl_number, interface=interface,
                direction=direction,
            ),
            absence=chain_absence(old, interface=interface, direction=direction),
            rollback=lambda _snapshot: update_chain_lines(
                new, old, acl_number=acl_number, interface=interface,
                direction=direction, preexisting=preexisting,
            ),
        )
    if config_action == "delete" and old is not None:
        return _ChainPlan(
            lines=delete_chain_lines(
                old, interface=interface, direction=direction,
                preexisting=preexisting,
            ),
            anchors=(),
            absence=chain_absence(old, interface=interface, direction=direction),
            rollback=lambda _snapshot: [
                *render_chain(old, str(acl_number))[0],
                f"interface {interface}",
                f"traffic-policy {old.policy} {direction}",
                "quit",
            ],
        )
    return None


def _save_chain_preset(
    key: str,
    flow: str,
    *,
    acl_number: int,
    interface: str,
    direction: str,
    chain: TrafficPolicyChain,
    applied: bool,
    preexisting: bool,
) -> bool:
    """Grava o preset da cadeia; falha de JSON volta ``False`` (fail-closed)."""
    try:
        save_preset(_preset_of(
            key, flow, acl_number=acl_number, interface=interface,
            direction=direction, chain=chain, applied=applied,
            preexisting=preexisting,
        ))
        return True
    except SdnValidationError as exc:
        log.warning("cadeia não persistida (%s/%s): %s", key, flow, exc)
        return False


def _delete_chain_preset(key: str, flow: str) -> bool:
    """Apaga o preset da cadeia; ausência é idempotente."""
    try:
        delete_preset(key, flow)
        return True
    except SdnValidationError as exc:
        log.warning("cadeia não removida (%s/%s): %s", key, flow, exc)
        return False


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
                "x  Permissão negada: configuração de dispositivo exige papel admin.",
                self._ctx.dispatch,
            )
            return

        # Aviso e bloqueio explícito para modo NAPALM em serviços de configuração
        if mode == "napalm" and svc.config_mode:
            _ui.write(
                self._state.output,
                "x  Modo NAPALM não suporta blocos VRP. Use CLI/SSH padrão.",
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
                        f"x  Parâmetro inválido: {err}",
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
                        "x  Servico inconsistente: "
                        f"{len(placeholders)} placeholder(s) para {len(entries)} "
                        "campo(s). Nada foi executado.",
                        self._ctx.dispatch)
                    return
                for placeholder, entry in zip(placeholders, entries):
                    val = entry.text().strip()
                    if _REJECT_PARAM.search(val):
                        _ui.write(
                            self._state.output,
                            f"x  Parametro '{placeholder}' contem caracteres "
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
                          f"x  Comando bloqueado ({reason}): {cmd}",
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
                          "x  Sem sessao SSH ativa. Conecte-se primeiro.",
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
                                  f"x  {exc} — nada foi aplicado.",
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
                        self._state.last_config_command = service_cmd
                        _ui.write(self._state.output,
                                  f"x  Falha SSH: {exc}",
                                  self._ctx.dispatch)
                        audit_config_op(
                            audit, op="config_apply", user=user, host=host,
                            session_id=session_id, status="error",
                            reason="falha ssh", service=svc.name,
                            backend="netmiko",
                        )
                        return
                    self._state.last_config_command = service_cmd
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
                f"x  '{svc.name}' não possui comando de consulta.",
                self._ctx.dispatch,
            )
            return
        if not self._ctx.sb.is_alive():
            _ui.write(self._state.output,
                      "x  Sem sessao SSH ativa. Conecte-se primeiro.",
                      self._ctx.dispatch)
            return

        def _do() -> None:
            _ui.loading(self._state.output, f"Consultando: {command}…",
                        self._ctx.dispatch)
            try:
                output = self._ctx.sb.send_command(command)
            except SdnError as exc:
                _ui.write(self._state.output,
                          f"x  Falha na consulta: {exc}",
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
                "x  Formulário indisponível — selecione o serviço novamente.",
                self._ctx.dispatch,
            )
            return None
        try:
            return render_form(svc.form_kind or "", form.values())
        except SdnValidationError as err:
            _ui.write(
                self._state.output,
                f"x  Formulário inválido: {err}",
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
                "x  Comando bloqueado pela política de segurança:\n"
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
                      "x  Sem sessao SSH ativa. Conecte-se primeiro.",
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

        # ── Pré-checagem: a interface existe no device? ──────────────
        # Sem esta checagem a VRP responde "Wrong parameter found at '^'
        # position" e o operador não descobre o nome correto da interface.
        ifaces = interfaces_in_block(lines)
        if ifaces:
            try:
                pre_state = self._ctx.sb.send_command(
                    "display current-configuration")
            except SdnError as exc:
                _ui.write(
                    self._state.output,
                    f"x  Falha ao ler o running-config: {exc} — "
                    "nada foi aplicado.",
                    self._ctx.dispatch,
                )
                audit_config_op(
                    audit, op="config_apply", user=user, host=host,
                    session_id=session_id, status="blocked",
                    reason="pre-check falhou", service=svc.name,
                    backend="netmiko", form_kind=svc.form_kind,
                    vrp_version=str(version), saved=False,
                )
                return
            missing = missing_interfaces(pre_state, ifaces)
            if missing:
                _ui.write(
                    self._state.output,
                    "x  Interface(s) inexistente(s) no device: "
                    + ", ".join(missing)
                    + "\nVerifique o nome exato em 'display interface brief'."
                    + "\nNada foi aplicado ao dispositivo.",
                    self._ctx.dispatch,
                )
                audit_config_op(
                    audit, op="config_apply", user=user, host=host,
                    session_id=session_id, status="blocked",
                    reason=f"interface inexistente: {', '.join(missing)}",
                    service=svc.name, backend="netmiko",
                    form_kind=svc.form_kind, vrp_version=str(version),
                    saved=False,
                )
                return

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
                      f"x  {exc} — nada foi aplicado.",
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
            self._state.last_config_command = service_cmd
            _ui.write(self._state.output,
                      f"x  Falha SSH: {exc}",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply", user=user, host=host,
                session_id=session_id, status="error",
                reason="falha ssh", service=svc.name,
                backend="netmiko", form_kind=svc.form_kind,
                vrp_version=str(version), saved=False,
            )
            return

        self._state.last_config_command = service_cmd
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

    # ── Feature "Bloquear Internet" (botão pré-definido da ACL) ──────

    def block_internet(self) -> None:
        """Abre o modal "Bloquear Internet" e executa a decisão.

        Fluxo: perfil por device (D2) → estado do binding detectado no
        device (ou cache com aviso de estado estimado) → modal com
        revisão obrigatória (D4) → execução com snapshot/verify/rollback.
        Persistência **somente** com ``result.ok`` + save marcado + papel
        admin (D3/D6).
        """
        svc = self._state.current_svc
        if svc is None or svc.form_kind != "acl":
            _ui.write(
                self._state.output,
                "x  Bloquear Internet disponível apenas no serviço de ACL.",
                self._ctx.dispatch,
            )
            return
        if not self._ctx.require_access("admin"):
            _ui.write(
                self._state.output,
                "x  Permissão negada: configuração de dispositivo exige "
                "papel admin.",
                self._ctx.dispatch,
            )
            return
        mode = self._ctx.svc_mode()
        if mode == "napalm":
            _ui.write(
                self._state.output,
                "x  Modo NAPALM não suporta aplicação de blocos VRP neste "
                "serviço. Alterne para o modo CLI/SSH padrão.",
                self._ctx.dispatch,
            )
            return

        device = self._ctx.device()
        if device is None:
            _ui.write(self._state.output,
                      "x  Nenhum device selecionado.",
                      self._ctx.dispatch)
            return
        key = device_key(str(device.name), str(device.host))
        try:
            profile = load_profile(None, key)
            preset = load_preset(key, "internet")
        except SdnValidationError as exc:
            _ui.write(self._state.output, f"x  {exc} — nada foi aplicado.",
                      self._ctx.dispatch)
            return

        chain = _chain_of(preset)
        applied, source = self._detect_applied(profile, chain)
        dialog = BlockInternetDialog(
            profile=profile,
            applied=applied,
            applied_source=source,
            can_save=role_meets(self._ctx.role(), "admin"),
            chain=chain,
        )
        dialog.set_device_key(key)
        if not dialog.exec():
            _ui.write(self._state.output, "Operação cancelada pelo usuário.",
                      self._ctx.dispatch)
            return
        decision = dialog.get_decision()

        if decision.config_action == "save":
            self._save_chain_config(
                chain=decision.chain,
                key=key,
                flow="internet",
                acl_number=decision.profile.acl_number,
                interface=decision.profile.interface,
                direction=decision.profile.direction,
                applied=bool(preset.applied) if preset is not None else False,
                preexisting=decision.profile.created_from_snapshot,
            )
            return

        if not self._ctx.sb.is_alive():
            _ui.write(self._state.output,
                      "x  Sem sessao SSH ativa. Conecte-se primeiro.",
                      self._ctx.dispatch)
            return
        if self._ctx.ensure_device_ready("aplicar o bloqueio") is None:
            return
        self._ctx.spawn_io(lambda: self._run_block(decision, key))

    def block_site(self) -> None:
        """Abre o modal "Bloquear site" e executa a decisão.

        Fluxo B: estratégia → destinos → aplicação → **revisão
        obrigatória** (D4) → execução com snapshot/verify/rollback.
        Save somente com ``result.ok`` + save marcado + papel admin
        (D3/D6); sem JSON de perfil (D2 é exclusivo do Bloquear
        Internet).
        """
        svc = self._state.current_svc
        if svc is None or svc.form_kind != "acl":
            _ui.write(
                self._state.output,
                "x  Bloquear site disponível apenas no serviço de ACL.",
                self._ctx.dispatch,
            )
            return
        if not self._ctx.require_access("admin"):
            _ui.write(
                self._state.output,
                "x  Permissão negada: configuração de dispositivo exige "
                "papel admin.",
                self._ctx.dispatch,
            )
            return
        mode = self._ctx.svc_mode()
        if mode == "napalm":
            _ui.write(
                self._state.output,
                "x  Modo NAPALM não suporta aplicação de blocos VRP neste "
                "serviço. Alterne para o modo CLI/SSH padrão.",
                self._ctx.dispatch,
            )
            return

        device = self._ctx.device()
        if device is None:
            _ui.write(self._state.output,
                      "x  Nenhum device selecionado.",
                      self._ctx.dispatch)
            return
        key = device_key(str(device.name), str(device.host))
        try:
            preset = load_preset(key, "site")
        except SdnValidationError as exc:
            _ui.write(self._state.output, f"x  {exc} — nada foi aplicado.",
                      self._ctx.dispatch)
            return
        chain = _chain_of(preset)

        dialog = BlockSiteDialog(
            can_save=role_meets(self._ctx.role(), "admin"),
            chain=chain,
        )
        if not dialog.exec():
            _ui.write(self._state.output, "Operação cancelada pelo usuário.",
                      self._ctx.dispatch)
            return
        decision = dialog.get_decision()

        if decision.config_action == "save":
            self._save_chain_config(
                chain=decision.chain,
                key=key,
                flow="site",
                acl_number=decision.acl_number,
                interface=decision.interface,
                direction=decision.direction,
                applied=bool(preset.applied) if preset is not None else False,
                preexisting=False,
            )
            return

        if not self._ctx.sb.is_alive():
            _ui.write(self._state.output,
                      "x  Sem sessao SSH ativa. Conecte-se primeiro.",
                      self._ctx.dispatch)
            return
        if self._ctx.ensure_device_ready("aplicar o bloqueio") is None:
            return
        self._ctx.spawn_io(lambda: self._run_block_site(decision, key))

    def _save_chain_config(
        self,
        *,
        chain: TrafficPolicyChain | None,
        key: str,
        flow: str,
        acl_number: int,
        interface: str,
        direction: str,
        applied: bool,
        preexisting: bool,
    ) -> None:
        """Persiste a cadeia editada no JSON local (sem tocar no device).

        Não exige sessão SSH: ``Editar cadeia`` só salva a configuração.
        A auditoria registra ``block_action=chain-save`` para distinguir
        de uma aplicação real. Falha de JSON falha fechado.
        """
        if chain is None:
            _ui.write(self._state.output,
                      "x  Cadeia inválida — nada foi salvo.",
                      self._ctx.dispatch)
            return
        session = self._ctx.session
        audit: AuditLogger | None = self._ctx.audit
        svc = self._state.current_svc
        svc_name = svc.name if svc is not None else "Serviço"
        try:
            save_preset(_preset_of(
                key, flow, acl_number=acl_number, interface=interface,
                direction=direction, chain=chain, applied=applied,
                preexisting=preexisting,
            ))
        except SdnValidationError as exc:
            _ui.write(self._state.output, f"x  {exc} — nada foi salvo.",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply",
                user=getattr(session, "_user", "unknown"),
                host=getattr(session, "_host", "unknown"),
                session_id=getattr(session, "_session_id", None),
                status="error", service=svc_name, backend="cli",
                form_kind="acl", saved=False, block_action="chain-save",
            )
            return
        _ui.write(
            self._state.output,
            f"✓ Cadeia salva localmente: {chain.classifier} / "
            f"{chain.behavior} / {chain.policy} ({flow}).\n"
            "Nada foi enviado ao dispositivo — use 'Atualizar cadeia' "
            "para trocá-lo.",
            self._ctx.dispatch,
        )
        audit_config_op(
            audit, op="config_apply",
            user=getattr(session, "_user", "unknown"),
            host=getattr(session, "_host", "unknown"),
            session_id=getattr(session, "_session_id", None),
            status="ok", service=svc_name, backend="cli",
            form_kind="acl", saved=False, block_action="chain-save",
        )
        self._ctx.event_bus.put(Event(
            EventType.CONFIG_CHANGED, source="service",
            payload=CommandExecutedPayload(
                command=f"Cadeia ({flow})",
                data={"mode": "cli", "form_kind": "acl",
                      "status": "ok", "saved": False,
                      "block_action": "chain-save"},
            ),
        ))

    def _detect_applied(
        self,
        profile: AclBlockProfile | None,
        chain: TrafficPolicyChain | None = None,
    ) -> tuple[bool, str]:
        """Binding na interface: consulta real ou cache do JSON.

        Returns:
            ``(applied, fonte)`` — ``"device"`` = verificado no
            running-config; ``"cache"`` = MOCK/offline (estado estimado
            a partir do campo ``applied`` do perfil, exibido com aviso).
        """
        if profile is None:
            return False, "cache"
        if not self._ctx.sb.is_alive():
            return bool(profile.applied), "cache"
        try:
            running = self._ctx.sb.send_command("display current-configuration")
        except SdnError:
            return bool(profile.applied), "cache"
        missing = check_anchors(
            running, anchors_for(profile, "apply", chain=chain))
        return (not missing), "device"

    def _verify_block(
        self, *, anchors: tuple[str, ...], absence: tuple[str, ...]
    ) -> tuple[bool, str]:
        """Verifica presença (âncoras) ou ausência (remoção) no running."""
        try:
            running = self._ctx.sb.send_command(
                "display current-configuration")
        except SdnError as exc:
            return False, f"falha ao ler o running-config: {exc}"
        if anchors:
            absent = check_anchors(running, anchors)
            if absent:
                return False, (
                    "linha(s) não encontrada(s) no running-config: "
                    + "; ".join(absent[:5])
                )
            return True, "configuração confirmada no running-config"
        lingering = [a for a in absence if a in running]
        if lingering:
            return False, (
                "linha(s) ainda presente(s) no running-config: "
                + "; ".join(lingering[:5])
            )
        return True, "remoção confirmada no running-config"

    def _run_block(
        self, decision: BlockInternetDecision, key: str = ""
    ) -> None:
        """Executa a decisão do modal Bloquear Internet (thread de IO).

        Calcula o bloco e as funções de verificação/rollback da ação e
        delega ao motor compartilhado :meth:`_execute_block`.
        """
        action = decision.action
        profile = decision.profile
        chain = decision.chain
        config_action = decision.config_action
        old_preset = load_preset(key, "internet") if key else None
        old_chain = _chain_of(old_preset)
        preexisting = profile.created_from_snapshot

        plan = _chain_plan(
            config_action=config_action, old=old_chain,
            new=chain or suggested_chain("BLOQ", profile.acl_number),
            acl_number=profile.acl_number, interface=profile.interface,
            direction=profile.direction, preexisting=preexisting,
        )
        if config_action in ("update", "delete") and plan is None:
            _ui.write(
                self._state.output,
                "x  Cadeia anterior não encontrada — nada foi aplicado.",
                self._ctx.dispatch,
            )
            return

        rollback_fn: Callable[[str], list[str]]
        try:
            if plan is not None:
                lines = plan.lines
                anchors, absence = plan.anchors, plan.absence
                rollback_fn = plan.rollback
            else:
                lines = preview_lines(profile, action, chain=chain)
                anchors = (
                    anchors_for(profile, "apply", chain=chain)
                    if action == "apply" else ()
                )
                absence = (
                    absence_check(profile, action, chain=chain)
                    if action != "apply" else ()
                )

                def _normal_rollback(snapshot: str) -> list[str]:
                    return rollback_for(
                        profile, action, snapshot, chain=chain)

                rollback_fn = _normal_rollback
        except SdnValidationError as exc:
            _ui.write(self._state.output, f"x  {exc}",
                      self._ctx.dispatch)
            return

        def _persist(pre_state: str) -> bool:
            if config_action == "delete":
                return _delete_chain_preset(key, "internet")
            ok = (
                self._persist_block(action, profile, pre_state)
                if config_action == "" else True
            )
            effective = chain or old_chain or suggested_chain(
                "BLOQ", profile.acl_number)
            applied = (
                bool(old_preset.applied)
                if config_action == "update" and old_preset is not None
                else action == "apply"
            )
            preset_ok = _save_chain_preset(
                key, "internet", acl_number=profile.acl_number,
                interface=profile.interface, direction=profile.direction,
                chain=effective, applied=applied, preexisting=preexisting,
            )
            return ok and preset_ok

        self._execute_block(
            lines=lines,
            block_action=config_action or action,
            progress=f"Aplicando bloqueio ({config_action or action})…",
            verify_fn=lambda: self._verify_block(
                anchors=anchors, absence=absence),
            rollback_fn=rollback_fn,
            save=decision.save,
            persist_fn=_persist,
            event_command=f"Bloquear Internet ({config_action or action})",
        )

    def _run_block_site(self, decision: BlockSiteDecision, key: str = "") -> None:
        """Executa a decisão do modal Bloquear site (thread de IO).

        Além da startup-config (D3), grava/apaga o preset da cadeia por
        device/fluxo. Operações de cadeia não removem a ACL.
        """
        chain = decision.chain
        config_action = decision.config_action
        old_preset = load_preset(key, "site") if key else None
        old_chain = _chain_of(old_preset)
        preexisting = bool(old_preset.preexisting) if old_preset else False

        plan = _chain_plan(
            config_action=config_action, old=old_chain,
            new=chain or suggested_chain("SITE", decision.acl_number),
            acl_number=decision.acl_number, interface=decision.interface,
            direction=decision.direction, preexisting=preexisting,
        )
        if config_action in ("update", "delete") and plan is None:
            _ui.write(
                self._state.output,
                "x  Cadeia anterior não encontrada — nada foi aplicado.",
                self._ctx.dispatch,
            )
            return

        rollback_fn: Callable[[str], list[str]]
        try:
            if plan is not None:
                lines = plan.lines
                anchors, absence = plan.anchors, plan.absence
                rollback_fn = plan.rollback
            else:
                lines = preview_site_lines(
                    strategy=decision.strategy,
                    acl_number=decision.acl_number,
                    interface=decision.interface,
                    direction=decision.direction,
                    resolved=decision.resolved,
                    chain=chain,
                )
                anchors = site_anchors(
                    strategy=decision.strategy,
                    acl_number=decision.acl_number,
                    interface=decision.interface,
                    direction=decision.direction,
                    resolved=decision.resolved,
                    chain=chain,
                )
                absence = ()

                def _normal_site_rollback(snapshot: str) -> list[str]:
                    return site_rollback(
                        strategy=decision.strategy,
                        acl_number=decision.acl_number,
                        interface=decision.interface,
                        direction=decision.direction,
                        resolved=decision.resolved,
                        snapshot=snapshot,
                        chain=chain,
                    )

                rollback_fn = _normal_site_rollback
        except SdnValidationError as exc:
            _ui.write(self._state.output, f"x  {exc}",
                      self._ctx.dispatch)
            return

        def _persist(_pre_state: str) -> bool:
            if config_action == "delete":
                return _delete_chain_preset(key, "site")
            effective = chain or old_chain or suggested_chain(
                "SITE", decision.acl_number)
            return _save_chain_preset(
                key, "site", acl_number=decision.acl_number,
                interface=decision.interface, direction=decision.direction,
                chain=effective, applied=True, preexisting=preexisting,
            )

        block_action = (
            f"site-{config_action}" if config_action else "site-apply"
        )
        self._execute_block(
            lines=lines,
            block_action=block_action,
            progress=(
                f"Aplicando bloqueio de site "
                f"({config_action or decision.strategy})…"
            ),
            verify_fn=lambda: self._verify_block(
                anchors=anchors, absence=absence),
            rollback_fn=rollback_fn,
            save=decision.save,
            persist_fn=_persist,
            event_command=f"Bloquear site ({config_action or decision.strategy})",
        )

    def _execute_block(
        self,
        *,
        lines: list[str],
        block_action: str,
        progress: str,
        verify_fn: Callable[[], tuple[bool, str]],
        rollback_fn: Callable[[str], list[str]],
        save: bool,
        persist_fn: Callable[[str], bool] | None,
        event_command: str,
    ) -> None:
        """Motor compartilhado dos botões de bloqueio (thread de IO).

        Mesmo fluxo do ``_apply_composite``: modo MOCK → pré-checagem de
        interface → ``ConfigCommand`` (snapshot → apply → verify →
        rollback) → persistência D3 (``result.ok`` + save + admin) →
        auditoria + evento. ``persist_fn`` (``None`` no Bloquear site)
        recebe o ``pre_state`` e grava o JSON por device.
        """
        svc = self._state.current_svc
        svc_name = svc.name if svc is not None else "Serviço"

        if self._ctx.svc_mode() == "mock":
            _ui.write(
                self._state.output,
                "Modo MOCK — nada foi aplicado:\n" + "\n".join(lines),
                self._ctx.dispatch,
            )
            return

        session = self._ctx.session
        user = getattr(session, "_user", "unknown")
        host = getattr(session, "_host", "unknown")
        session_id = getattr(session, "_session_id", None)
        audit: AuditLogger | None = self._ctx.audit
        version = self._detect_vrp_version()
        spec = get_form_spec("acl")
        allow_patterns = list(spec.allow_patterns) or None

        def _apply_lines(block: list[str]) -> tuple[bool, str]:
            return self._ctx.sb.send_config_block(
                block,
                save=False,
                allow_patterns=allow_patterns,
                vrp_version=version,
            )

        pre_state = ""
        ifaces = interfaces_in_block(lines)
        if ifaces:
            try:
                pre_state = self._ctx.sb.send_command(
                    "display current-configuration")
            except SdnError as exc:
                _ui.write(
                    self._state.output,
                    f"x  Falha ao ler o running-config: {exc} — "
                    "nada foi aplicado.",
                    self._ctx.dispatch,
                )
                audit_config_op(
                    audit, op="config_apply", user=user, host=host,
                    session_id=session_id, status="blocked",
                    reason="pre-check falhou", service=svc_name,
                    backend="netmiko", form_kind="acl",
                    vrp_version=str(version), saved=False,
                    block_action=block_action,
                )
                return
            missing = missing_interfaces(pre_state, ifaces)
            if missing:
                _ui.write(
                    self._state.output,
                    "x  Interface(s) inexistente(s) no device: "
                    + ", ".join(missing)
                    + "\nVerifique o nome exato em 'display interface brief'."
                    + "\nNada foi aplicado ao dispositivo.",
                    self._ctx.dispatch,
                )
                audit_config_op(
                    audit, op="config_apply", user=user, host=host,
                    session_id=session_id, status="blocked",
                    reason=f"interface inexistente: {', '.join(missing)}",
                    service=svc_name, backend="netmiko",
                    form_kind="acl", vrp_version=str(version),
                    saved=False, block_action=block_action,
                )
                return

        service_cmd = ConfigCommand(
            lines,
            read_state=lambda: self._ctx.sb.send_command(
                "display current-configuration"),
            apply_fn=_apply_lines,
            dry_run=self._ctx.dry_run,
            verify_fn=verify_fn,
            rollback_fn=rollback_fn,
        )

        _ui.loading(self._state.output, progress, self._ctx.dispatch)
        try:
            result = service_cmd.execute()
        except SnapshotError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(self._state.output,
                      f"x  {exc} — nada foi aplicado.",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply", user=user, host=host,
                session_id=session_id, status="blocked",
                reason="snapshot falhou", service=svc_name,
                backend="netmiko", form_kind="acl",
                vrp_version=str(version), saved=False,
                block_action=block_action,
            )
            return
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            self._state.last_config_command = service_cmd
            _ui.write(self._state.output, f"x  Falha SSH: {exc}",
                      self._ctx.dispatch)
            audit_config_op(
                audit, op="config_apply", user=user, host=host,
                session_id=session_id, status="error",
                reason="falha ssh", service=svc_name,
                backend="netmiko", form_kind="acl",
                vrp_version=str(version), saved=False,
                block_action=block_action,
            )
            return

        self._state.last_config_command = service_cmd
        message = result.message

        # ── D3: persistência só com result.ok + save + papel admin ──
        saved = False
        persisted = False
        save_ok = bool(save) and role_meets(self._ctx.role(), "admin")
        if result.ok and save_ok:
            try:
                ok_save, save_msg = self._ctx.sb.save_running_config(version)
            except SdnError as exc:
                ok_save, save_msg = False, f"falha ao salvar: {exc}"
            saved = bool(ok_save)
            message = f"{message}\n{save_msg}"
            if saved and persist_fn is not None:
                persisted = persist_fn(pre_state)
        if result.ok and save_ok and not saved:
            result_status = "error"
        else:
            result_status = result.status

        if persist_fn is not None:
            if persisted:
                message += "\nPerfil de bloqueio persistido (JSON)."
            elif saved:
                message += "\nFalha ao persistir o perfil de bloqueio (JSON)."
            elif result.ok:
                message += (
                    "\nPerfil do bloqueio NÃO persistido — marque "
                    "'Salvar' para gravar na startup-config."
                )
        elif result.ok and not saved:
            message += (
                "\nNÃO persistido na startup-config — marque "
                "'Salvar' para gravar após reboot."
            )

        _ui.write(self._state.output, message, self._ctx.dispatch)
        audit_config_op(
            audit, op="config_apply", user=user, host=host,
            session_id=session_id, status=result_status,
            duration_ms=result.duration_ms, service=svc_name,
            backend="netmiko", form_kind="acl",
            vrp_version=str(version), saved=saved,
            block_action=block_action,
        )
        self._ctx.event_bus.put(Event(
            EventType.CONFIG_CHANGED, source="service",
            payload=CommandExecutedPayload(
                command=event_command,
                data={
                    "mode": "cli",
                    "form_kind": "acl",
                    "status": result_status,
                    "saved": saved,
                },
            ),
        ))

    def _persist_block(
        self, action: str, profile: AclBlockProfile, pre_state: str
    ) -> bool:
        """Grava o resultado do bloqueio no JSON por device (D2/D3).

        Chamado **apenas** após ``result.ok`` + save confirmado. Falha de
        JSON nunca derruba a operação já aplicada (fail-closed + aviso).
        """
        try:
            if action == "delete":
                delete_profile(None, profile.device_key)
                return True
            if action == "apply":
                existing = load_profile(None, profile.device_key)
                if existing is not None:
                    # A origem da ACL é decidida uma única vez (primeira
                    # persistência) — reaplicar não muda a classificação.
                    created = existing.created_from_snapshot
                else:
                    created = (
                        f"acl number {profile.acl_number}" in pre_state
                    )
            else:
                created = profile.created_from_snapshot
            save_profile(None, replace(
                profile,
                applied=(action == "apply"),
                created_from_snapshot=created,
            ))
            return True
        except SdnValidationError as exc:
            log.warning("perfil de bloqueio não persistido: %s", exc)
            return False

    def rollback_last(self) -> None:
        """Desfaz a última configuração aplicada **nesta aba** (rollback).

        O alvo é o snapshot registrado pela própria aba Serviços — o
        rollback da Config Básica (e vice-versa) é independente: cada aba
        desfaz apenas o que ela mesma aplicou.

        O rollback roda apenas na running-config — para persistir a
        reversão, marque "Salvar" e aplique novamente.
        """
        last_cmd = self._state.last_config_command
        if last_cmd is None:
            _ui.write(
                self._state.output,
                "x  Nenhuma configuração anterior aplicada nesta aba "
                "para reverter.",
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
                          f"x  Falha durante o rollback: {exc}",
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
                      "x  NAPALM: sem sessao Netmiko ativa — nada foi aplicado.",
                      self._ctx.dispatch)
            _audit_napalm_blocked(audit, user=user, host=host,
                                  session_id=session_id, service=svc.name,
                                  reason="sem conexão Netmiko exposta")
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
                      f"x  NAPALM: preview (dry-run) falhou — nada foi "
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
            log.warning("NAPALM: sem UiBridge — aplicando '%s' sem confirmação",
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
                      f"x  NAPALM: aplicação recusada pelo dispositivo — "
                      f"alteracoes descartadas.\n{sanitize_command(str(exc))}",
                      self._ctx.dispatch)
            return True
        except Exception as exc:
            # justificativa (exceção genérica): o snapshot é capturado fora do
            # try interno do backend e o driver de terceiros pode levantar erro
            # cru — vira recusa auditada, nunca fallback Netmiko.
            err = sanitize_command(str(exc))
            _ui.write(self._state.output,
                      f"x  NAPALM: falha ao aplicar — nada foi "
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
