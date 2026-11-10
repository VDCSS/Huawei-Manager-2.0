"""Testes de caracterização — formato de backup honesto + logout confirmado (B8+B11).

Verifica que a página Backup mostra QLabel fixo (sem combo mentiroso) e que
o logout exige confirmação explícita (QMessageBox.question).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMessageBox, QWidget

import huawei_manager.constants as C
from huawei_manager.app_shortcuts import ShortcutsMixin
from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.tabs.backup import BackupTab


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_tab() -> tuple[BackupTab, MagicMock, QWidget]:
    """BackupTab com ctx fake (build não usa ctx; run é MagicMock).

    A página é devolvida para manter a referência Python viva — QWidget
    sem pai seria deletado no GC e levaria os filhos junto ( RuntimeError
    de "Internal C++ object already deleted" ).
    """
    tab = BackupTab()
    ctx = MagicMock()
    page = tab.build(ctx)
    return tab, ctx, page


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
        _current_page=None,
        content=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestBackupFormatLabel:
    def test_backup_page_has_label_not_combo(self):
        tab, _ctx, page = _make_tab()

        assert isinstance(tab.state.fmt_lbl, QLabel)
        assert tab.state.fmt_lbl.text() == f"Formato: {C.BACKUP_FMT_TEXT}"
        assert page.findChildren(QComboBox) == []

    def test_backup_button_uses_constant_format(self):
        tab, ctx, page = _make_tab()
        # O botão Fazer Backup despacha run_backup(BACKUP_FMT_TEXT) → ctx.run
        btns = [
            b for b in page.findChildren(object)
            if hasattr(b, "text") and "Fazer Backup" in getattr(b, "text")()
        ]
        assert len(btns) == 1
        btns[0].click()
        ctx.run.assert_called_once()
        # executa a lambda p/ provar que despacha do_backup c/ a constante
        do_backup = MagicMock()
        tab._h().do_backup = do_backup
        ctx.run.call_args.args[0]()
        do_backup.assert_called_once_with(C.BACKUP_FMT_TEXT)


class TestBackupEnterShortcut:
    def test_on_enter_backup_page_uses_constant(self):
        mixin = ShortcutsMixin()
        mixin._auth_overlay = None
        mixin._current_page = "backup"
        mixin._do_backup = MagicMock()
        mixin.focusWidget = MagicMock(return_value=None)  # Mock focusWidget

        mixin._on_enter()
        # O shell chama a fachada direto (sem _run externo — a aba envolve
        # ctx.run; ver F2-config, que corrigiu o double-run).
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
