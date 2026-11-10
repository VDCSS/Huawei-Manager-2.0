"""Testes para troca de tema — restauração do estado de conexão (B4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.app import AppCore


def _make_connected_app() -> MagicMock:
    """Mock de AppCore com header simulando sessão conectada."""
    from huawei_manager.app import AppCore
    app = MagicMock(spec=AppCore)
    app._theme = "dark"
    app._theme_toggling = False
    app._current_page = "cmd"
    app._active_btn = None
    app.pages = {"cmd": MagicMock()}
    app._nav_buttons = {"cmd": MagicMock()}
    app.theme_btn = MagicMock()
    app._rebuild_ui = MagicMock()
    app._set_status = MagicMock()
    app._set_conn_btn = MagicMock()
    app._show_page = MagicMock()

    status_lbl = MagicMock()
    status_lbl.text.return_value = "Conectado"
    status_dot = MagicMock()
    status_dot.styleSheet.return_value = (
        "color: #00e5ff; background: #0b0e14; font: 16px 'Inter';")
    conn_btn = MagicMock()
    conn_btn.text.return_value = "  DESCONECTAR  "
    conn_btn.isEnabled.return_value = True
    app.status_lbl = status_lbl
    app.status_dot = status_dot
    app.conn_btn = conn_btn
    return app


class TestThemeRestoresConnection:
    def test_toggle_preserves_connected_header(self):
        app = _make_connected_app()
        with patch("huawei_manager.app.set_theme"), \
             patch("huawei_manager.app.apply_theme"):
            AppCore._toggle_theme(app)
        app._set_status.assert_called_once_with("Conectado", "#00e5ff")
        app._set_conn_btn.assert_called_once_with(
            text="  DESCONECTAR  ", disabled=False)

    def test_toggle_restores_active_page(self):
        app = _make_connected_app()
        with patch("huawei_manager.app.set_theme"), \
             patch("huawei_manager.app.apply_theme"):
            AppCore._toggle_theme(app)
        app._show_page.assert_called_once_with("cmd")
        app._nav_buttons["cmd"]._activate.assert_called_once()
        assert app._active_btn == app._nav_buttons["cmd"]

    def test_feedback_shown_during_rebuild(self):
        app = _make_connected_app()
        with patch("huawei_manager.app.set_theme"), \
             patch("huawei_manager.app.apply_theme"):
            AppCore._toggle_theme(app)
        app.status_lbl.setText.assert_any_call("Reconstruindo tema…")