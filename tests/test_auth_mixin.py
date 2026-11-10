"""Testes de caracterização — AuthMixin (handlers/auth.py).

Testa _require_access (já puro) e caracterização de _show_auth_dialog
com mocks.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

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
        _current_page=None,
        content=MagicMock(),
        ADMIN_MAX_ATTEMPTS=3,
        ADMIN_LOCKOUT_SECS=300,
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

    @patch("huawei_manager.handlers.auth.AuthOverlay")
    def test_creates_overlay_when_user(self, mock_overlay_cls):
        """Quando access_level=user e nao bloqueado, cria AuthOverlay."""
        mixin = _make_mixin()
        mixin._show_auth_dialog()
        mock_overlay_cls.assert_called_once()

    def test_blocks_when_locked(self):
        import time
        mixin = _make_mixin(_admin_locked_until=time.time() + 300)
        with patch("huawei_manager.handlers.auth.QMessageBox") as mock_msgbox:
            mixin._show_auth_dialog()
        mock_msgbox.warning.assert_called_once()


class TestRebuildForAccessChange:
    """Troca de nível de acesso reconstrói a página ATUAL (não só topology).

    Regressão: login com a aba Manutenção aberta deixava a página presa em
    "Acesso Restrito" (o botão de auth passava a perguntar sair da sessão).
    """

    def test_current_manutencao_rebuilt_then_topology(self):
        mixin = _make_mixin(_current_page="manutencao")
        mixin._rebuild_for_access_change()
        assert mixin._rebuild_page.call_args_list == [
            call("manutencao"),
            call("topology"),
        ]

    def test_current_topology_rebuilt_once(self):
        mixin = _make_mixin(_current_page="topology")
        mixin._rebuild_for_access_change()
        mixin._rebuild_page.assert_called_once_with("topology")

    def test_no_current_page_defaults_to_topology(self):
        mixin = _make_mixin(_current_page=None)
        mixin._rebuild_for_access_change()
        mixin._rebuild_page.assert_called_once_with("topology")

    def test_login_rebuilds_current_page(self):
        """Login com Manutenção ativa reconstrói a própria aba."""
        if QApplication.instance() is None:
            QApplication([])
        mixin = _make_mixin(_current_page="manutencao", content=QWidget())
        mixin._show_auth_dialog()
        overlay = mixin._auth_overlay
        assert overlay is not None

        overlay.on_result("tecnico", 0, 0)

        assert mixin._access_level == "tecnico"
        assert mixin._rebuild_page.call_args_list == [
            call("manutencao"),
            call("topology"),
        ]
        mixin._watcher.start.assert_called_once()

    def test_logout_rebuilds_current_page(self):
        mixin = _make_mixin(_access_level="admin", _current_page="manutencao")
        with (
            patch("huawei_manager.handlers.auth.log"),
            patch(
                "huawei_manager.handlers.auth.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
        ):
            mixin._show_auth_dialog()
        assert mixin._access_level == "user"
        assert mixin._rebuild_page.call_args_list == [
            call("manutencao"),
            call("topology"),
        ]
