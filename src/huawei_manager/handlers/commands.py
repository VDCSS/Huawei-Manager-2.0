"""Commands mixin — editor command execution and backup."""

from __future__ import annotations

import datetime
import os
import re

import huawei_manager.constants as C
from huawei_manager._config import audit, log
from huawei_manager._protocols import AppCoreProtocol
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
        return self._cmd_editor.toPlainText().strip()

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
            except RuntimeError:
                self._sb.invalidate_connection()
                return
        else:
            self._loading(self.out_cmd, f"Executando: {cmd}\u2026")
            try:
                result = self._sb.send_command(cmd or "")
            except RuntimeError:
                self._sb.invalidate_connection()
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
                log.exception("Dry-run falhou \u2014 aplicando config sem preview")
        self._loading(self.out_cmd, "Aplicando configuracao\u2026")
        try:
            ok, msg = self._sb.send_config(cmd.strip().splitlines())
        except RuntimeError:
            self._sb.invalidate_connection()
            self._write(self.out_cmd, "\u2718  Sessao SSH inativa. Conecte-se primeiro.")
            return
        self._write(self.out_cmd, msg)
        self._event_queue.put(Event(EventType.CONFIG_CHANGED,
                                    source="editor",
                                    payload=ConfigChangedPayload(
                                        status="ok" if ok else "error",
                                    )))

    # ══════════════════════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════════════════════
    def _do_backup(self: AppCoreProtocol, fmt: str = "") -> None:
        """Salva a running-config em arquivo TXT e registra na auditoria.

        fmt deve ser extraido da UI (self._backup_fmt_cb) ANTES de
        chamar este metodo (roda na IO thread).
        """
        self._session_tracker.touch()
        assert fmt, "_do_backup: fmt must be extracted from UI before calling"
        self._loading(self.out_backup, "Coletando configuracao para backup\u2026")
        try:
            conteudo = self._sb.send_command("display current-configuration")
        except RuntimeError:
            self._sb.invalidate_connection()
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
            audit.log_operation("backup", user=self.session._user,
                                host=host, status="ok", file=path)
            log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="backup",
                                        payload=CommandExecutedPayload(
                                            command=host,
                                            data={"file": path},
                                        )))
        except OSError as ex:
            log.error("Backup falhou: %s", ex)
            self._write(self.out_backup, f"\u2718  Erro ao salvar:\n  {ex}")
