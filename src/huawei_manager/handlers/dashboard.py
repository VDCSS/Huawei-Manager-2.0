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
        status_lbl = self._dash_conn_status
        host_lbl = self._dash_conn_host
        online_lbl = self._dash_device_online
        offline_lbl = self._dash_device_offline
        unknown_lbl = self._dash_device_unknown
        audit_text = self._dash_audit_text
        if (
            status_lbl is None or host_lbl is None or online_lbl is None
            or offline_lbl is None or unknown_lbl is None or audit_text is None
        ):
            return
        try:
            conn = self._sb.is_alive()
        except Exception:
            conn = False
        if conn:
            host = getattr(self.session, "_host", "?")
            status_lbl.setText("Online")
            status_lbl.setStyleSheet(
                f"color: {C.NEON_CYAN}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            host_lbl.setText(f"Host: {host}")
        else:
            status_lbl.setText("Desconectado")
            status_lbl.setStyleSheet(
                f"color: {C.NEON_RED}; font: bold 14px {C.FONT_UI_FAMILY}; background: {C.BG_INPUT};")
            host_lbl.setText("Host: ---")

        devices = self._devices
        online = sum(1 for d in devices if getattr(d, "status", "") == "online")
        offline = sum(1 for d in devices if getattr(d, "status", "") == "offline")
        unknown = sum(1 for d in devices if getattr(d, "status", "") not in ("online", "offline"))
        online_lbl.setText(f"Online: {online}")
        offline_lbl.setText(f"Offline: {offline}")
        unknown_lbl.setText(f"Desconhecido: {unknown}")

        try:
            text = audit.format_tail(5) if audit is not None else "  (nenhuma entrada de auditoria ainda)"
        except Exception:
            text = "  (erro ao ler auditoria)"
        audit_text.setReadOnly(False)
        audit_text.clear()
        audit_text.setPlainText(text)
        audit_text.setReadOnly(True)
