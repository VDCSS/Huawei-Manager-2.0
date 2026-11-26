"""Ciclo 4 — perfil/login no topbar e na sidebar (TDD)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QWidget

from huawei_manager.app_shortcuts import ShortcutsMixin


def _boot():
    import huawei_manager._config as cfg

    if cfg._secrets is None or cfg.audit is None:
        cfg._INITIALIZED = False
        cfg.init()
    from huawei_manager._app import get_app

    qapp = get_app()
    return qapp


class TestProfileWidgets:
    def test_topbar_avatar_is_clickable_profile_button(self):
        from huawei_manager.app import HuaweiRouterApp

        qapp = _boot()
        window = HuaweiRouterApp()
        try:
            avatar = window.findChild(QToolButton, "avatar")
            assert avatar is not None
            with patch.object(window, "_show_auth_dialog") as show:
                avatar.click()
            show.assert_called_once_with()
        finally:
            window.close()
            qapp.processEvents()

    def test_sidebar_card_click_opens_auth(self, qtbot):
        from huawei_manager.app import HuaweiRouterApp

        qapp = _boot()
        window = HuaweiRouterApp()
        try:
            card = window.findChild(QWidget, "userCard")
            assert card is not None
            with patch.object(window, "_show_auth_dialog") as show:
                qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
            show.assert_called_once_with()
        finally:
            window.close()
            qapp.processEvents()

    def test_sidebar_switch_button_opens_auth(self):
        from huawei_manager.app import HuaweiRouterApp

        qapp = _boot()
        window = HuaweiRouterApp()
        try:
            button = window.findChild(QToolButton, "profileSwitchBtn")
            assert button is not None
            with patch.object(window, "_show_auth_dialog") as show:
                button.click()
            show.assert_called_once_with()
        finally:
            window.close()
            qapp.processEvents()

    def test_profile_labels_follow_access_level(self):
        from huawei_manager.app import HuaweiRouterApp

        qapp = _boot()
        window = HuaweiRouterApp()
        try:
            window._access_level = "admin"
            window._update_profile_labels()
            name = window.findChild(QLabel, "profileName")
            role = window.findChild(QLabel, "profileRole")
            assert name is not None and name.text() == "Operador"
            assert role is not None and role.text() == "admin · Sessão ativa"
        finally:
            window.close()
            qapp.processEvents()


class _ShortcutHost(ShortcutsMixin, QObject):
    pass


def test_ctrl_shift_a_opens_auth_dialog():
    QApplication.instance() or QApplication([])
    host = _ShortcutHost()
    host._PAGE_KEYS = ["home"]
    host._show_page = MagicMock()
    host._toggle_command_palette = MagicMock()
    host._show_auth_dialog = MagicMock()
    host._setup_bindings()
    for shortcut in host.findChildren(QShortcut):
        if shortcut.key().toString() == "Ctrl+Shift+A":
            shortcut.activated.emit()
            host._show_auth_dialog.assert_called_once_with()
            return
    raise AssertionError("Ctrl+Shift+A não registrado")
