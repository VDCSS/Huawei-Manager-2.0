"""Testes de caracterização — formato de backup honesto + logout confirmado (B8+B11).

Verifica que a página Backup mostra QLabel fixo (sem combo mentiroso) e que
o logout exige confirmação explícita (QMessageBox.question).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMessageBox, QStackedWidget

import huawei_manager.constants as C
from huawei_manager.app_shortcuts import ShortcutsMixin
from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.pages.builder import PageBuilder


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_builder() -> PageBuilder:
    builder = PageBuilder()
    builder._page_container = QStackedWidget()
    builder._access_level = "user"
    builder._target_device = None
    builder._run = MagicMock()
    builder._do_backup = MagicMock()
    return builder


def _make_auth_mixin(**attrs) -> AuthMixin:
    mixin = AuthMixin()
    defaults = dict(
        _access_level="user",
        _admin_locked_until=0.0,
        _admin_attempts=0,
        _auth_overlay=None,
        _session_tracker=MagicMock(),
        _mock_mode=False,
        _watcher=MagicMock(),
        _sb=MagicMock(),
        _rebuild_page=MagicMock(),
        content=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestBackupFormatLabel:
    def test_backup_page_has_label_not_combo(self):
        builder = _make_builder()
        builder._build_backup_page()
        page = builder._page_container.widget(0)

        assert isinstance(builder._backup_fmt_lbl, QLabel)
        assert builder._backup_fmt_lbl.text() == f"Formato: {C.BACKUP_FMT_TEXT}"
        assert page.findChildren(QComboBox) == []

    def test_backup_button_uses_constant_format(self):
        builder = _make_builder()
        builder._build_backup_page()
        # O botão Fazer Backup dispara self._run(lambda: _do_backup(BACKUP_FMT_TEXT))
        btns = [
            b for b in builder._page_container.widget(0).findChildren(object)
            if hasattr(b, "text") and "Fazer Backup" in getattr(b, "text")()
        ]
        assert len(btns) == 1
        btns[0].click()
        builder._run.assert_called_once()
        builder._run.call_args.args[0]()
        builder._do_backup.assert_called_once_with(C.BACKUP_FMT_TEXT)


class TestBackupEnterShortcut:
    def test_on_enter_backup_page_uses_constant(self):
        mixin = ShortcutsMixin()
        mixin._auth_overlay = None
        mixin._current_page = "backup"
        mixin._run = MagicMock()
        mixin._do_backup = MagicMock()
        mixin.focusWidget = MagicMock(return_value=None)  # Mock focusWidget

        mixin._on_enter()
        mixin._run.assert_called_once()
        mixin._run.call_args.args[0]()
        mixin._do_backup.assert_called_once_with(C.BACKUP_FMT_TEXT)


class TestLogoutConfirmation:
    def test_logout_asks_confirmation(self):
        mixin = _make_auth_mixin(_access_level="admin")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch("huawei_manager.handlers.auth.QMessageBox.question",
                  return_value=QMessageBox.StandardButton.Yes) as mock_q,
        ):
            mixin._show_auth_dialog()
        mock_q.assert_called_once()
        assert mixin._access_level == "user"

    def test_logout_cancelled_keeps_session(self):
        mixin = _make_auth_mixin(_access_level="admin")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch("huawei_manager.handlers.auth.QMessageBox.question",
                  return_value=QMessageBox.StandardButton.No),
        ):
            mixin._show_auth_dialog()
        assert mixin._access_level == "admin"
        mixin._session_tracker.set_role.assert_not_called()
        mixin._watcher.stop.assert_not_called()

    def test_logout_confirmed_logs_out(self):
        mixin = _make_auth_mixin(_access_level="admin")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch("huawei_manager.handlers.auth.QMessageBox.question",
                  return_value=QMessageBox.StandardButton.Yes),
        ):
            mixin._show_auth_dialog()
        assert mixin._access_level == "user"
        mixin._session_tracker.set_role.assert_called_once()
        mixin._watcher.stop.assert_called_once()
        mixin._rebuild_page.assert_called_once_with("topology")