"""Testes de caracterização — _CmdReturnFilter e CmdTab (tabs/cmd/page.py).

Testa eventFilter com QKeyEvent reais do PySide6 + leitura do editor.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from huawei_manager.tabs.cmd.page import CmdTab, _CmdReturnFilter


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
        tab = MagicMock()
        tab.get_editor_cmd.return_value = "display version"
        filt = _CmdReturnFilter(tab)
        obj = MagicMock()

        event = _make_key_event(Qt.Key.Key_Return)
        result = filt.eventFilter(obj, event)
        assert result is True
        tab.run_cmd_safe.assert_called_once_with("display version")

    def test_enter_key_also_triggers(self):
        tab = MagicMock()
        filt = _CmdReturnFilter(tab)
        obj = MagicMock()

        event = _make_key_event(Qt.Key.Key_Enter)
        result = filt.eventFilter(obj, event)
        assert result is True
        tab.run_cmd_safe.assert_called_once()

    def test_shift_enter_inserts_newline(self):
        tab = MagicMock()
        filt = _CmdReturnFilter(tab)
        obj, cursor = _make_text_cursor_widget()

        event = _make_key_event(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        result = filt.eventFilter(obj, event)
        assert result is True
        cursor.insertText.assert_called_once_with("\n")

    def test_non_enter_returns_false(self):
        from PySide6.QtCore import QObject
        tab = MagicMock()
        filt = _CmdReturnFilter(tab)
        obj = QObject()

        event = _make_key_event(Qt.Key.Key_A)
        result = filt.eventFilter(obj, event)
        assert result is False


class TestGetEditorCmd:
    """CmdTab.get_editor_cmd lê o estado privado (nunca o App)."""

    def test_returns_stripped_text(self):
        tab = CmdTab()
        tab.state.editor = MagicMock()
        tab.state.editor.toPlainText.return_value = "  display version  "
        assert tab.get_editor_cmd() == "display version"

    def test_returns_empty_string_when_blank(self):
        tab = CmdTab()
        tab.state.editor = MagicMock()
        tab.state.editor.toPlainText.return_value = "   "
        assert tab.get_editor_cmd() == ""

    def test_returns_empty_when_not_built(self):
        tab = CmdTab()
        assert tab.get_editor_cmd() == ""
