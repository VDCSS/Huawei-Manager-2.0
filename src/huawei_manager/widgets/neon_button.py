from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

import huawei_manager.constants as _C
from huawei_manager.widgets.helpers import _css_font


class ActionButton(QPushButton):
    def __init__(
        self,
        parent: QWidget | None = None,
        text: str = "",
        command: Callable[[], object] | None = None,
        color: str = _C.NEON_CYAN,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._command = command
        self._color = color
        self._disabled = False

        self.setText(text)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if command is not None:
            self.clicked.connect(command)

        self._apply_style()

    def _apply_style(self) -> None:
        if self._disabled:
            bg = _C.BG_INPUT
            fg = "#555566"
            border = _C.BORDER_NRM
        else:
            bg = _C.BG_INPUT
            fg = self._color
            border = self._color

        self.setStyleSheet(f"""
            ActionButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 16px;
                font: {_css_font(_C.FONT_UI_MEDIUM_B)};
            }}
            ActionButton:hover {{
                background-color: {self._color};
                color: {_C.BG_BASE};
                border: 1px solid {self._color};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor if not self._disabled else Qt.CursorShape.ArrowCursor)

    def configure(
        self,
        text: str | None = None,
        state: str | None = None,
        command: Callable[[], object] | None = None,
        color: str | None = None,
    ) -> None:
        if text is not None:
            self._text = text
            self.setText(text)
        if state is not None:
            self._disabled = state == "disabled"
            self.setEnabled(not self._disabled)
        if command is not None:
            self._command = command
            try:
                self.clicked.disconnect()
            except RuntimeError:
                pass
            self.clicked.connect(command)
        if color is not None:
            self._color = color
        self._apply_style()


def action_button(
    parent: QWidget,
    text: str = "",
    command: Callable[..., object] | None = None,
    color: str = _C.NEON_CYAN,
) -> ActionButton:
    btn = ActionButton(parent, text, command, color)
    return btn


class NeonButton(QPushButton):
    def __init__(
        self,
        parent: QWidget | None = None,
        text: str = "",
        command: Callable[..., object] | None = None,
        color: str = _C.NEON_CYAN,
        icon: str = "",
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._icon_text = icon
        self._label_text = text
        self._active = False

        self.setMinimumHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if command is not None:
            self.clicked.connect(command)
        self._update_display()

    def _update_display(self) -> None:
        if self._icon_text:
            self.setText(f"{self._icon_text}  {self._label_text}")
        else:
            self.setText(self._label_text)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            bg = "#1a1a3a"
            fg = self._color
            accent = f"border-left: 4px solid {self._color};"
        else:
            bg = _C.BG_SIDEBAR
            fg = _C.FG_MAIN
            accent = ""

        self.setStyleSheet(f"""
            NeonButton {{
                background-color: {bg};
                color: {fg};
                border: none;
                {accent}
                border-radius: 0px;
                padding: 0px 0px 0px 12px;
                text-align: left;
                font: {_css_font(_C.FONT_UI_MEDIUM)};
            }}
            NeonButton:hover {{
                background-color: #1a1a3e;
                color: {self._color if not self._active else fg};
            }}
        """)

    def _activate(self) -> None:
        self._active = True
        self._apply_style()

    def _deactivate(self) -> None:
        self._active = False
        self._apply_style()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)


def neon_button(
    parent: QWidget,
    text: str = "",
    command: Callable[..., object] | None = None,
    color: str = _C.NEON_CYAN,
    icon: str = "",
) -> NeonButton:
    return NeonButton(parent, text, command, color, icon)
