from __future__ import annotations

import logging

from huawei_manager.session_helpers import resolve_filter
from huawei_manager.utils import clean_output, sanitize_command

log = logging.getLogger("huawei.session")


class SessionCommandsMixin:
    """Mixin for NetmikoSession command execution methods."""

    # ── executa comando CLI ──────────────────────────────────────────
    def _cmd(self, command: str) -> str:
        if not self._conn:
            return "Sem conexao"
        try:
            out = self._conn.send_command(command, read_timeout=120)
            return clean_output(str(out))
        except Exception as e:
            log.exception("Comando falhou: %s", command)
            return f"ERRO: {e}"

    def run_cli_timing(self, cmd: str) -> str:
        if not self._conn:
            return "Sem conexao"
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-timing", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                try:
                    out = self._conn.send_command_timing(cmd, read_timeout=120)
                    ctx.set_status("ok")
                    return clean_output(str(out))
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("CLI timing falhou: %s", cmd)
                    return f"ERRO: {e}"

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
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    return f"ERRO: {e}"

    # ── get estado operacional via CLI ────────────────────────────────
    def get(self, filter_xml: str | None = None) -> str:
        cmd = resolve_filter(filter_xml) or "display ip routing-table"
        with self._lock:
            with self._audit.timed(
                "get", user=self._user, host=self._host,
                session_id=self._session_id,
            ) as ctx:
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    return f"ERRO: {e}"

    # ── edit config via CLI ───────────────────────────────────────────
    def edit_config(
        self,
        config: str,
        target: str = "running",
    ) -> tuple[bool, str]:
        if not self._conn:
            return False, "Sem conexao"
        with self._lock:
            with self._audit.timed(
                "edit-config", user=self._user, host=self._host,
                datastore=target, session_id=self._session_id,
            ) as ctx:
                try:
                    lines = [line.strip() for line in config.splitlines() if line.strip()]
                    output = self._conn.send_config_set(lines, read_timeout=120)
                    self._conn.save_config()
                    ctx.set_status("ok")
                    return True, f"OK Configuracao aplicada\n{output}"
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("edit-config falhou")
                    return False, f"ERRO: {e}"

    # ── schemas (nao aplicavel via CLI) ───────────────────────────────
    def get_schemas(self) -> str:
        return "Schemas nao disponiveis via Netmiko/CLI."

    # ── capabilities ─────────────────────────────────────────────────
    def get_capabilities(self) -> str:
        with self._lock:
            return self._cmd("display version")

    # ── comando CLI livre ─────────────────────────────────────────────
    def run_cli_rpc(self, cmd: str) -> str:
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-rpc", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("CLI falhou")
                    return f"ERRO: {e}"
