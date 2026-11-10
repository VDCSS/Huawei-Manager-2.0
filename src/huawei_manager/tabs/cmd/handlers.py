"""Handlers da aba Editor de Comandos — execução, config e rollback.

Extraído de ``handlers/commands.py`` (F2-cmd do plano
``plano-abas-independentes.md``): as seções EDITOR e ROLLBACK do
``CommandsMixin`` viraram a classe injetada :class:`CmdHandlers`
``(ctx, state)`` — sem leitura do App, só do :class:`TabContext`.
``_do_backup`` permanece no mixin legado até a Fase 2 de backup.

Segurança (inalterada): validação RBAC via ``ctx.cmd_validator`` +
``ctx.role()``, confirmação explícita de bypass 2FA (QMessageBox na UI
thread), snapshot fail-closed do ``ConfigCommand`` antes de aplicar,
dry-run aborta aplicação se falhar, e toda falha SSH invalida a conexão
e audita a operação.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import huawei_manager.constants as C
from huawei_manager import _config
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SnapshotError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload, ConfigChangedPayload
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.cmd.state import CmdState


class CmdHandlers:
    """Execução do editor: UI thread (safe) → ctx.run → IO thread (exec)."""

    def __init__(self, ctx: TabContext, state: CmdState) -> None:
        self._ctx = ctx
        self._state = state

    # ══════════════════════════════════════════════════════════════
    #  EDITOR
    # ══════════════════════════════════════════════════════════════
    def confirm_destructive(self, cmd: str) -> bool:
        """Valida o comando e pede confirmacao explicita para bypass de politica.

        Roda na UI thread (antes do run). Retorna False se o comando for
        bloqueado ou se o operador cancelar um comando destrutivo liberado
        por privilegio elevado (admin/tecnico).
        """
        validator = self._ctx.cmd_validator
        if validator is None:
            return True
        vr = validator.validate(cmd, self._ctx.role())
        if not vr.allowed:
            _ui.write(self._state.out, f"✘  Comando bloqueado: {vr.reason}",
                      self._ctx.dispatch)
            return False
        if vr.bypass_2fa:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "Confirmar comando destrutivo",
                f"O comando abaixo e destrutivo e foi liberado por privilegio elevado:\n\n"
                f"{cmd}\n\nExecutar mesmo assim?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                _ui.write(self._state.out, "✘  Comando cancelado pelo usuario.",
                          self._ctx.dispatch)
                return False
        return True

    def run_cmd_safe(self, cmd: str = "") -> None:
        """Despacha exec_cmd apos validacao + confirmacao (UI thread)."""
        if not cmd:
            return
        if not self.confirm_destructive(cmd):
            return
        self._ctx.run(lambda: self.exec_cmd(cmd))

    def run_config_safe(self, cmd: str = "") -> None:
        """Despacha exec_config apos validacao + confirmacao (UI thread)."""
        if not cmd:
            return
        if not self.confirm_destructive(cmd):
            return
        self._ctx.run(lambda: self.exec_config(cmd))

    def exec_cmd(self, cmd: str = "") -> None:
        """Executa o comando do editor, opcionalmente dentro de system-view.

        cmd deve ser extraido do editor ANTES de chamar este metodo
        (roda na IO thread).
        """
        self._ctx.touch_session()
        out = self._state.out
        dispatch = self._ctx.dispatch
        if not cmd:
            _ui.write(out, "✘  Editor vazio — digite um comando", dispatch)
            return
        validator = self._ctx.cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._ctx.role())
            if not vr.allowed:
                _ui.write(out, f"✘  Comando bloqueado: {vr.reason}", dispatch)
                return
        if self._state.sysview_var:
            _ui.loading(out,
                        "system-view → " + cmd.splitlines()[0] + " → quit…",
                        dispatch)
            try:
                _ok, result = self._ctx.sb.send_config(cmd.strip().splitlines())
            except SdnError as exc:
                self._ctx.sb.invalidate_connection()
                _ui.write(out, f"✘  Falha SSH: {exc}", dispatch)
                return
        else:
            _ui.loading(out, f"Executando: {cmd}…", dispatch)
            try:
                result = self._ctx.sb.send_command(cmd or "")
            except SdnError as exc:
                self._ctx.sb.invalidate_connection()
                _ui.write(out, f"✘  Falha SSH: {exc}", dispatch)
                return
        _ui.write(out, result, dispatch)
        self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                      source="editor",
                                      payload=CommandExecutedPayload(
                                          command=cmd.splitlines()[0])))

    def exec_config(self, cmd: str = "") -> None:
        """Envia comandos de configuracao do editor via send_config.

        cmd deve ser extraido do editor ANTES de chamar este metodo
        (roda na IO thread).
        """
        self._ctx.touch_session()
        out = self._state.out
        dispatch = self._ctx.dispatch
        if not cmd:
            _ui.write(out, "✘  Editor vazio — digite os comandos de configuracao",
                      dispatch)
            return
        validator = self._ctx.cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._ctx.role())
            if not vr.allowed:
                _ui.write(out, f"✘  Config bloqueada: {vr.reason}", dispatch)
                return
        dry_run = self._ctx.dry_run
        session = self._ctx.session
        if dry_run is not None and session.is_connected:
            try:
                current = session.run_cli_rpc("display current-configuration")
                diff_report = dry_run.diff(current, cmd)
                if diff_report.has_changes:
                    preview = diff_report.summary + "\n\n"
                    for line in diff_report.added[:10]:
                        preview += line
                    for line in diff_report.removed[:10]:
                        preview += line
                    _ui.loading(out, f"Dry-run: {diff_report.summary}", dispatch)
                else:
                    _ui.write(out, "ℹ  Nenhuma alteracao detectada em relacao a config atual.",
                              dispatch)
                    return
            except Exception:
                # Protecao falhou -> NAO aplicar: seguir sem preview violaria
                # o contrato de dry-run (mudanca de estado sem visibilidade).
                if _config.log is not None:
                    _config.log.exception("Dry-run falhou — abortando aplicacao de config")
                _ui.write(
                    out,
                    "✘  Dry-run falhou — configuracao NAO aplicada. Verifique o log.",
                    dispatch,
                )
                return
        _ui.loading(out, "Aplicando configuracao…", dispatch)
        # Command pattern: snapshot pré-mudança (fail-closed) + mutação.
        # Sem snapshot não há rollback possível — nada é aplicado.
        command = ConfigCommand(
            cmd.strip().splitlines(),
            read_state=lambda: self._ctx.sb.send_command(
                "display current-configuration"),
            apply_fn=lambda lines: self._ctx.sb.send_config(lines),
            dry_run=dry_run,
        )
        try:
            result = command.execute()
        except SnapshotError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(out, f"✘  {exc} — configuração NÃO aplicada.", dispatch)
            audit_config_op(
                _config.audit,
                op="config_apply",
                user=session._user,
                host=session._host,
                status="blocked",
                reason="snapshot falhou",
            )
            return
        except SdnError as exc:
            # Falha na aplicação: a conexão pode ter caído no meio da
            # mutação — invalida e mantém o comando (snapshot válido)
            # para permitir rollback depois de reconectar.
            self._ctx.sb.invalidate_connection()
            self._ctx.set_last_config_command(command)
            _ui.write(out, f"✘  Falha SSH: {exc}", dispatch)
            audit_config_op(
                _config.audit,
                op="config_apply",
                user=session._user,
                host=session._host,
                status="error",
                reason="falha ssh",
                lines=len(command.lines),
            )
            return
        self._ctx.set_last_config_command(command)
        _ui.write(out, result.message, dispatch)
        audit_config_op(
            _config.audit,
            op="config_apply",
            user=session._user,
            host=session._host,
            status=result.status,
            duration_ms=result.duration_ms,
            lines=len(command.lines),
        )
        self._ctx.event_bus.put(Event(EventType.CONFIG_CHANGED,
                                      source="editor",
                                      payload=ConfigChangedPayload(
                                          status=result.status,
                                      )))

    # ══════════════════════════════════════════════════════════════
    #  ROLLBACK (Command pattern)
    # ══════════════════════════════════════════════════════════════
    def rollback_last_config(self) -> None:
        """Desfaz a última configuração aplicada (UI thread → run).

        Sem snapshot registrado não faz nada (nada a desfazer). O
        trabalho pesado (leitura/diff/envio) roda na IO thread via
        ``ctx.run``, que também garante dispositivo selecionado + sessão.
        """
        command = self._ctx.get_last_config_command()
        if command is None:
            _ui.write(
                self._state.out,
                "ℹ  Nada a desfazer — nenhuma configuração "
                "aplicada nesta sessão.",
                self._ctx.dispatch,
            )
            return
        self._ctx.run(lambda: self.do_rollback_config(command))

    def do_rollback_config(self, command: ConfigCommand) -> None:
        """Executa o rollback do ``command`` (IO thread)."""
        self._ctx.touch_session()
        out = self._state.out
        dispatch = self._ctx.dispatch
        _ui.loading(out, "Desfazendo última configuração…", dispatch)
        session = self._ctx.session
        try:
            result = command.rollback()
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(out, f"✘  Falha SSH no rollback: {exc}", dispatch)
            audit_config_op(
                _config.audit,
                op="config_rollback",
                user=session._user,
                host=session._host,
                status="error",
                reason="falha ssh",
            )
            dispatch(lambda: self._ctx.set_status(
                "Rollback: falha SSH", C.NEON_RED))
            return
        _ui.write(out, result.message, dispatch)
        if result.ok:
            # Restauração completa confirmada por verificação — não há
            # mais o que desfazer; parcial/error mantêm o snapshot para
            # nova tentativa ou diagnóstico.
            self._ctx.set_last_config_command(None)
        audit_config_op(
            _config.audit,
            op="config_rollback",
            user=session._user,
            host=session._host,
            status=result.status,
            duration_ms=result.duration_ms,
            restored=result.restored,
            pending=result.pending,
        )
        self._ctx.event_bus.put(Event(EventType.CONFIG_CHANGED,
                                      source="editor",
                                      payload=ConfigChangedPayload(
                                          status=result.status,
                                      )))
        color = (C.NEON_CYAN if result.ok
                 else C.NEON_AMBER if result.status == "partial"
                 else C.NEON_RED)
        dispatch(lambda: self._ctx.set_status(
            f"Rollback: {result.status}", color))
