from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from huawei_manager.exceptions import SdnCommandError, SdnConnectionError
from huawei_manager.session_helpers import resolve_filter
from huawei_manager.utils import clean_output, sanitize_command

if TYPE_CHECKING:
    import threading

    from netmiko.base_connection import BaseConnection as NetmikoConnection  # pyright: ignore[reportMissingTypeStubs]

    from huawei_manager.audit_log import AuditLogger

log = logging.getLogger("huawei.session")


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

    # ── executa comando CLI ──────────────────────────────────────────
    def _cmd(self, command: str) -> str:
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        try:
            out = self._conn.send_command(command, read_timeout=120)
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
    ) -> tuple[bool, str]:
        if not self._conn:
            raise SdnConnectionError("Sem conexao ativa")
        with self._lock:
            with self._audit.timed(
                "edit-config", user=self._user, host=self._host,
                datastore=target, session_id=self._session_id,
            ) as ctx:
                lines = [line.strip() for line in config.splitlines() if line.strip()]
                output = self._conn.send_config_set(lines, read_timeout=120)
                # Persistir na startup-config e mudanca de estado duradoura:
                # so acontece com save=True explicito (fail-closed por padrao).
                if save:
                    self._conn.save_config()
                ctx.set_status("ok")
                saved = " e salva" if save else " (running-config; use save=True para persistir)"
                return True, f"OK Configuracao aplicada{saved}\n{output}"

    # ── comando CLI livre ─────────────────────────────────────────────
    def run_cli_rpc(self, cmd: str) -> str:
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-rpc", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                result = self._cmd(cmd)
                ctx.set_status("ok")
                return result
