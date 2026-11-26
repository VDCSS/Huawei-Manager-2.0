"""Controle global de zoom da aplicação.

A lupa fica no topbar num slot reservado de 34 px (visível só quando o zoom
diferente de 100%). O clique abre um popup ancorado com um ``QSpinBox`` que
já contém o sufixo ``%`` e três botões circulares: ``+``, ``−`` e
``Redefinir``. Estado e persistência vivem aqui; a aplicação apenas reage
ao sinal ``zoomChanged``.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QSettings,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QToolButton,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.widgets.icons import icon_pixmap

MIN_ZOOM = 50
MAX_ZOOM = 150
DEFAULT_ZOOM = 100

_CIRCLE_CSS = (
    "{sel} {{ background: {bg}; color: {fg};"
    " border: 2px solid {border}; border-radius: {radius}px;"
    " font: bold {font}px \"{family}\"; }}"
)
_HOVER_CSS = (
    "{sel}:hover {{ background: {hover}; color: {fg};"
    " border: 2px solid {cyan}; border-radius: {radius}px; }}"
)


def _clamp(value: int) -> int:
    return max(MIN_ZOOM, min(MAX_ZOOM, int(value)))


def _as_int(value: object, default: int) -> int:
    if not isinstance(value, int | str):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _alpha_hex(value: str, alpha: float) -> str:
    """QSS aceita ``#AARRGGBB``; ``rgba(...%)`` não é confiável."""
    a = int(max(0.0, min(1.0, alpha)) * 255)
    return f"#{a:02x}{value.lstrip('#')}"


class ZoomControl(QWidget):
    """Lupa + popup de zoom, com estado centralizado e persistência."""

    zoomChanged = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        initial: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "HuaweiManager",
            "Preferences",
        )
        saved = self._settings.value("ui_zoom", DEFAULT_ZOOM)
        raw = DEFAULT_ZOOM if initial is None else _as_int(initial, DEFAULT_ZOOM)
        persisted = _as_int(saved, DEFAULT_ZOOM)
        self._zoom = _clamp(raw if initial is not None else persisted)
        self._updating = False

        self.slot = QWidget(self)
        self.slot.setObjectName("zoomSlot")
        self.slot.setFixedSize(34, 34)
        slot_layout = QHBoxLayout(self.slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)

        self.magnifier = QToolButton(self.slot)
        self.magnifier.setObjectName("zoomMagnifierBtn")
        self.magnifier.setFixedSize(34, 34)
        self.magnifier.setCursor(Qt.CursorShape.PointingHandCursor)
        self.magnifier.setIcon(QIcon(icon_pixmap("i-search", C.NEON_CYAN, 18)))
        self.magnifier.setIconSize(QSize(18, 18))
        self.magnifier.setToolTip("Zoom da interface (Ctrl + + / Ctrl + -)")
        self.magnifier.clicked.connect(self.show_popup)
        slot_layout.addWidget(self.magnifier)

        self.popup = QFrame(None, Qt.WindowType.Popup)
        self.popup.setObjectName("zoomPopup")
        self.popup.setFixedSize(256, 98)
        self.popup.setStyleSheet(
            f"#zoomPopup {{ background: {C.BG_SURFACE_2};"
            f" border: 1px solid {C.BORDER_NRM}; border-radius: 10px; }}"
        )
        row = QHBoxLayout(self.popup)
        # 11 px laterais: o frame de 1 px do popup consome 2 px da largura;
        # 11 + 72 + 8 + 40 + 8 + 40 + 8 + 56 + 11 = 254 px úteis.
        row.setContentsMargins(11, 12, 11, 12)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.spin = QSpinBox(self.popup)
        self.spin.setObjectName("zoomSpin")
        self.spin.setRange(MIN_ZOOM, MAX_ZOOM)
        self.spin.setSuffix("%")
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin.setFixedWidth(72)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setStyleSheet(
            f"#zoomSpin {{ background: {C.BG_INPUT}; color: {C.FG_MAIN};"
            f" border: 1px solid {C.BORDER_NRM}; border-radius: 6px;"
            f" padding: 4px 6px; font: bold 13px '{C.FONT_MONO_FAMILY}'; }}"
        )
        self.spin.valueChanged.connect(self.set_zoom)
        row.addWidget(self.spin)

        self.plus_btn = self._make_circle("+", "zoomPlusBtn", 40, 20)
        self.plus_btn.clicked.connect(lambda: self.step(10))
        row.addWidget(self.plus_btn)

        self.minus_btn = self._make_circle("−", "zoomMinusBtn", 40, 20)
        self.minus_btn.clicked.connect(lambda: self.step(-10))
        row.addWidget(self.minus_btn)

        self.reset_btn = self._make_circle("Redefinir", "zoomResetBtn", 56, 28, 9)
        self.reset_btn.clicked.connect(self.reset)
        row.addWidget(self.reset_btn)

        self._updating = True
        self.spin.setValue(self._zoom)
        self._updating = False
        self.magnifier.setVisible(self._zoom != DEFAULT_ZOOM)

    # ── API pública ─────────────────────────────────────────────────
    def zoom(self) -> int:
        return self._zoom

    def set_zoom(self, value: int) -> None:
        value = _clamp(value)
        if value == self._zoom:
            return
        self._zoom = value
        self._settings.setValue("ui_zoom", value)
        self._settings.sync()
        self._updating = True
        self.spin.setValue(value)
        self._updating = False
        self.magnifier.setVisible(value != DEFAULT_ZOOM)
        if value == DEFAULT_ZOOM:
            self.hide_popup()
        self.zoomChanged.emit(value)

    def step(self, delta: int) -> None:
        self.set_zoom(self._zoom + delta)

    def reset(self) -> None:
        self.set_zoom(DEFAULT_ZOOM)
        self.hide_popup()

    # ── Popup ───────────────────────────────────────────────────────
    def show_popup(self) -> None:
        if self.popup.isVisible():
            return
        anchor = self.magnifier.mapToGlobal(QPoint(0, self.magnifier.height()))
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(anchor.x(), area.left()), area.right() - self.popup.width())
        y = anchor.y() + 6
        if y + self.popup.height() > area.bottom():
            above = self.magnifier.mapToGlobal(QPoint(0, 0)).y() - self.popup.height() - 6
            y = max(area.top(), above)
        self.popup.move(x, y)
        self.popup.show()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.installEventFilter(self)

    def hide_popup(self) -> None:
        if not self.popup.isVisible():
            return
        self.popup.hide()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.removeEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: ANN001
        try:
            visible = self.popup.isVisible()
        except RuntimeError:
            return False
        if not visible:
            return False
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        pos = event.globalPosition().toPoint()
        if not self.popup.geometry().contains(pos):
            self.hide_popup()
        return False

    # ── Helpers ─────────────────────────────────────────────────────
    def _make_circle(
        self,
        text: str,
        object_name: str,
        size: int,
        radius: int,
        font: int = 16,
    ) -> QPushButton:
        btn = QPushButton(text, self.popup)
        btn.setObjectName(object_name)
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        css = _CIRCLE_CSS.format(
            sel=f"#{object_name}",
            bg=C.BG_SURFACE_3,
            fg=C.FG_MAIN,
            border=C.BORDER_NRM,
            radius=radius,
            font=font,
            family=C.FONT_UI_FAMILY,
        )
        css += "\n" + _HOVER_CSS.format(
            sel=f"#{object_name}",
            hover=_alpha_hex(C.NEON_CYAN, 0.12),
            fg=C.NEON_CYAN,
            cyan=C.NEON_CYAN,
            radius=radius,
        )
        btn.setStyleSheet(css)
        return btn
