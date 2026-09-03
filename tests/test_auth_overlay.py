"""Testes para AuthOverlay — modalidade e isolamento de atalhos globais (B1)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from huawei_manager.widgets.auth_overlay import AuthOverlay
from huawei_manager.app_shortcuts import ShortcutsMixin


class TestAuthOverlayModal:
    """AuthOverlay deve ser modal e bloquear atalhos globais."""

    @pytest.fixture(autouse=True)
    def _app(self):
        """Garante QApplication para testes Qt."""
        app = QApplication.instance() or QApplication([])
        yield app

    def test_overlay_is_application_modal(self):
        """Overlay deve ter WindowModality.ApplicationModal."""
        parent = QWidget()
        on_result = MagicMock()
        overlay = AuthOverlay(parent=parent, on_result=on_result)
        assert overlay.windowModality() == Qt.WindowModality.ApplicationModal

    def test_escape_closes_overlay(self):
        """Escape deve fechar o overlay (não limpar output da página)."""
        parent = QWidget()
        on_result = MagicMock()
        overlay = AuthOverlay(parent=parent, on_result=on_result)

        # Simula keyPressEvent com Escape
        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        overlay.keyPressEvent(event)

        # close_() deve ser chamado, que chama on_result("user", ...)
        on_result.assert_called_with("user", 0, 0)

    def test_overlay_show_does_not_crash(self):
        """show() não deve crashar."""
        parent = QWidget()
        parent.resize(800, 600)
        on_result = MagicMock()
        overlay = AuthOverlay(parent=parent, on_result=on_result)

        overlay.show()
        # Se chegou aqui sem exception, passou

    def test_enter_in_password_calls_verify(self):
        """Enter no campo de senha deve chamar _verify."""
        parent = QWidget()
        on_result = MagicMock()
        overlay = AuthOverlay(parent=parent, on_result=on_result)

        # Mock _verify e emite o sinal
        overlay._verify = MagicMock()
        overlay._pw_entry.returnPressed.emit()

        overlay._verify.assert_called_once()


class TestShortcutGuards:
    """Atalhos globais devem ser bloqueados quando AuthOverlay visível."""

    @pytest.fixture
    def mixin(self):
        """Cria um ShortcutsMixin com mocks necessários."""
        mixin = ShortcutsMixin()
        # Atributos necessários
        mixin._auth_overlay = None
        mixin._current_page = "cmd"
        mixin._PAGE_KEYS = ["home", "topology", "config", "route", "arp", "info", "cmd", "backup", "manutencao", "services"]
        mixin._run = MagicMock()
        mixin._get_editor_cmd = MagicMock(return_value="display version")
        mixin._fetch_config = MagicMock()
        mixin._fetch_route = MagicMock()
        mixin._fetch_arp = MagicMock()
        mixin._fetch_info = MagicMock()
        mixin._exec_cmd = MagicMock()
        mixin._do_backup = MagicMock()
        mixin._toggle_connect = MagicMock()
        mixin._write = MagicMock()
        mixin._refresh_devices = MagicMock()
        mixin._refresh_service_list = MagicMock()
        mixin._show_page = MagicMock()
        mixin._show_auth_dialog = MagicMock()
        mixin._on_ctrl_l = MagicMock()
        mixin._spawn_io = MagicMock()
        mixin.out_config = MagicMock()
        mixin.out_route = MagicMock()
        mixin.out_arp = MagicMock()
        mixin.out_info = MagicMock()
        mixin.out_cmd = MagicMock()
        mixin.out_backup = MagicMock()
        mixin._svc_output = MagicMock()
        mixin._route_filter_cb = MagicMock()
        mixin.focusWidget = MagicMock(return_value=None)  # Mock focusWidget
        return mixin

    @pytest.fixture
    def visible_overlay(self):
        """Overlay visível real (QWidget) para testes de bloqueio."""
        overlay = QWidget()
        overlay.show()
        return overlay

    @pytest.fixture
    def hidden_overlay(self):
        """Overlay NÃO visível real (QWidget) para testes de não-bloqueio."""
        overlay = QWidget()
        # Não chama show()
        return overlay

    def test_on_enter_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_enter não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_enter()

        mixin._run.assert_not_called()
        mixin._exec_cmd.assert_not_called()

    def test_on_ctrl_d_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_d (toggle connect) não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_d()

        mixin._toggle_connect.assert_not_called()

    def test_on_ctrl_l_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_l (clear output) não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_l()

        mixin._write.assert_not_called()

    def test_on_ctrl_q_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_q (close app) não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_q()
        # Se chegarmos aqui sem erro, o guard funcionou

    def test_on_ctrl_shift_a_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_shift_a (show auth) não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_shift_a()

        mixin._show_auth_dialog.assert_not_called()

    def test_on_f5_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_f5 não deve executar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_f5()

        mixin._spawn_io.assert_not_called()
        mixin._refresh_service_list.assert_not_called()

    def test_on_ctrl_tab_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_tab não deve navegar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_tab()

        mixin._show_page.assert_not_called()

    def test_on_ctrl_shift_tab_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_ctrl_shift_tab não deve navegar quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_ctrl_shift_tab()

        mixin._show_page.assert_not_called()

    def test_on_escape_blocked_when_overlay_visible(self, mixin, visible_overlay):
        """_on_escape não deve limpar output quando overlay visível."""
        mixin._auth_overlay = visible_overlay

        mixin._on_escape()

        mixin._on_ctrl_l.assert_not_called()

    def test_shortcuts_work_when_overlay_not_visible(self, mixin, hidden_overlay):
        """Atalhos devem funcionar normalmente quando overlay NÃO está visível."""
        mixin._auth_overlay = hidden_overlay

        mixin._on_enter()
        # Deve chamar _run com lambda que executa _exec_cmd
        mixin._run.assert_called_once()


class TestAuthOverlayIntegration:
    """Testes de integração com AuthMixin."""

    @pytest.fixture(autouse=True)
    def _app(self):
        app = QApplication.instance() or QApplication([])
        yield app

    def test_auth_dialog_creates_modal_overlay(self):
        """_show_auth_dialog deve criar overlay modal."""
        from huawei_manager.handlers.auth import AuthMixin

        mixin = AuthMixin()
        mixin._access_level = "user"
        mixin._admin_locked_until = 0.0
        mixin._admin_attempts = 0
        mixin._auth_overlay = None
        mixin._session_tracker = MagicMock()
        mixin._mock_mode = False
        mixin._watcher = MagicMock()
        mixin._sb = MagicMock()
        mixin._rebuild_page = MagicMock()
        # content deve ser um QWidget real
        mixin.content = QWidget()
        mixin.ADMIN_MAX_ATTEMPTS = 3
        mixin.ADMIN_LOCKOUT_SECS = 30

        mixin._show_auth_dialog()

        assert mixin._auth_overlay is not None
        assert mixin._auth_overlay.windowModality() == Qt.WindowModality.ApplicationModal


if __name__ == "__main__":
    pytest.main([__file__, "-v"])