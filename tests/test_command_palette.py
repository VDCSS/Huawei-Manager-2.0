"""Testes para Command Palette (Ctrl+K) — filtro, navegação teclado, execução."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem, QWidget

from huawei_manager.widgets.command_palette import Command, CommandPalette, create_default_commands


@pytest.fixture
def _palette_parent(qapp):
    parent = QWidget()
    parent.resize(800, 600)
    parent.show()
    yield parent
    parent.hide()
    parent.deleteLater()


def _make_palette(commands: list[Command] | None = None, parent: QWidget | None = None) -> CommandPalette:
    if parent is None:
        parent = QWidget()
        parent.resize(800, 600)
        parent.show()
    cmds = commands or [
        Command("test:1", "Teste Um", "Descrição 1", "Cat", "Ctrl+1", MagicMock()),
        Command("test:2", "Teste Dois", "Descrição 2", "Cat", "Ctrl+2", MagicMock()),
        Command("test:3", "Outro", "Outra descrição", "Outra", None, MagicMock()),
    ]
    palette = CommandPalette(parent, cmds)
    return palette


class TestCommandPaletteFiltering:
    def test_filter_by_label(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("teste")
        assert len(palette._filtered_commands) == 2
        assert palette._filtered_commands[0].id == "test:1"
        assert palette._filtered_commands[1].id == "test:2"

    def test_filter_by_description(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("descrição")
        assert len(palette._filtered_commands) == 3

    def test_filter_by_category(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("outra")
        assert len(palette._filtered_commands) == 1
        assert palette._filtered_commands[0].id == "test:3"

    def test_filter_by_shortcut(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("ctrl+1")
        assert len(palette._filtered_commands) == 1
        assert palette._filtered_commands[0].id == "test:1"

    def test_filter_case_insensitive(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("TESTE")
        assert len(palette._filtered_commands) == 2

    def test_empty_filter_shows_all_enabled(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._search.setText("")
        assert len(palette._filtered_commands) == 3

    def test_disabled_commands_excluded(self, _palette_parent):
        cmds = [
            Command("enabled", "Habilitado", "desc", "Cat", None, MagicMock(), enabled=True),
            Command("disabled", "Desabilitado", "desc", "Cat", None, MagicMock(), enabled=False),
        ]
        palette = _make_palette(cmds, parent=_palette_parent)
        palette.show()
        palette._search.setText("")
        assert len(palette._filtered_commands) == 1
        assert palette._filtered_commands[0].id == "enabled"


class TestCommandPaletteKeyboardNavigation:
    def _make_key_event(self, key):
        class KeyEvent:
            def key(self): return key
        return KeyEvent()

    def test_up_down_navigation(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        assert palette._list.currentRow() == 0
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Down))
        assert palette._list.currentRow() == 1
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Down))
        assert palette._list.currentRow() == 2
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Up))
        assert palette._list.currentRow() == 1

    def test_enter_executes_action(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        mock_action = palette._filtered_commands[1].action
        palette._list.setCurrentRow(1)
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Return))
        mock_action.assert_called_once()
        assert not palette.isVisible()

    def test_escape_closes_palette(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Escape))
        assert not palette.isVisible()

    def test_escape_from_list_returns_to_search(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        palette._list.setFocus()
        QApplication.processEvents()
        palette.keyPressEvent(self._make_key_event(Qt.Key.Key_Escape))
        assert palette._search.hasFocus()


class TestCommandPaletteExecution:
    def test_item_activated_executes_action(self, _palette_parent):
        palette = _make_palette(parent=_palette_parent)
        palette.show()
        mock_action = palette._filtered_commands[0].action
        item = palette._list.item(0)
        assert item is not None
        palette._list.setCurrentRow(0)
        palette._on_item_activated(item)
        mock_action.assert_called_once()
        assert not palette.isVisible()


class TestCreateDefaultCommands:
    def test_creates_navigation_commands(self):
        mock_app = MagicMock()
        mock_app._show_page = MagicMock()
        mock_app._secrets = {"host": "192.168.1.1"}
        cmds = create_default_commands(mock_app)
        nav_cmds = [c for c in cmds if c.category == "Navegação"]
        assert len(nav_cmds) == 10
        assert any(c.id == "nav:home" for c in nav_cmds)
        assert any(c.id == "nav:services" for c in nav_cmds)

    def test_creates_toggle_theme_command(self):
        mock_app = MagicMock()
        mock_app._show_page = MagicMock()
        mock_app._secrets = {"host": "192.168.1.1"}
        mock_app._toggle_theme = MagicMock()
        cmds = create_default_commands(mock_app)
        theme_cmd = next(c for c in cmds if c.id == "toggle_theme")
        assert theme_cmd.shortcut == "Ctrl+T"
        theme_cmd.action()
        mock_app._toggle_theme.assert_called_once()

    def test_creates_copy_ip_command_enabled_when_host_exists(self):
        mock_app = MagicMock()
        mock_app._show_page = MagicMock()
        mock_app._secrets = {"host": "192.168.1.1"}
        mock_app._toggle_theme = MagicMock()
        cmds = create_default_commands(mock_app)
        copy_cmd = next(c for c in cmds if c.id == "copy_ip")
        assert copy_cmd.enabled is True

    def test_creates_copy_ip_command_disabled_when_no_host(self):
        mock_app = MagicMock()
        mock_app._show_page = MagicMock()
        mock_app._secrets = {}
        mock_app._toggle_theme = MagicMock()
        cmds = create_default_commands(mock_app)
        copy_cmd = next(c for c in cmds if c.id == "copy_ip")
        assert copy_cmd.enabled is False