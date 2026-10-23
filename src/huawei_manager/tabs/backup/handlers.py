"""Handler da aba Backup — coleta a running-config e grava em arquivo.

Extraído de ``handlers/commands.py`` (F2-backup do plano
``plano-abas-independentes.md``): o ``_do_backup`` do ``CommandsMixin``
virou a classe injetada :class:`BackupHandlers` ``(ctx, state)`` — sem
leitura do App, só do :class:`TabContext`.

Segurança (inalterada): conexão invalidada em falha SSH, escrita do
resumo na saída da aba, entrada de auditoria (``log_operation``) e evento
``COMMAND_EXECUTED`` publicado no event bus.
"""
from __future__ import annotations

import datetime
import os
import re
from typing import TYPE_CHECKING

import huawei_manager.constants as C
from huawei_manager import _config
from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.backup.state import BackupState


class BackupHandlers:
    """Execução do backup (IO thread — chamado via ``ctx.run``)."""

    def __init__(self, ctx: TabContext, state: BackupState) -> None:
        self._ctx = ctx
        self._state = state

    def do_backup(self, fmt: str = "") -> None:
        """Salva a running-config em arquivo TXT e registra na auditoria.

        fmt vem da constante C.BACKUP_FMT_TEXT (único formato suportado),
        extraído na UI thread antes de chamar este método (roda na IO thread).
        """
        self._ctx.touch_session()
        if not fmt:
            raise RuntimeError("_do_backup: fmt must be extracted from UI before calling")
        out = self._state.out
        dispatch = self._ctx.dispatch
        _ui.loading(out, "Coletando configuracao para backup…", dispatch)
        try:
            conteudo = self._ctx.sb.send_command("display current-configuration")
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(out, f"✘  Falha SSH: {exc}", dispatch)
            return
        session = self._ctx.session
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "txt"
        host = re.sub(r'[^a-zA-Z0-9._-]', '_', session._host)
        nome = f"backup_{host}_{ts}.{ext}"
        pasta = self._state.backup_path or os.path.expanduser("~")
        path = os.path.join(pasta, nome)
        try:
            os.makedirs(pasta, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                header = (
                    f"# Backup CLI\n"
                    f"# Host   : {host}\n"
                    f"# User   : {session._user}\n"
                    f"# Data   : {ts}\n\n"
                )
                fh.write(header + conteudo)
            linhas = conteudo.count("\n") + 1
            resumo = (
                f"✔  Backup concluido!\n{'-' * 60}\n"
                f"  Arquivo  : {path}\n"
                f"  Formato  : {fmt}\n"
                f"  Data     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"  Linhas   : {linhas}\n"
                f"  Tamanho  : {os.path.getsize(path):,} bytes\n"
                f"{'-' * 60}\n\nPrevia (40 linhas):\n\n"
                + "\n".join(conteudo.splitlines()[:40])
            )
            _ui.write(out, resumo, dispatch)
            dispatch(lambda: self._ctx.set_status(f"Backup: {nome}", C.NEON_CYAN))
            if _config.audit is not None:
                _config.audit.log_operation("backup", user=session._user,
                                    host=host, status="ok", file=path)
            if _config.log is not None:
                _config.log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
            self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                        source="backup",
                                        payload=CommandExecutedPayload(
                                            command=host,
                                            data={"file": path},
                                        )))
        except OSError as ex:
            if _config.log is not None:
                _config.log.error("Backup falhou: %s", ex)
            _ui.write(out, f"✘  Erro ao salvar:\n  {ex}", dispatch)
