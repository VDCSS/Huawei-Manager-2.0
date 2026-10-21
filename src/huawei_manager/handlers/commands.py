"""Commands mixin — backup de configuração.

Editor/exec/rollback migraram para ``tabs/cmd/`` (F2-cmd do plano
``plano-abas-independentes.md``); este mixin permanece só com
``_do_backup`` até a Fase 2 de Backup migrar a aba.
"""

from __future__ import annotations

import datetime
import os
import re

import huawei_manager.constants as C
from huawei_manager import _config
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload


class CommandsMixin:
    """Mixin com o backup de configuração (aba Backup)."""

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
