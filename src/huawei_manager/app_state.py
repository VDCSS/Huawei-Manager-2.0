from __future__ import annotations

import logging

import huawei_manager.constants as C

log = logging.getLogger("huawei_manager")


class AppStateMixin:
    def _tick_dashboard(self) -> None:
        if self._current_page == "home":
            self._refresh_dashboard()

    def _tick_vnfs(self) -> None:
        if self._current_page in ("home", "topology"):
            self._spawn_io(self._refresh_vnfs)

    def _check_session_timeout(self) -> None:
        if self._access_level == "user":
            return
        new_role = self._session_tracker.current_role
        if new_role.value != self._access_level:
            self._access_level = new_role.value
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
        self._watcher_results = results
        self._dispatch(self._rebuild_manutencao_if_active)

    def _rebuild_manutencao_if_active(self) -> None:
        if self._current_page == "manutencao":
            self._rebuild_page("manutencao")
