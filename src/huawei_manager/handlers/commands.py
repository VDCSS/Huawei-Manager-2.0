"""Commands mixin — editor command execution and backup."""

from __future__ import annotations

import datetime
import os
import re

import huawei_manager.constants as C
from huawei_manager import _config
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SnapshotError
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload, ConfigChangedPayload
from huawei_manager.sdn_controller.validator import CommandValidator


class CommandsMixin:
    """Mixin com metodos de execucao de comandos e backup."""

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR
    # ══════════════════════════════════════════════════════════════════
    def _get_editor_cmd(self: AppCoreProtocol) -> str:
        """Retorna o texto atual do editor de comandos."""
        editor = self._cmd_editor
        return "" if editor is None else editor.toPlainText().strip()

    def _confirm_destructive(self: AppCoreProtocol, cmd: str) -> bool:
        """Valida o comando e pede confirmacao explicita para bypass de politica.

        Roda na UI thread (antes do _run). Retorna False se o comando for
        bloqueado ou se o operador cancelar um comando destrutivo liberado
        por privilegio elevado (admin/tecnico).
        """
        validator: CommandValidator | None = self._cmd_validator
        if validator is None:
            return True
        vr = validator.validate(cmd, self._access_level)
        if not vr.allowed:
            self._write(self.out_cmd, f"\u2718  Comando bloqueado: {vr.reason}")
            return False
        if vr.bypass_2fa:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "Confirmar comando destrutivo",
                f"O comando abaixo e destrutivo e foi liberado por privilegio elevado:\n\n"
                f"{cmd}\n\nExecutar mesmo assim?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._write(self.out_cmd, "\u2718  Comando cancelado pelo usuario.")
                return False
        return True

    def _run_cmd_safe(self: AppCoreProtocol, cmd: str = "") -> None:
        """Despacha _exec_cmd apos validacao + confirmacao (UI thread)."""
        if not cmd:
            return
        if not self._confirm_destructive(cmd):
            return
        self._run(lambda: self._exec_cmd(cmd))

    def _run_config_safe(self: AppCoreProtocol, cmd: str = "") -> None:
        """Despacha _exec_config apos validacao + confirmacao (UI thread)."""
        if not cmd:
            return
        if not self._confirm_destructive(cmd):
            return
        self._run(lambda: self._exec_config(cmd))

    def _exec_cmd(self: AppCoreProtocol, cmd: str = "") -> None:
        """Executa o comando do editor, opcionalmente dentro de system-view.

        cmd deve ser extraido do editor ANTES de chamar este metodo
        (roda na IO thread).
        """
        self._session_tracker.touch()
        if not cmd:
            self._write(self.out_cmd, "\u2718  Editor vazio \u2014 digite um comando")
            return
        validator: CommandValidator | None = self._cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._access_level)
            if not vr.allowed:
                self._write(self.out_cmd, f"\u2718  Comando bloqueado: {vr.reason}")
                return
        if self._sysview_var:
            self._loading(self.out_cmd,
                          "system-view \u2192 " + cmd.splitlines()[0] + " \u2192 quit\u2026")
            try:
                _ok, result = self._sb.send_config(cmd.strip().splitlines())
            except SdnError as exc:
                self._sb.invalidate_connection()
                self._write(self.out_cmd, f"\u2718  Falha SSH: {exc}")
                return
        else:
            self._loading(self.out_cmd, f"Executando: {cmd}\u2026")
            try:
                result = self._sb.send_command(cmd or "")
            except SdnError as exc:
                self._sb.invalidate_connection()
                self._write(self.out_cmd, f"\u2718  Falha SSH: {exc}")
                return
        self._write(self.out_cmd, result)
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="editor",
                                    payload=CommandExecutedPayload(command=cmd.splitlines()[0])))

    def _exec_config(self: AppCoreProtocol, cmd: str = "") -> None:
        """Envia comandos de configuracao do editor via send_config.

        cmd deve ser extraido do editor ANTES de chamar este metodo
        (roda na IO thread).
        """
        self._session_tracker.touch()
        if not cmd:
            self._write(self.out_cmd,
                         "\u2718  Editor vazio \u2014 digite os comandos de configuracao")
            return
        validator: CommandValidator | None = self._cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._access_level)
            if not vr.allowed:
                self._write(self.out_cmd, f"\u2718  Config bloqueada: {vr.reason}")
                return
        dry_run: DryRunEngine | None = self._dry_run
        if dry_run is not None and self.session.is_connected:
            try:
                current = self.session.run_cli_rpc("display current-configuration")
                diff_report = dry_run.diff(current, cmd)
                if diff_report.has_changes:
                    preview = diff_report.summary + "\n\n"
                    for line in diff_report.added[:10]:
                        preview += line
                    for line in diff_report.removed[:10]:
                        preview += line
                    self._loading(self.out_cmd, f"Dry-run: {diff_report.summary}")
                else:
                    self._write(self.out_cmd, "\u2139  Nenhuma alteracao detectada em relacao a config atual.")
                    return
            except Exception:
                # Protecao falhou -> NAO aplicar: seguir sem preview violaria
                # o contrato de dry-run (mudanca de estado sem visibilidade).
                if _config.log is not None:
                    _config.log.exception("Dry-run falhou \u2014 abortando aplicacao de config")
                self._write(
                    self.out_cmd,
                    "\u2718  Dry-run falhou \u2014 configuracao NAO aplicada. Verifique o log.",
                )
                return
        self._loading(self.out_cmd, "Aplicando configuracao\u2026")
        # Command pattern: snapshot pré-mudança (fail-closed) + mutação.
        # Sem snapshot não há rollback possível — nada é aplicado.
        command = ConfigCommand(
            cmd.strip().splitlines(),
            read_state=lambda: self._sb.send_command(
                "display current-configuration"),
            apply_fn=lambda lines: self._sb.send_config(lines),
            dry_run=dry_run,
        )
        try:
            result = command.execute()
        except SnapshotError as exc:
            self._sb.invalidate_connection()
            self._write(self.out_cmd,
                         f"\u2718  {exc} \u2014 configura\u00e7\u00e3o N\u00c3O aplicada.")
            audit_config_op(
                _config.audit,
                op="config_apply",
                user=self.session._user,
                host=self.session._host,
                status="blocked",
                reason="snapshot falhou",
            )
            return
        except SdnError as exc:
            # Falha na aplicação: a conexão pode ter caído no meio da
            # mutação — invalida e mantém o comando (snapshot válido)
            # para permitir rollback depois de reconectar.
            self._sb.invalidate_connection()
            self._last_config_command = command
            self._write(self.out_cmd, f"\u2718  Falha SSH: {exc}")
            audit_config_op(
                _config.audit,
                op="config_apply",
                user=self.session._user,
                host=self.session._host,
                status="error",
                reason="falha ssh",
                lines=len(command.lines),
            )
            return
        self._last_config_command = command
        self._write(self.out_cmd, result.message)
        audit_config_op(
            _config.audit,
            op="config_apply",
            user=self.session._user,
            host=self.session._host,
            status=result.status,
            duration_ms=result.duration_ms,
            lines=len(command.lines),
        )
        self._event_queue.put(Event(EventType.CONFIG_CHANGED,
                                    source="editor",
                                    payload=ConfigChangedPayload(
                                        status=result.status,
                                    )))

    # ══════════════════════════════════════════════════════════════════
    #  ROLLBACK (Command pattern)
    # ══════════════════════════════════════════════════════════════════
    def _rollback_last_config(self: AppCoreProtocol) -> None:
        """Desfaz a última configuração aplicada (UI thread → _run).

        Sem snapshot registrado não faz nada (nada a desfazer). O
        trabalho pesado (leitura/diff/envio) roda na IO thread via
        ``_run``, que também garante dispositivo selecionado + sessão.
        """
        command = self._last_config_command
        if command is None:
            self._write(
                self.out_cmd,
                "\u2139  Nada a desfazer \u2014 nenhuma configura\u00e7\u00e3o "
                "aplicada nesta sess\u00e3o.",
            )
            return
        self._run(lambda: self._do_rollback_config(command))

    def _do_rollback_config(self: AppCoreProtocol,
                            command: ConfigCommand) -> None:
        """Executa o rollback do ``command`` (IO thread)."""
        self._session_tracker.touch()
        self._loading(self.out_cmd, "Desfazendo \u00faltima configura\u00e7\u00e3o\u2026")
        try:
            result = command.rollback()
        except SdnError as exc:
            self._sb.invalidate_connection()
            self._write(self.out_cmd,
                         f"\u2718  Falha SSH no rollback: {exc}")
            audit_config_op(
                _config.audit,
                op="config_rollback",
                user=self.session._user,
                host=self.session._host,
                status="error",
                reason="falha ssh",
            )
            self._dispatch(lambda: self._set_status(
                "Rollback: falha SSH", C.NEON_RED))
            return
        self._write(self.out_cmd, result.message)
        if result.ok:
            # Restauração completa confirmada por verificação — não há
            # mais o que desfazer; parcial/error mantêm o snapshot para
            # nova tentativa ou diagnóstico.
            self._last_config_command = None
        audit_config_op(
            _config.audit,
            op="config_rollback",
            user=self.session._user,
            host=self.session._host,
            status=result.status,
            duration_ms=result.duration_ms,
            restored=result.restored,
            pending=result.pending,
        )
        self._event_queue.put(Event(EventType.CONFIG_CHANGED,
                                    source="editor",
                                    payload=ConfigChangedPayload(
                                        status=result.status,
                                    )))
        color = (C.NEON_CYAN if result.ok
                 else C.NEON_AMBER if result.status == "partial"
                 else C.NEON_RED)
        self._dispatch(lambda: self._set_status(
            f"Rollback: {result.status}", color))

    # ══════════════════════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════════════════════
    def _do_backup(self: AppCoreProtocol, fmt: str = "") -> None:
        """Salva a running-config em arquivo TXT e registra na auditoria.

        fmt vem da constante C.BACKUP_FMT_TEXT (único formato suportado),
        extraído na UI thread antes de chamar este método (roda na IO thread).
        """
        self._session_tracker.touch()
        if not fmt:
            raise RuntimeError("_do_backup: fmt must be extracted from UI before calling")
        self._loading(self.out_backup, "Coletando configuracao para backup\u2026")
        try:
            conteudo = self._sb.send_command("display current-configuration")
        except SdnError as exc:
            self._sb.invalidate_connection()
            self._write(self.out_backup, f"\u2718  Falha SSH: {exc}")
            return
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext  = "txt"
        host = re.sub(r'[^a-zA-Z0-9._-]', '_', self.session._host)
        nome = f"backup_{host}_{ts}.{ext}"
        pasta = self.backup_path or os.path.expanduser("~")
        path  = os.path.join(pasta, nome)
        try:
            os.makedirs(pasta, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                header = (
                    f"# Backup CLI\n"
                    f"# Host   : {host}\n"
                    f"# User   : {self.session._user}\n"
                    f"# Data   : {ts}\n\n"
                )
                fh.write(header + conteudo)
            linhas = conteudo.count("\n") + 1
            resumo = (
                f"\u2714  Backup concluido!\n{'-' * 60}\n"
                f"  Arquivo  : {path}\n"
                f"  Formato  : {fmt}\n"
                f"  Data     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"  Linhas   : {linhas}\n"
                f"  Tamanho  : {os.path.getsize(path):,} bytes\n"
                f"{'-' * 60}\n\nPrevia (40 linhas):\n\n"
                + "\n".join(conteudo.splitlines()[:40])
            )
            self._write(self.out_backup, resumo)
            self._dispatch(lambda: self._set_status(f"Backup: {nome}", C.NEON_CYAN))
            if _config.audit is not None:
                _config.audit.log_operation("backup", user=self.session._user,
                                    host=host, status="ok", file=path)
            if _config.log is not None:
                _config.log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="backup",
                                        payload=CommandExecutedPayload(
                                            command=host,
                                            data={"file": path},
                                        )))
        except OSError as ex:
            if _config.log is not None:
                _config.log.error("Backup falhou: %s", ex)
            self._write(self.out_backup, f"\u2718  Erro ao salvar:\n  {ex}")
