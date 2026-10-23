"""Handler da aba Dashboard — refresh de conexão, devices e auditoria.

Extraído de ``handlers/dashboard.py`` (``DashboardMixin._refresh_dashboard``,
F2-home do plano ``plano-abas-independentes.md``): a classe injetada
:class:`HomeHandlers` ``(ctx, state)`` lê só o :class:`TabContext`.
Roda na thread GUI (timer do shell chama a fachada sem ``ctx.run`` —
não é operação de IO; paridade legada: sem dispatch).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import huawei_manager.constants as C
from huawei_manager import _config

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.home.state import HomeState


class HomeHandlers:
    """Refresh do dashboard (chamado direto na thread GUI)."""

    def __init__(self, ctx: TabContext, state: HomeState) -> None:
        self._ctx = ctx
        self._state = state

    def refresh_dashboard(self) -> None:
        status_lbl = self._state.conn_status
        host_lbl = self._state.conn_host
        online_lbl = self._state.device_online
        offline_lbl = self._state.device_offline
        unknown_lbl = self._state.device_unknown
        audit_text = self._state.audit_text
        if (
            status_lbl is None or host_lbl is None or online_lbl is None
            or offline_lbl is None or unknown_lbl is None or audit_text is None
        ):
            return
        try:
            conn = self._ctx.sb.is_alive()
        except Exception:
            conn = False
        if conn:
            host = getattr(self._ctx.session, "_host", "?")
            status_lbl.setText("Online")
            status_lbl.setStyleSheet(
                f"color: {C.NEON_CYAN}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            host_lbl.setText(f"Host: {host}")
        else:
            status_lbl.setText("Desconectado")
            status_lbl.setStyleSheet(
                f"color: {C.NEON_RED}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            host_lbl.setText("Host: ---")

        devices = self._ctx.devices()
        online = sum(1 for d in devices if getattr(d, "status", "") == "online")
        offline = sum(1 for d in devices if getattr(d, "status", "") == "offline")
        unknown = sum(1 for d in devices if getattr(d, "status", "") not in ("online", "offline"))
        online_lbl.setText(f"Online: {online}")
        offline_lbl.setText(f"Offline: {offline}")
        unknown_lbl.setText(f"Desconhecido: {unknown}")

        try:
            audit_log = _config.audit
            text = (
                audit_log.format_tail(5)
                if audit_log is not None
                else "  (nenhuma entrada de auditoria ainda)"
            )
        except Exception:
            text = "  (erro ao ler auditoria)"
        audit_text.setReadOnly(False)
        audit_text.clear()
        audit_text.setPlainText(text)
        audit_text.setReadOnly(True)
