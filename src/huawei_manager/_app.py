import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from huawei_manager.themes import (
    QSS_DARK,
    QSS_HUAWEI,
    QSS_LIGHT,
    scale_css,
    scale_qss,
)

log = logging.getLogger(__name__)

_current_key: tuple[str, float] | None = None


def scale_inline_style(style: str, factor: float) -> str:
    """Escala apenas as fontes de um stylesheet inline já aplicado.

    ``clamp=False`` é essencial: o CSS já foi escalado uma vez, então a razão
    incremental pode estar fora da faixa 0.5–1.5 (ex.: 1.0/1.5 = 0.667).
    """
    if not style or factor == 1.0:
        return style
    return scale_css(style, factor, clamp=False)


def scale_all_inline_styles(factor: float) -> None:
    """Reescala os stylesheets inline de todos os widgets vivos."""
    if factor == 1.0:
        return
    for widget in QApplication.allWidgets():
        try:
            css = widget.styleSheet()
        except RuntimeError:
            continue
        if not css:
            continue
        try:
            widget.setStyleSheet(scale_inline_style(css, factor))
        except RuntimeError:
            continue


def get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([])
    if not isinstance(app, QApplication):
        raise TypeError("app must be a QApplication instance")
    return app


def apply_theme(name: str, zoom: float = 1.0) -> None:
    """Aplica tema e fator de zoom global (tipografia do QSS).

    ``zoom=1.0`` preserva o comportamento anterior. O cache considera tema
    **e** zoom para que trocar apenas a escala reaplique o QSS.
    """
    global _current_key
    previous_factor = _current_key[1] if _current_key is not None else None
    if name == "dark":
        qss = QSS_DARK
    elif name == "light":
        qss = QSS_LIGHT
    elif name == "huawei":
        qss = QSS_HUAWEI
    else:
        msg = f"Unknown theme: {name!r}. Expected 'dark', 'light' or 'huawei'."
        raise ValueError(msg)
    factor = max(0.5, min(1.5, zoom))
    key = (name, factor)
    if _current_key == key:
        return
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyleSheet(scale_qss(qss, factor))
        if previous_factor is not None and factor != previous_factor:
            scale_all_inline_styles(factor / previous_factor)
    _current_key = key
    log.info("Theme switched to %s (zoom %.2f)", name, factor)
