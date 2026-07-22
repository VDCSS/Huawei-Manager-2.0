"""Tests for widgets.py — ActionButton, NeonButton, _css_font."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

from huawei_manager.widgets.helpers import _css_font
from huawei_manager.widgets.neon_button import ActionButton, NeonButton, action_button


class TestCssFont:
    def test_normal_font(self):
        font = ("Inter", 13)
        result = _css_font(font)
        assert "normal" in result
        assert "13px" in result
        assert "Inter" in result

    def test_bold_font(self):
        font = ("Consolas", 14, "bold")
        result = _css_font(font)
        assert "bold" in result

    def test_different_sizes(self):
        font = ("Inter", 10)
        result = _css_font(font)
        assert "10px" in result


class TestActionButton:
    def test_can_instantiate(self, qtbot):
        btn = ActionButton()
        qtbot.addWidget(btn)
        assert isinstance(btn, QPushButton)

    def test_sets_text(self, qtbot):
        btn = ActionButton(text="Executar")
        qtbot.addWidget(btn)
        assert btn.text() == "Executar"

    def test_connects_command(self, qtbot):
        mock = MagicMock()
        btn = ActionButton(text="OK", command=mock)
        qtbot.addWidget(btn)
        btn.click()
        assert mock.called

    def test_no_command_no_crash(self, qtbot):
        btn = ActionButton(text="OK")
        qtbot.addWidget(btn)
        btn.click()  # must not raise

    def test_configure_text(self, qtbot):
        btn = ActionButton(text="Old")
        qtbot.addWidget(btn)
        btn.configure(text="New")
        assert btn.text() == "New"

    def test_configure_disabled(self, qtbot):
        btn = ActionButton(text="Test")
        qtbot.addWidget(btn)
        btn.configure(state="disabled")
        assert not btn.isEnabled()

    def test_configure_enabled(self, qtbot):
        btn = ActionButton(text="Test")
        qtbot.addWidget(btn)
        btn.configure(state="disabled")
        btn.configure(state="normal")
        assert btn.isEnabled()

    def test_configure_new_command(self, qtbot):
        mock1 = MagicMock()
        mock2 = MagicMock()
        btn = ActionButton(text="Test", command=mock1)
        qtbot.addWidget(btn)
        btn.configure(command=mock2)
        btn.click()
        assert mock2.called
        # mock1 should NOT be called — old signal disconnected
        assert not mock1.called

    def test_configure_color(self, qtbot):
        btn = ActionButton(text="Test")
        qtbot.addWidget(btn)
        btn.configure(color="#FF0000")
        assert btn._color == "#FF0000"

    def test_cursor_changes_when_disabled(self, qtbot):
        btn = ActionButton(text="Test")
        qtbot.addWidget(btn)
        btn.configure(state="disabled")
        assert btn.cursor().shape() == Qt.CursorShape.ArrowCursor

    def test_cursor_pointing_when_enabled(self, qtbot):
        btn = ActionButton(text="Test")
        qtbot.addWidget(btn)
        assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestActionButtonFactory:
    def test_returns_action_button(self, qtbot):
        parent = QWidget()
        qtbot.addWidget(parent)
        btn = action_button(parent, "Click")
        assert isinstance(btn, ActionButton)
        assert btn.text() == "Click"
        assert btn.parent() is parent

    def test_with_command_and_color(self, qtbot):
        mock = MagicMock()
        parent = QWidget()
        qtbot.addWidget(parent)
        btn = action_button(parent, "Go", mock, "#00FF00")
        btn.click()
        assert mock.called
        assert btn._color == "#00FF00"


class TestNeonButton:
    def test_can_instantiate(self, qtbot):
        btn = NeonButton()
        qtbot.addWidget(btn)
        assert isinstance(btn, QPushButton)

    def test_sets_text(self, qtbot):
        btn = NeonButton(text="Dashboard")
        qtbot.addWidget(btn)
        assert btn.text() == "Dashboard"

    def test_with_icon(self, qtbot):
        btn = NeonButton(text="Home", icon="🏠")
        qtbot.addWidget(btn)
        assert "🏠" in btn.text()
        assert "Home" in btn.text()

    def test_connects_command(self, qtbot):
        mock = MagicMock()
        btn = NeonButton(text="Test", command=mock)
        qtbot.addWidget(btn)
        btn.click()
        assert mock.called

    def test_activate_changes_style(self, qtbot):
        btn = NeonButton(text="Test")
        qtbot.addWidget(btn)
        btn._activate()
        assert btn._active is True

    def test_deactivate_clears_active(self, qtbot):
        btn = NeonButton(text="Test")
        qtbot.addWidget(btn)
        btn._activate()
        btn._deactivate()
        assert btn._active is False
