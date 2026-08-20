"""QLabel com elide à direita (Qt6) — texto longo é truncado com '…' quando não cabe."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QWidget


class ElideLabel(QLabel):
    """QLabel que elide o texto à direita quando a largura disponível encolhe."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self._apply_elide()

    def setText(self, text: str) -> None:
        self._full_text = text
        self._apply_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        super().setText(elided)
