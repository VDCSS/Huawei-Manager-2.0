import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from huawei_manager.themes import QSS_DARK, QSS_HUAWEI, QSS_LIGHT, scale_qss

log = logging.getLogger(__name__)

_current_key: tuple[str, float] | None = None

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
    _current_key = key
    log.info("Theme switched to %s (zoom %.2f)", name, factor)
