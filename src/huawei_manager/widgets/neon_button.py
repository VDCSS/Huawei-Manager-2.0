"""Botões do design system — equivalentes a ``.btn`` e ``.nav__item`` do MVP.

``ActionButton`` é o botão de ação (``.btn`` do MVP: 38 px, 13.5 px,
``surface-2`` e hover em ``surface-hover``), com variantes ``outline``,
``primary``, ``danger`` e ``ghost`` usadas no shell.

``NeonButton`` é o item de navegação da sidebar (``.nav__item``). Como o
MVP usa gradiente + barra de acento desenhados em CSS (``::before``), o item
é pintado à mão em :meth:`NeonButton.paintEvent`: fundo com gradiente
``cyan-soft → transparent`` no estado ativo, barra de 3 px na borda
esquerda, ícone SVG de 19 px na cor do grupo e badge opcional à direita.
"""
from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

import huawei_manager.constants as _C
from huawei_manager.widgets.icons import icon_pixmap


# ─── helpers de tema ────────────────────────────────────────────────
def _is_light_theme() -> bool:
    """Temas claros (White e Huawei) compartilham os ajustes de contraste."""
    return _C.THEME.get("BG_BASE") in (_C.BG_BASE_L, _C.BG_BASE_H)


def _with_alpha(color: str, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class ActionButton(QPushButton):
    """Botão de ação (MVP ``.btn``) com variantes de ênfase.

    Variantes:
        ``default``  — ``surface-2`` + borda, hover ``surface-hover``
        ``outline``  — transparente, texto/borda no acento, hover sólido
        ``primary``  — acento sólido com texto de contraste
        ``danger``   — transparente, vermelho, hover ``red-soft``
        ``ghost``    — transparente, sem borda, hover ``surface-hover``
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        text: str = "",
        command: Callable[[], object] | None = None,
        color: str = _C.NEON_CYAN,
        variant: str = "default",
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._command = command
        self._color = color
        self._variant = variant
        self._disabled = False

        self.setText(text)
        self.setMinimumHeight(_C.BTN_MIN_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if command is not None:
            self.clicked.connect(command)

        self._apply_style()

    # ── paleta por variante ──────────────────────────────────────────
    def _palette(self) -> tuple[str, str, str, str, str, str]:
        """Retorna (bg, fg, border, hover_bg, hover_fg, hover_border)."""
        if self._disabled:
            return (
                _C.BG_SURFACE_2, _C.FG_FAINT, _C.BORDER_SOFT,
                _C.BG_SURFACE_2, _C.FG_FAINT, _C.BORDER_SOFT,
            )

        variant = self._variant
        if variant == "outline":
            return (
                "transparent", self._color, _C.rgba(self._color, 0.34),
                self._color, _C.THEME.get("CYAN_INK", "#041116"), self._color,
            )
        if variant == "primary":
            return (
                self._color, _C.THEME.get("CYAN_INK", "#041116"), self._color,
                _C.NEON_CYAN_STRONG, _C.THEME.get("CYAN_INK", "#041116"),
                _C.NEON_CYAN_STRONG,
            )
        if variant == "danger":
            return (
                "transparent", _C.NEON_RED, _C.rgba(_C.NEON_RED, 0.34),
                _C.rgba(_C.NEON_RED, 0.12), _C.NEON_RED, _C.NEON_RED,
            )
        if variant == "ghost":
            return (
                "transparent", _C.FG_DIM, "transparent",
                _C.BG_HOVER, _C.FG_MAIN, _C.BORDER_SOFT,
            )
        # default (.btn)
        return (
            _C.BG_SURFACE_2, _C.FG_CODE, _C.BORDER_NRM,
            _C.BG_HOVER, _C.FG_MAIN, _C.BORDER_STRONG,
        )

    def _apply_style(self) -> None:
        bg, fg, border, hover_bg, hover_fg, hover_border = self._palette()
        self.setStyleSheet(f"""
            ActionButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 0px 16px;
                min-height: {_C.BTN_MIN_HEIGHT}px;
                font: 500 {_C.BTN_FONT_SIZE}px '{_C.FONT_UI_FAMILY}';
            }}
            ActionButton:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
                border: 1px solid {hover_border};
            }}
            ActionButton:pressed {{
                background-color: {_C.BG_SOFT};
                color: {hover_fg};
            }}
            ActionButton:focus {{
                border-color: {self._color};
            }}
            ActionButton:disabled {{
                background-color: {_C.BG_SURFACE_2};
                color: {_C.FG_FAINT};
                border-color: {_C.BORDER_SOFT};
            }}
        """)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if not self._disabled else Qt.CursorShape.ArrowCursor
        )

    def configure(
        self,
        text: str | None = None,
        state: str | None = None,
        command: Callable[[], object] | None = None,
        color: str | None = None,
        variant: str | None = None,
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
        if variant is not None:
            self._variant = variant
        self._apply_style()


def action_button(
    parent: QWidget,
    text: str = "",
    command: Callable[..., object] | None = None,
    color: str = _C.NEON_CYAN,
    variant: str = "default",
) -> ActionButton:
    return ActionButton(parent, text, command, color, variant)


class NeonButton(QPushButton):
    """Item de navegação da sidebar (MVP ``.nav__item``).

    O widget ocupa toda a largura da sidebar; o fundo do item é desenhado
    com 8 px de recuo lateral (paridade com ``margin: 0 8px``) e a barra de
    acento de 3 px fica encostada na borda esquerda (``left: -8px`` no MVP).
    """

    _SIDE_INSET = 8
    _PAD_X = 11
    _ICON_SIZE = _C.NAV_ICON_SIZE
    _GAP = 11

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
        self._icon_id = icon
        self._label_text = text
        self._active = False
        self._hover = False
        self._badge_text = ""
        self._icon_cache: QPixmap | None = None

        self.setText(text)
        self.setMinimumHeight(_C.NAV_ITEM_HEIGHT)
        self.setMaximumHeight(_C.NAV_ITEM_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if command is not None:
            self.clicked.connect(command)

        self._font = QFont(_C.FONT_UI_FAMILY)
        self._font.setPixelSize(14)
        self._font.setWeight(QFont.Weight.Medium)
        self._apply_style()

    # ── API ──────────────────────────────────────────────────────────
    def set_badge(self, text: str) -> None:
        """Badge "live" à direita do item (ex.: Dashboard)."""
        self._badge_text = text
        self.update()

    def set_icon(self, icon_id: str) -> None:
        self._icon_id = icon_id
        self._icon_cache = None
        self.update()

    def _apply_style(self) -> None:
        # A pintura é feita em paintEvent; o QSS só remove o chrome padrão.
        # min/max-height repetem a geometria do MVP porque o QSS global de
        # QPushButton (38 px) tem precedência sobre setMinimumHeight().
        self.setStyleSheet(
            f"NeonButton {{ background: transparent; border: none;"
            f" min-height: {_C.NAV_ITEM_HEIGHT}px;"
            f" max-height: {_C.NAV_ITEM_HEIGHT}px; }}")
        self.setFont(self._font)
        self.update()

    def _icon_pixmap(self) -> QPixmap | None:
        if self._icon_cache is None:
            if self._icon_id:
                self._icon_cache = icon_pixmap(
                    self._icon_id, self._color, self._ICON_SIZE
                )
            else:
                self._icon_cache = None
        return self._icon_cache

    # ── estado ───────────────────────────────────────────────────────
    def _activate(self) -> None:
        self._active = True
        self.update()

    def _deactivate(self) -> None:
        self._active = False
        self.update()

    # ── eventos ──────────────────────────────────────────────────────
    def enterEvent(self, event: QEnterEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(200, _C.NAV_ITEM_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, _C.NAV_ITEM_HEIGHT)

    # ── pintura ──────────────────────────────────────────────────────
    def paintEvent(self, _event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        r = QRectF(self.rect())
        item = r.adjusted(self._SIDE_INSET, 0, -self._SIDE_INSET, 0)
        light = _is_light_theme()
        active = self._active
        hover = self._hover and self.isEnabled()

        # fundo
        if active:
            if light:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#e0e0e0"))
                p.drawRoundedRect(item, _C.NAV_ITEM_RADIUS, _C.NAV_ITEM_RADIUS)
            else:
                grad = QLinearGradient(item.left(), 0, item.right(), 0)
                grad.setColorAt(0.0, _with_alpha(_C.NEON_CYAN, 0.09))
                grad.setColorAt(0.92, QColor(0, 0, 0, 0))
                grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(grad)
                p.drawRoundedRect(item, _C.NAV_ITEM_RADIUS, _C.NAV_ITEM_RADIUS)
        elif hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e4e4e4") if light else QColor(_C.BG_HOVER))
            p.drawRoundedRect(item, _C.NAV_ITEM_RADIUS, _C.NAV_ITEM_RADIUS)

        # barra de acento
        if active:
            bar = QRectF(
                r.left(), item.top() + 8, _C.NAV_ACCENT_BAR_W, item.height() - 16
            )
            if not light:
                glow = QColor(_C.NEON_CYAN)
                glow.setAlphaF(0.35)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawRoundedRect(
                    QRectF(bar.left() - 2, bar.top(), bar.width() + 4, bar.height()),
                    3, 3,
                )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_C.NEON_CYAN))
            p.drawRoundedRect(bar, 1.5, 1.5)

        # cores do texto
        if not self.isEnabled():
            text_color = QColor(_C.FG_FAINT)
        elif active:
            text_color = QColor("#1a1a1a") if light else QColor(_C.FG_MAIN)
        elif hover:
            text_color = QColor(_C.FG_MAIN)
        else:
            text_color = QColor(_C.FG_DIM)

        x = item.left() + self._PAD_X
        content_right = item.right() - self._PAD_X

        # ícone SVG
        pm = self._icon_pixmap()
        if pm is not None:
            iy = item.top() + (item.height() - self._ICON_SIZE) / 2
            p.drawPixmap(QPointF(x, iy), pm)
            x += self._ICON_SIZE + self._GAP

        # badge (reserva espaço à direita)
        badge_left = content_right
        if self._badge_text:
            badge_font = QFont(_C.FONT_MONO_FAMILY)
            badge_font.setPixelSize(10)
            fm_b = QFontMetricsF(badge_font)
            text_w = fm_b.horizontalAdvance(self._badge_text)
            badge_w = 7 + 4 + 3 + text_w + 7
            badge_h = 16
            badge_left = content_right - badge_w
            badge_rect = QRectF(
                badge_left, item.top() + (item.height() - badge_h) / 2,
                badge_w, badge_h,
            )
            p.setPen(QPen(QColor(_C.rgba(_C.NEON_GREEN, 0.30)), 1))
            p.setBrush(QColor(_C.rgba(_C.NEON_GREEN, 0.10)))
            p.drawRoundedRect(badge_rect, 8, 8)
            # dot 4 px
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_C.NEON_GREEN))
            p.drawEllipse(
                QPointF(badge_rect.left() + 9, badge_rect.center().y()), 2, 2
            )
            p.setFont(badge_font)
            p.setPen(QColor(_C.NEON_GREEN))
            p.drawText(
                QRectF(
                    badge_rect.left() + 14, badge_rect.top(),
                    badge_rect.width() - 18, badge_rect.height(),
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._badge_text,
            )

        # rótulo
        if self._label_text:
            p.setFont(self._font)
            p.setPen(text_color)
            text_rect = QRectF(x, item.top(), max(0.0, badge_left - x - 8), item.height())
            p.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._label_text,
            )

        # foco (anel ciano discreto)
        if self.hasFocus():
            p.setPen(QPen(QColor(_C.rgba(_C.NEON_CYAN, 0.55)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(
                item.adjusted(0.5, 0.5, -0.5, -0.5),
                _C.NAV_ITEM_RADIUS, _C.NAV_ITEM_RADIUS,
            )

        p.end()


def neon_button(
    parent: QWidget,
    text: str = "",
    command: Callable[..., object] | None = None,
    color: str = _C.NEON_CYAN,
    icon: str = "",
) -> NeonButton:
    return NeonButton(parent, text, command, color, icon)
