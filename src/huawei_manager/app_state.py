from __future__ import annotations

import logging

import huawei_manager.constants as C
from huawei_manager.sdn_controller.event_queue import Event, EventType

log = logging.getLogger("huawei_manager")


class AppStateMixin:
    def _on_sdn_event(self, ev: Event | None) -> None:
        if ev is None:
            return
        try:
            if ev.type is EventType.DEVICE_DISCONNECTED:
                self._topo_canvas.set_device_status(ev.source, "offline")
            elif ev.type is EventType.DEVICE_CONNECTED:
                self._topo_canvas.set_device_status(ev.source, "online")
            elif ev.type is EventType.CONFIG_CHANGED:
                self._tick_dashboard()
            else:
                log.debug("_on_sdn_event sem efeito na UI: %s/%s", ev.type.name, ev.source)
        except Exception:
            log.exception("_on_sdn_event falhou (type=%s, source=%s)", ev.type, ev.source)

    def _tick_dashboard(self) -> None:
        if self._current_page == "home":
            self._refresh_dashboard()

    def _tick_devices(self) -> None:
        self._spawn_io(self._refresh_devices)

    def _check_session_timeout(self) -> None:
        if self._access_level == "user":
            return
        new_role = self._session_tracker.current_role
        if new_role.value != self._access_level:
            self._access_level = new_role.value
            self._sb.set_access_role("user")
            self._mock_mode = False
            self._watcher.stop()
            self._rebuild_page("topology")
            log.info("Acesso: timeout de sessao — resetado para user")

    def _set_status(self, text: str, color: str) -> None:
        self.status_dot.setStyleSheet(
            f"color: {color}; background: {C.BG_BASE}; font: 16px 'Inter';")
        self.status_lbl.setText(text)

    def _set_conn_btn(self, text: str = "  CONECTAR  ", disabled: bool = False) -> None:
        btn = self.conn_btn
        self._dispatch(lambda: (
            btn.setText(text),
            btn.setEnabled(not disabled),
        ))

    def _on_watcher_update(self, results) -> None:
        self._watcher_results = tuple(results)  # snapshot (R18) — cópia imutável
        self._dispatch(self._rebuild_manutencao_if_active)

    def _rebuild_manutencao_if_active(self) -> None:
        if self._current_page == "manutencao":
            self._rebuild_page("manutencao")
