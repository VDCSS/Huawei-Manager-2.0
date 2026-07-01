"""
Widgets PySide6 — ActionButton, NeonButton, neon_entry, styled_text, output_text
====================================================================================
Componentes de interface reutilizáveis construídos com PySide6 QWidgets.
Substituem os antigos helpers Tkinter (ActionButton, neon_button, etc.)."""

import logging
import time
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as _C

log = logging.getLogger("huawei.widgets")


def _css_font(font_tuple: tuple) -> str:
    family, size, *_ = font_tuple
    weight = "bold" if len(font_tuple) > 2 and font_tuple[2] == "bold" else "normal"
    return f"{weight} {size}px '{family}'"


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


def neon_entry(
    parent: QWidget | None = None,
    textvariable: list | dict | None = None,
    width: int = 30,
    state: str = "normal",
) -> QLineEdit:
    entry = QLineEdit(parent)
    entry.setMinimumWidth(width * 8)
    entry.setMaximumWidth(width * 14)
    entry.setPlaceholderText("")
    entry.setStyleSheet(f"""
        QLineEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.NEON_CYAN};
            border: none;
            border-bottom: 2px solid {_C.NEON_CYAN};
            padding: 4px 6px;
            font: {_css_font(_C.FONT_UI_MEDIUM)};
        }}
        QLineEdit:focus {{
            border-bottom: 2px solid {_C.NEON_CYAN};
        }}
        QLineEdit:disabled {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_DIM};
            border-bottom: 2px solid {_C.BORDER_NRM};
        }}
    """)
    if isinstance(textvariable, list):
        def _on_change(text: str) -> None:
            if textvariable:
                textvariable[0] = text
        entry.textChanged.connect(_on_change)
    elif isinstance(textvariable, dict):
        def _on_change(text: str) -> None:
            if textvariable is not None:
                textvariable["value"] = text
        entry.textChanged.connect(_on_change)

    if state == "disabled":
        entry.setEnabled(False)
    return entry


def styled_text(parent: QWidget | None = None, **kw) -> QTextEdit:
    ed = QTextEdit(parent)
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    ed.setFont(font := ed.font())
    font.setFamily(family)
    font.setPointSize(size)
    ed.setFont(font)
    ed.setStyleSheet(f"""
        QTextEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_CODE};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 4px;
            padding: 4px;
            font: {size}pt '{family}';
        }}
    """)
    ed.setTabStopDistance(20)
    ed.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    for k, v in kw.items():
        if hasattr(ed, k):
            try:
                setattr(ed, k, v)
            except Exception:
                pass
    return ed


def output_text(parent: QWidget | None = None, **kw) -> QTextEdit:
    ed = styled_text(parent, **kw)
    ed.setReadOnly(True)
    family, size = _C.FONT_LARGE[0], _C.FONT_LARGE[1]
    base_style = f"""
        QTextEdit {{
            background-color: {_C.BG_INPUT};
            color: {_C.FG_CODE};
            border: 1px solid {_C.BORDER_NRM};
            border-radius: 4px;
            padding: 4px;
            font: {size}pt '{family}';
        }}
        QTextEdit:read-only {{
            color: #b0b0d0;
        }}
    """
    ed.setStyleSheet(base_style)
    return ed


_ENTRY_STYLE = f"""QLineEdit {{
    background: {_C.BG_INPUT};
    color: {_C.NEON_CYAN};
    border: 1px solid {_C.BORDER_NRM};
    border-radius: 4px;
    padding: 6px 10px;
    font: 13px 'Inter';
}}"""


class AuthOverlay(QWidget):
    def __init__(
        self,
        parent: QWidget,
        on_result: Callable[[str, int, float], None],
        admin_locked_until: float = 0,
        admin_max_attempts: int = 3,
        admin_lockout_secs: int = 30,
        attempts_so_far: int = 0,
    ) -> None:
        super().__init__(parent)
        self.on_result = on_result
        self._max_attempts = admin_max_attempts
        self._lockout_secs = admin_lockout_secs
        self._locked_until = admin_locked_until
        self._attempts = attempts_so_far

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("AuthOverlay { background: rgba(0, 0, 0, 140); }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addStretch()

        self._card = QFrame(self)
        self._card.setFixedWidth(340)
        self._card.setStyleSheet(
            f"QFrame {{ background: {_C.BG_CARD}; border: 1px solid {_C.BORDER_NRM}; border-radius: 8px; }}")

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch()
        self._close_btn = QPushButton("\u2715", self._card)
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_C.FG_DIM}; border: none; font: 14px 'Inter'; }}"
            f"QPushButton:hover {{ color: {_C.NEON_CYAN}; }}")
        self._close_btn.clicked.connect(self.close_)
        header.addWidget(self._close_btn)
        card_layout.addLayout(header)

        title = QLabel("Acesso Restrito", self._card)
        title.setStyleSheet(
            f"color: {_C.NEON_CYAN}; font: bold 18px 'Inter'; background: transparent; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        card_layout.addWidget(QLabel("Usu\u00e1rio:", self._card))
        self._user_entry = QLineEdit(self._card)
        self._user_entry.setStyleSheet(_ENTRY_STYLE)
        card_layout.addWidget(self._user_entry)

        card_layout.addWidget(QLabel("Senha:", self._card))
        self._pw_entry = QLineEdit(self._card)
        self._pw_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_entry.setStyleSheet(_ENTRY_STYLE)
        card_layout.addWidget(self._pw_entry)

        self._error_lbl = QLabel("", self._card)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            "color: #ff4444; background: transparent; border: none; font: 12px 'Inter';")
        self._error_lbl.hide()
        card_layout.addWidget(self._error_lbl)

        card_layout.addSpacing(8)

        self._auth_btn = QPushButton("Autenticar", self._card)
        self._auth_btn.setStyleSheet(
            f"QPushButton {{ background: {_C.BG_CARD}; color: {_C.NEON_CYAN}; "
            f"border: 1px solid {_C.NEON_CYAN}; border-radius: 6px; "
            f"padding: 8px 24px; font: bold 13px 'Inter'; }}"
            f"QPushButton:hover {{ background: {_C.NEON_CYAN}; color: {_C.BG_CARD}; }}")
        self._auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auth_btn.clicked.connect(self._verify)
        card_layout.addWidget(self._auth_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        h_layout.addWidget(self._card)
        h_layout.addStretch()
        layout.addLayout(h_layout)
        layout.addStretch()

        self._pw_entry.returnPressed.connect(self._verify)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close_)

    def show(self) -> None:
        parent = self.parent()
        if isinstance(parent, QWidget):
            self.setGeometry(parent.rect())
        super().show()
        self.raise_()
        self._user_entry.setFocus()

    def resizeEvent(self, event) -> None:
        parent = self.parent()
        if isinstance(parent, QWidget):
            self.setGeometry(parent.rect())
        super().resizeEvent(event)

    def close_(self) -> None:
        locked = self._locked_until if time.time() < self._locked_until else 0
        self.on_result("user", self._attempts, locked)
        self.hide()
        self.deleteLater()

    def _verify(self) -> None:
        if time.time() < self._locked_until:
            self._show_lockout()
            return

        from huawei_manager._config import get_credentials

        user = self._user_entry.text().strip()
        pw = self._pw_entry.text()
        level = "user"

        tec_user, tec_pass = get_credentials("tecnico")
        if user == tec_user and pw == tec_pass:
            level = "tecnico"
        else:
            adm_user, adm_pass = get_credentials("admin")
            if user == adm_user and pw == adm_pass:
                level = "admin"

        if level != "user":
            self._error_lbl.hide()
            self.on_result(level, 0, 0)
            self.hide()
            self.deleteLater()
        else:
            self._attempts += 1
            remaining = self._max_attempts - self._attempts
            if remaining <= 0:
                self._locked_until = time.time() + self._lockout_secs
                self.on_result("user", 0, self._locked_until)
                self._show_lockout()
            else:
                self.on_result("user", self._attempts, 0)
                self._error_lbl.setText(
                    "Usu\u00e1rio ou senha incorretos. "
                    f"{remaining} tentativa(s) restante(s).")
                self._error_lbl.show()
                self._pw_entry.clear()
                self._pw_entry.setFocus()

    def _show_lockout(self) -> None:
        remaining = int(self._locked_until - time.time())
        self._user_entry.setEnabled(False)
        self._pw_entry.setEnabled(False)
        self._auth_btn.setEnabled(False)
        self._error_lbl.setText(f"Acesso bloqueado por {remaining}s")
        self._error_lbl.show()
