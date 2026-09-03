import time
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as _C

_ENTRY_STYLE = f"""QLineEdit {{
    background: {_C.BG_INPUT};
    color: {_C.NEON_CYAN};
    border: 1px solid {_C.BORDER_NRM};
    border-radius: 4px;
    padding: 6px 10px;
    font: 13px {_C.FONT_UI_FAMILY};
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
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.on_result = on_result
        self._max_attempts = admin_max_attempts
        self._lockout_secs = admin_lockout_secs
        self._locked_until = admin_locked_until
        self._attempts = attempts_so_far
        self._lockout_handled = False

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
            f"QPushButton {{ background: transparent; color: {_C.FG_DIM};"
            f" border: none; font: 14px {_C.FONT_UI_FAMILY}; }}"
            f"QPushButton:hover {{ color: {_C.NEON_CYAN}; }}")
        self._close_btn.clicked.connect(self.close_)
        header.addWidget(self._close_btn)
        card_layout.addLayout(header)

        title = QLabel("Acesso Restrito", self._card)
        title.setStyleSheet(
            f"color: {_C.NEON_CYAN}; font: bold 18px {_C.FONT_UI_FAMILY}; background: transparent; border: none;")
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
            "color: #ff4444; background: transparent; border: none; font: 12px {_C.FONT_UI_FAMILY};")
        self._error_lbl.hide()
        card_layout.addWidget(self._error_lbl)

        card_layout.addSpacing(8)

        self._auth_btn = QPushButton("Autenticar", self._card)
        self._auth_btn.setStyleSheet(
            f"QPushButton {{ background: {_C.BG_CARD}; color: {_C.NEON_CYAN}; "
            f"border: 1px solid {_C.NEON_CYAN}; border-radius: 6px; "
            f"padding: 8px 24px; font: bold 13px {_C.FONT_UI_FAMILY}; }}"
            f"QPushButton:hover {{ background: {_C.NEON_CYAN}; color: {_C.BG_CARD}; }}")
        self._auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auth_btn.clicked.connect(self._verify)
        card_layout.addWidget(self._auth_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        h_layout.addWidget(self._card)
        h_layout.addStretch()
        layout.addLayout(h_layout)
        layout.addStretch()

        self._pw_entry.returnPressed.connect(self._verify)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_()
        super().keyPressEvent(event)

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
        if not self._lockout_handled:
            self.on_result("user", self._attempts, locked)
        self.hide()
        self.deleteLater()

    def _verify(self) -> None:
        if time.time() < self._locked_until:
            self._show_lockout()
            return

        from huawei_manager.db import get_connection
        from huawei_manager.user_repository import UserRepository

        user = self._user_entry.text().strip()
        pw = self._pw_entry.text()

        try:
            conn = get_connection()
            user_repo = UserRepository(conn)
            user_repo.seed_default_users()
            authenticated_user = user_repo.verify_password(user, pw)

            if authenticated_user is not None:
                level = authenticated_user.role
                self._error_lbl.hide()
                self.on_result(level, 0, 0)
                self.hide()
                self.deleteLater()
                return

            self._attempts += 1
            remaining = self._max_attempts - self._attempts
            if remaining <= 0:
                self._locked_until = time.time() + self._lockout_secs
                self.on_result("user", 0, self._locked_until)
                self._lockout_handled = True
                self._show_lockout()
            else:
                self.on_result("user", self._attempts, 0)
                self._error_lbl.setText(
                    "Usuário ou senha incorretos. "
                    f"{remaining} tentativa(s) restante(s).")
                self._error_lbl.show()
                self._pw_entry.clear()
                self._pw_entry.setFocus()
        except Exception:
            # Fail-closed: treat any error as authentication failure
            self._attempts += 1
            remaining = self._max_attempts - self._attempts
            if remaining <= 0:
                self._locked_until = time.time() + self._lockout_secs
                self.on_result("user", 0, self._locked_until)
                self._lockout_handled = True
                self._show_lockout()
            else:
                self.on_result("user", self._attempts, 0)
                self._error_lbl.setText(
                    "Erro de autenticação. "
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
        if remaining > 0:
            QTimer.singleShot(self._lockout_secs * 1000, self._reenable_after_lockout)

    def _reenable_after_lockout(self) -> None:
        """Reabilita inputs apos lockout, seguro para widget deletado."""
        try:
            if time.time() >= self._locked_until:
                self._user_entry.setEnabled(True)
                self._pw_entry.setEnabled(True)
                self._auth_btn.setEnabled(True)
                self._error_lbl.setText("")
                self._error_lbl.hide()
        except RuntimeError:
            pass  # Widget foi deletado (dialog fechado durante lockout)
