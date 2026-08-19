"""Testes para Editor de Comandos - Enter executa comando (B2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from huawei_manager.pages.cmd import _CmdReturnFilter


class TestEditorEnter:
    """Enter no editor deve executar comando; Shift+Enter insere newline."""

    @pytest.fixture(autouse=True)
    def _app(self):
        app = QApplication.instance() or QApplication([])
        yield app

    def test_shortcut_override_accepts_return(self):
        """ShortcutOverride para Return deve ser aceito (previne shortcut global)."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()

        # Simula evento ShortcutOverride com Return
        event = QEvent(QEvent.Type.ShortcutOverride)
        # Precisa definir key() e modifiers() no evento - usar QKeyEvent seria melhor
        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is True
        assert event.isAccepted()

    def test_shortcut_override_accepts_enter(self):
        """ShortcutOverride para Enter (numpad) deve ser aceito."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()

        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is True
        assert event.isAccepted()

    def test_shortcut_override_rejects_other_keys(self):
        """ShortcutOverride para outras teclas não deve ser interceptado."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()

        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is False  # Deve chamar super()

    def test_enter_keypress_executes_command(self):
        """KeyPress Enter (sem Shift) deve executar comando via app._run."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()
        editor.setPlainText("display version")

        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is True
        app_mock._run.assert_called_once()

    def test_shift_enter_inserts_newline(self):
        """Shift+Enter deve inserir newline no editor."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()
        editor.setPlainText("display version")
        # Move cursor para o final
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is True
        assert editor.toPlainText() == "display version\n"
        app_mock._run.assert_not_called()

    def test_other_keys_pass_through(self):
        """Outras teclas devem passar normalmente (chamar super)."""
        app_mock = MagicMock()
        filter_obj = _CmdReturnFilter(app_mock)
        editor = QPlainTextEdit()

        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)

        result = filter_obj.eventFilter(editor, event)

        assert result is False  # super() retorna False para eventos não tratados


if __name__ == "__main__":
    pytest.main([__file__, "-v"])