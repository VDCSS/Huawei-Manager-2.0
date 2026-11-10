"""Drawer lateral deslizante para confirmações (sem modais centrais).

Traduz o ``#discardDrawer`` e ``#drawerScrim`` do MVP para PySide6.
O drawer desliza a partir da borda direita da janela, cobrindo o conteúdo
com um scrim semi-transparente. Medidas do MVP: 440 px, cabeçalho 24/22/20,
ícone 40 px, h2 20 px, corpo 24/22 e rodapé ``surface-2`` 18/22.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.widgets.icons import icon, icon_pixmap


class ConfirmDrawer(QWidget):
    """Drawer lateral deslizante de confirmação sobre a janela principal."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("drawerRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setVisible(False)

        self._on_confirm: Callable[[], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._drawer_width = 440

        # Scrim / backdrop (fundo escurecido clicável para fechar)
        self.scrim = QFrame(self)
        self.scrim.setObjectName("drawerScrim")
        self.scrim.setStyleSheet("background: rgba(5, 5, 13, 0.55);")
        self.scrim.mousePressEvent = lambda _e: self.close_drawer()

        # Painel lateral deslizante
        self.panel = QFrame(self)
        self.panel.setObjectName("drawerPanel")
        self.panel.setStyleSheet(f"""
            #drawerPanel {{
                background-color: {C.BG_BASE};
                border-left: 1px solid {C.BORDER_STRONG};
            }}
        """)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Cabeçalho (24/22/20, ícone 40, h2 20) ────────────────────
        head_widget = QWidget(self.panel)
        head_widget.setObjectName("drawerHead")
        head_widget.setStyleSheet(
            f"#drawerHead {{ background: transparent;"
            f" border-bottom: 1px solid {C.BORDER_NRM}; }}")
        head_layout = QHBoxLayout(head_widget)
        head_layout.setContentsMargins(24, 24, 22, 20)
        head_layout.setSpacing(14)

        icon_box = QLabel(head_widget)
        icon_box.setObjectName("drawerIcon")
        icon_box.setFixedSize(40, 40)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"""
            #drawerIcon {{
                background: {C.rgba(C.NEON_AMBER, 0.10)};
                border: 1px solid {C.rgba(C.NEON_AMBER, 0.30)};
                border-radius: 6px;
            }}
        """)
        icon_box.setPixmap(icon_pixmap("i-alert-triangle", C.NEON_AMBER, 19))
        head_layout.addWidget(icon_box)

        title_col = QWidget(head_widget)
        title_col.setStyleSheet("background: transparent;")
        title_col_layout = QVBoxLayout(title_col)
        title_col_layout.setContentsMargins(0, 0, 0, 0)
        title_col_layout.setSpacing(2)

        self.eyebrow_lbl = QLabel("CONFIRMAÇÃO", title_col)
        self.eyebrow_lbl.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 11px '{C.FONT_MONO_FAMILY}'; letter-spacing: 0.11em;")
        title_col_layout.addWidget(self.eyebrow_lbl)

        self.title_lbl = QLabel("Descartar configuração?", title_col)
        self.title_lbl.setStyleSheet(
            f"color: {C.FG_MAIN}; background: transparent;"
            f" font: 600 20px '{C.FONT_UI_TITLE_FAMILY}';")
        self.title_lbl.setWordWrap(True)
        title_col_layout.addWidget(self.title_lbl)

        head_layout.addWidget(title_col, stretch=1)

        close_btn = QPushButton(head_widget)
        close_btn.setObjectName("drawerCloseBtn")
        close_btn.setFixedSize(34, 34)
        close_btn.setIcon(icon("i-x", C.FG_DIM, 16))
        close_btn.setIconSize(QSize(16, 16))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            #drawerCloseBtn {{
                background: transparent;
                color: {C.FG_DIM};
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            #drawerCloseBtn:hover {{
                background: {C.BG_HOVER};
                color: {C.FG_MAIN};
                border-color: {C.BORDER_SOFT};
            }}
        """)
        close_btn.clicked.connect(self.close_drawer)
        head_layout.addWidget(close_btn)

        layout.addWidget(head_widget)

        # ── Corpo (padding 24/22) ────────────────────────────────────
        body = QWidget(self.panel)
        body.setObjectName("drawerBody")
        body.setStyleSheet("#drawerBody { background: transparent; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 24, 22, 24)
        body_layout.setSpacing(14)

        self.message_lbl = QLabel(
            "A alteração em andamento ainda não foi aplicada ao dispositivo. "
            "Se sair agora, as etapas preenchidas serão perdidas.",
            body,
        )
        self.message_lbl.setStyleSheet(
            f"color: {C.FG_CODE}; background: transparent;"
            f" font: 14px '{C.FONT_UI_FAMILY}';")
        self.message_lbl.setWordWrap(True)
        body_layout.addWidget(self.message_lbl)

        # Caixa de dica / aviso (surface + border-soft, 12/14, 12.5 px)
        self.hint_box = QFrame(body)
        self.hint_box.setStyleSheet(f"""
            QFrame {{
                background: {C.BG_CARD};
                border: 1px solid {C.BORDER_SOFT};
                border-radius: 6px;
            }}
        """)
        hint_layout = QVBoxLayout(self.hint_box)
        hint_layout.setContentsMargins(14, 12, 14, 12)
        self.hint_lbl = QLabel(
            "Nenhuma alteração foi gravada na running-config do roteador.",
            self.hint_box,
        )
        self.hint_lbl.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent;"
            f" font: 12.5px '{C.FONT_UI_FAMILY}';")
        self.hint_lbl.setWordWrap(True)
        hint_layout.addWidget(self.hint_lbl)
        body_layout.addWidget(self.hint_box)

        body_layout.addStretch(1)
        layout.addWidget(body, stretch=1)

        # ── Rodapé (surface-2, 18/22, gap 10) ────────────────────────
        foot_widget = QWidget(self.panel)
        foot_widget.setObjectName("drawerFoot")
        foot_widget.setStyleSheet(
            f"#drawerFoot {{ background: {C.BG_SURFACE_2};"
            f" border-top: 1px solid {C.BORDER_NRM}; }}")
        foot_layout = QHBoxLayout(foot_widget)
        foot_layout.setContentsMargins(22, 18, 22, 18)
        foot_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Continuar editando", foot_widget)
        self.cancel_btn.setMinimumHeight(C.BTN_MIN_HEIGHT)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.FG_MAIN};
                border: 1px solid {C.BORDER_NRM};
                border-radius: 6px;
                padding: 0 16px;
                font: 500 {C.BTN_FONT_SIZE}px '{C.FONT_UI_FAMILY}';
            }}
            QPushButton:hover {{
                background: {C.BG_HOVER};
                border-color: {C.BORDER_STRONG};
            }}
        """)
        self.cancel_btn.clicked.connect(self.close_drawer)
        foot_layout.addWidget(self.cancel_btn, stretch=1)

        self.confirm_btn = QPushButton("Descartar e sair", foot_widget)
        self.confirm_btn.setMinimumHeight(C.BTN_MIN_HEIGHT)
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.NEON_RED};
                color: #ffffff;
                border: 1px solid {C.NEON_RED};
                border-radius: 6px;
                padding: 0 16px;
                font: 600 {C.BTN_FONT_SIZE}px '{C.FONT_UI_FAMILY}';
            }}
            QPushButton:hover {{
                background: #a50d25;
                border-color: #a50d25;
            }}
        """)
        self.confirm_btn.clicked.connect(self._handle_confirm)
        foot_layout.addWidget(self.confirm_btn, stretch=1)

        layout.addWidget(foot_widget)

    def open_drawer(
        self,
        title: str = "Descartar configuração?",
        message: str = "",
        on_confirm: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        confirm_text: str = "Descartar e sair",
        cancel_text: str = "Continuar editando",
        eyebrow: str = "CONFIRMAÇÃO",
        is_danger: bool = True,
    ) -> None:
        """Abre o drawer lateral sobre o parentWidget."""
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        self.title_lbl.setText(title)
        if message:
            self.message_lbl.setText(message)
        self.eyebrow_lbl.setText(eyebrow)
        self.confirm_btn.setText(confirm_text)
        self.cancel_btn.setText(cancel_text)

        btn_color = C.NEON_RED if is_danger else C.NEON_CYAN
        hover_color = "#a50d25" if is_danger else C.NEON_CYAN_STRONG
        text_color = "#ffffff" if is_danger else C.BG_BASE
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {btn_color};
                color: {text_color};
                border: 1px solid {btn_color};
                border-radius: 6px;
                padding: 0 16px;
                font: 600 {C.BTN_FONT_SIZE}px '{C.FONT_UI_FAMILY}';
            }}
            QPushButton:hover {{
                background: {hover_color};
                border-color: {hover_color};
            }}
        """)

        parent = self.parentWidget()
        if parent is not None:
            w, h = parent.width(), parent.height()
            self.setGeometry(0, 0, w, h)
            self.scrim.setGeometry(0, 0, w, h)
            dw = min(self._drawer_width, w)
            self.panel.setGeometry(w - dw, 0, dw, h)

        self.setVisible(True)
        self.raise_()
        self.cancel_btn.setFocus()

    def close_drawer(self) -> None:
        """Fecha o drawer e aciona o callback de cancelamento, se houver."""
        if not self.isVisible():
            return
        callback = self._on_cancel
        self._on_confirm = None
        self._on_cancel = None
        self.setVisible(False)
        if callback:
            callback()

    def _handle_confirm(self) -> None:
        """Processa a confirmação e fecha o drawer."""
        callback = self._on_confirm
        self._on_confirm = None
        self._on_cancel = None
        self.setVisible(False)
        if callback:
            callback()

    def sync_geometry(self) -> None:
        """Sincroniza o tamanho do drawer quando o parent é redimensionado."""
        parent = self.parentWidget()
        if parent is not None and self.isVisible():
            w, h = parent.width(), parent.height()
            self.setGeometry(0, 0, w, h)
            self.scrim.setGeometry(0, 0, w, h)
            dw = min(self._drawer_width, w)
            self.panel.setGeometry(w - dw, 0, dw, h)
