"""Testes de caracterização — _CmdReturnFilter (pages/cmd.py).

Testa eventFilter com QKeyEvent reais do PySide6.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from huawei_manager.pages.cmd import _CmdReturnFilter


def _make_key_event(key: Qt.Key, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def _make_text_cursor_widget():
    """Widget mock com textCursor() que retorna cursor MagicMock."""
    obj = MagicMock()
    cursor = MagicMock()
    obj.textCursor.return_value = cursor
    return obj, cursor


class TestCmdReturnFilter:
    def test_enter_runs_command(self):
        app = MagicMock()
        app._get_editor_cmd.return_value = "display version"
        filt = _CmdReturnFilter(app)
        obj = MagicMock()

        event = _make_key_event(Qt.Key.Key_Return)
        result = filt.eventFilter(obj, event)
        assert result is True
        app._run.assert_called_once()

    def test_enter_key_also_triggers(self):
        app = MagicMock()
        filt = _CmdReturnFilter(app)
        obj = MagicMock()

        event = _make_key_event(Qt.Key.Key_Enter)
        result = filt.eventFilter(obj, event)
        assert result is True
        app._run.assert_called_once()

    def test_shift_enter_inserts_newline(self):
        app = MagicMock()
        filt = _CmdReturnFilter(app)
        obj, cursor = _make_text_cursor_widget()

        event = _make_key_event(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        result = filt.eventFilter(obj, event)
        assert result is True
        cursor.insertText.assert_called_once_with("\n")

    def test_non_enter_returns_false(self):
        from PySide6.QtCore import QObject
        app = MagicMock()
        filt = _CmdReturnFilter(app)
        obj = QObject()

        event = _make_key_event(Qt.Key.Key_A)
        result = filt.eventFilter(obj, event)
        assert result is False
