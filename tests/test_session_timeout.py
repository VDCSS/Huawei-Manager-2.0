"""Testes de caracterização — timeout de sessão notifica + cor de desconexão (B13+B14).

Verifica que _check_session_timeout sinaliza "Sessão expirada" em amber e
que a desconexão (header + dashboard) usa NEON_RED, nunca NEON_PURP.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import huawei_manager.constants as C
from huawei_manager.app_state import AppStateMixin
from huawei_manager.handlers.auth import Role
from huawei_manager.handlers.ssh import SshMixin


def _make_app_mixin(**attrs) -> AppStateMixin:
    mixin = AppStateMixin()
    defaults = dict(
        _access_level="admin",
        _session_tracker=MagicMock(),
        _sb=MagicMock(),
        _mock_mode=False,
        _watcher=MagicMock(),
        _rebuild_page=MagicMock(),
        _set_status=MagicMock(),
        status_dot=MagicMock(),
        status_lbl=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _make_ssh_mixin(**attrs) -> SshMixin:
    mixin = SshMixin()
    defaults = dict(
        _sb=MagicMock(),
        _set_status=MagicMock(),
        _set_conn_btn=MagicMock(),
        _get_selected_device=MagicMock(return_value=None),
        _event_queue=MagicMock(),
        _target_device=None,
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestSessionTimeoutNotifies:
    def test_timeout_sets_amber_status(self):
        mixin = _make_app_mixin(_access_level="admin")
        mixin._session_tracker.current_role = Role.USER

        mixin._check_session_timeout()

        assert mixin._access_level == "user"
        mixin._set_status.assert_called_once_with(
            "Sess\u00e3o expirada \u2014 acesso user", C.NEON_AMBER)

    def test_timeout_resets_ui_state(self):
        mixin = _make_app_mixin(_access_level="tecnico")
        mixin._session_tracker.current_role = Role.USER

        mixin._check_session_timeout()

        mixin._sb.set_access_role.assert_called_once_with("user")
        mixin._watcher.stop.assert_called_once()
        mixin._rebuild_page.assert_called_once_with("topology")
        assert mixin._mock_mode is False

    def test_no_timeout_keeps_session(self):
        mixin = _make_app_mixin(_access_level="admin")
        mixin._session_tracker.current_role = Role.ADMIN

        mixin._check_session_timeout()

        assert mixin._access_level == "admin"
        mixin._set_status.assert_not_called()

    def test_user_level_returns_early(self):
        mixin = _make_app_mixin(_access_level="user")

        mixin._check_session_timeout()

        mixin._set_status.assert_not_called()


class TestDisconnectColor:
    def test_disconnect_uses_neon_red(self):
        mixin = _make_ssh_mixin()
        mixin._sb.is_alive.return_value = True

        mixin._toggle_connect()

        mixin._set_status.assert_called_once_with("Desconectado", C.NEON_RED)

    def test_header_initial_dot_is_red(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src"
               / "huawei_manager" / "app.py").read_text(encoding="utf-8")
        assert "status_dot.setStyleSheet" in src
        dot_line = next(ln for ln in src.splitlines()
                        if "status_dot.setStyleSheet" in ln)
        assert "NEON_RED" in dot_line
        assert "NEON_PURP" not in dot_line

    def test_dashboard_conn_status_uses_red(self):
        from PySide6.QtWidgets import QApplication, QStackedWidget

        QApplication.instance() or QApplication([])
        from huawei_manager.pages.builder import PageBuilder

        builder = PageBuilder()
        builder._page_container = QStackedWidget()
        builder._access_level = "user"
        builder._target_device = None
        builder._run = MagicMock()
        builder._get_editor_cmd = MagicMock(return_value="display version")
        builder._exec_cmd = MagicMock()
        builder._exec_config = MagicMock()
        builder._build_home_page()

        assert builder._dash_conn_status.text() == "Desconectado"
        assert C.NEON_RED in builder._dash_conn_status.styleSheet()
        assert "NEON_PURP" not in builder._dash_conn_status.styleSheet()
