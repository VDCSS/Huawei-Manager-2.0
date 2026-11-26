"""Faixa de conexão dentro da aba Topologia (Ciclo 2)."""
from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QPushButton, QWidget


def _boot():
    import huawei_manager._config as cfg

    if cfg._secrets is None or cfg.audit is None:
        cfg._INITIALIZED = False
        cfg.init()
    from huawei_manager._app import get_app

    qapp = get_app()
    from huawei_manager.app import HuaweiRouterApp

    return qapp, HuaweiRouterApp()


class TestConnectionBar:
    def test_connection_widgets_live_in_topology_page(self):
        qapp, window = _boot()
        try:
            window._show_page("topology")
            qapp.processEvents()
            assert window.conn_btn.objectName() == "topologyConnBtn"
            topbar = window.findChild(QWidget, "topbar")
            assert topbar is not None
            assert topbar.findChild(QPushButton, "connBtn") is None
            page = window.pages["topology"]
            assert window.conn_btn in page.findChildren(QPushButton)
        finally:
            window.close()
            qapp.processEvents()

    def test_set_conn_btn_updates_single_toggle(self):
        qapp, window = _boot()
        try:
            window._show_page("topology")
            qapp.processEvents()
            window._set_conn_btn("  DESCONECTAR  ")
            window._poll_queue()
            qapp.processEvents()
            assert window.conn_btn.text() == "  DESCONECTAR  "
            assert window.conn_btn.isEnabled()
            window._set_conn_btn("  CONECTANDO…  ", disabled=True)
            window._poll_queue()
            qapp.processEvents()
            assert window.conn_btn.text() == "  CONECTANDO…  "
            assert not window.conn_btn.isEnabled()
        finally:
            window.close()
            qapp.processEvents()

    def test_set_status_updates_topology_label(self):
        qapp, window = _boot()
        try:
            window._show_page("topology")
            qapp.processEvents()
            window._set_status("Conectado", "#00e5ff")
            window._poll_queue()
            qapp.processEvents()
            assert window.status_lbl.text() == "Conectado"
            assert "#00e5ff" in window.status_dot.styleSheet()
        finally:
            window.close()
            qapp.processEvents()

    def test_topology_button_click_uses_toggle_connect(self):
        qapp, window = _boot()
        try:
            window._show_page("topology")
            qapp.processEvents()
            with patch.object(window, "_toggle_connect") as toggle:
                window.conn_btn.click()
                toggle.assert_called_once_with()
        finally:
            window.close()
            qapp.processEvents()
