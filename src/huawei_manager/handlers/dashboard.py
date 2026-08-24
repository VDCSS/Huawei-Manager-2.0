"""Dashboard mixin — dashboard refresh handlers."""

from __future__ import annotations

import logging

import huawei_manager.constants as C
from huawei_manager._config import audit
from huawei_manager._protocols import AppCoreProtocol

log = logging.getLogger(__name__)


class DashboardMixin:
    """Mixin com metodos de atualizacao do dashboard."""

    def _refresh_dashboard(self: AppCoreProtocol) -> None:
        try:
            conn = self._sb.is_alive()
        except Exception:
            conn = False
        if conn:
            host = getattr(self.session, "_host", "?")
            self._dash_conn_status.setText("Online")
            self._dash_conn_status.setStyleSheet(
                f"color: {C.NEON_CYAN}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            self._dash_conn_host.setText(f"Host: {host}")
        else:
            self._dash_conn_status.setText("Desconectado")
            self._dash_conn_status.setStyleSheet(
                f"color: {C.NEON_RED}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            self._dash_conn_host.setText("Host: ---")

        devices = self._devices
        online = sum(1 for d in devices if getattr(d, "status", "") == "online")
        offline = sum(1 for d in devices if getattr(d, "status", "") == "offline")
        unknown = sum(1 for d in devices if getattr(d, "status", "") not in ("online", "offline"))
        self._dash_device_online.setText(f"Online: {online}")
        self._dash_device_offline.setText(f"Offline: {offline}")
        self._dash_device_unknown.setText(f"Desconhecido: {unknown}")

        try:
            text = audit.format_tail(5)
        except Exception:
            text = "  (erro ao ler auditoria)"
        self._dash_audit_text.setReadOnly(False)
        self._dash_audit_text.clear()
        self._dash_audit_text.setPlainText(text)
        self._dash_audit_text.setReadOnly(True)
