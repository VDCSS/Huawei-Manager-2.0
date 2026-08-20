"""Testes de caracterização — AuthMixin (handlers/auth.py).

Testa _require_access (já puro) e caracterização de _show_auth_dialog
com mocks.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QMessageBox

from huawei_manager.handlers.auth import AuthMixin


def _make_mixin(**attrs) -> AuthMixin:
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


class TestRequireAccess:
    """_require_access verifica nivel de acesso."""

    def test_admin_requires_admin(self):
        mixin = _make_mixin(_access_level="admin")
        assert mixin._require_access("admin") is True

    def test_user_requires_admin_returns_false(self):
        mixin = _make_mixin(_access_level="user")
        assert mixin._require_access("admin") is False

    def test_tecnico_requires_user_returns_true(self):
        mixin = _make_mixin(_access_level="tecnico")
        assert mixin._require_access("user") is True

    def test_admin_requires_tecnico_returns_true(self):
        mixin = _make_mixin(_access_level="admin")
        assert mixin._require_access("tecnico") is True

    def test_tecnico_requires_tecnico_returns_true(self):
        mixin = _make_mixin(_access_level="tecnico")
        assert mixin._require_access("tecnico") is True

    def test_user_requires_user_returns_true(self):
        mixin = _make_mixin(_access_level="user")
        assert mixin._require_access("user") is True

    def test_invalid_level_returns_false(self):
        mixin = _make_mixin(_access_level="unknown")
        assert mixin._require_access("admin") is False

    def test_default_level_is_user(self):
        mixin = _make_mixin()
        assert mixin._require_access("admin") is False


class TestShowAuthDialog:
    """_show_auth_dialog comportamento de caracterização."""

    def test_logout_when_not_user(self):
        mixin = _make_mixin(_access_level="admin")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch("huawei_manager.handlers.auth.QMessageBox.question",
                  return_value=QMessageBox.StandardButton.Yes),
        ):
            mixin._show_auth_dialog()
        assert mixin._access_level == "user"
        mixin._session_tracker.set_role.assert_called_once()

    def test_logout_cancelled_keeps_session(self):
        mixin = _make_mixin(_access_level="admin")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch("huawei_manager.handlers.auth.QMessageBox.question",
                  return_value=QMessageBox.StandardButton.No),
        ):
            mixin._show_auth_dialog()
        assert mixin._access_level == "admin"
        mixin._session_tracker.set_role.assert_not_called()

    def test_blocks_when_overlay_visible(self):
        overlay = MagicMock()
        overlay.isVisible.return_value = True
        mixin = _make_mixin(_auth_overlay=overlay)
        mixin._show_auth_dialog()
        overlay.show.assert_not_called()

    @patch("huawei_manager.handlers.auth.ADMIN_PASSWORD", "")
    @patch("huawei_manager.handlers.auth.TECNICO_PASSWORD", "secret")
    @patch("huawei_manager.handlers.auth.QMessageBox")
    def test_warns_when_passwords_not_set(self, mock_msgbox, monkeypatch):
        mixin = _make_mixin()
        mixin._show_auth_dialog()
        mock_msgbox.warning.assert_called_once()

    def test_blocks_when_locked(self):
        import time
        mixin = _make_mixin(_admin_locked_until=time.time() + 300)
        with patch("huawei_manager.handlers.auth.QMessageBox") as mock_msgbox:
            mixin._show_auth_dialog()
        mock_msgbox.warning.assert_called_once()
