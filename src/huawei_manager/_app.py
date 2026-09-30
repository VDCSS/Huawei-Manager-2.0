import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from huawei_manager.themes import QSS_DARK, QSS_LIGHT

log = logging.getLogger(__name__)

_current_theme: str = ""

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


def apply_theme(name: str) -> None:
    global _current_theme
    if name == "dark":
        qss = QSS_DARK
    elif name == "light":
        qss = QSS_LIGHT
    else:
        msg = f"Unknown theme: {name!r}. Expected 'dark' or 'light'."
        raise ValueError(msg)
    if _current_theme == name:
        return
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyleSheet(qss)
    _current_theme = name
    log.info("Theme switched to %s", name)
