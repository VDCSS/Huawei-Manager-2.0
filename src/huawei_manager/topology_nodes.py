"""
topology_nodes.py — VNF node graphics items for TopologyCanvas.
================================================================
Custom QGraphicsRectItem representing a VNF node in the topology.
Features rounded corners, hover pen toggling, and smooth paint.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from huawei_manager.topology_items import ITEM_DATA_KEY

if TYPE_CHECKING:
    from huawei_manager.topology import TopologyCanvas
    from huawei_manager.vnf_models import VNF

_RADIUS = 6.0


class _VNFNodeRect(QGraphicsRectItem):
    """Rectângulo principal do nó VNF — rounded, clique, hover visual + pen."""

    def __init__(
        self,
        x: float, y: float, w: float, h: float,
        vnf: VNF,
        canvas: TopologyCanvas,
        normal_brush: QBrush,
        hover_brush: QBrush,
    ) -> None:
        super().__init__(x, y, w, h)
        self._vnf = vnf
        self._canvas = canvas
        self._normal_brush = normal_brush
        self._hover_brush = hover_brush
        self._normal_pen: QPen | None = None
        self._hover_pen: QPen | None = None
        self.setAcceptHoverEvents(True)
        self.setBrush(normal_brush)
        self.setData(ITEM_DATA_KEY, vnf.id)

    # ── Public pen API ─────────────────────────────────────────────

    def set_pen_pair(self, normal: QPen, hover: QPen) -> None:
        """Define a caneta normal e a caneta de hover (mais espessa/brilhante)."""
        self._normal_pen = normal
        self._hover_pen = hover
        self.setPen(normal)

    # ── Shape / Paint — rounded corners ────────────────────────────

    def shape(self) -> QPainterPath:
        """Hit-testing shape with rounded corners."""
        path = QPainterPath()
        path.addRoundedRect(self.rect(), _RADIUS, _RADIUS)
        return path

    def paint(self, painter, option, widget=None) -> None:
        """Draw a rounded rect with current brush and pen."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), _RADIUS, _RADIUS)
        painter.fillPath(path, self.brush())
        pen = self.pen()
        if pen.style() != Qt.PenStyle.NoPen:
            painter.setPen(pen)
            painter.drawPath(path)

    # ── Events ─────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._canvas._on_click(self._vnf)
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(self._hover_brush)
        if self._hover_pen is not None:
            self.setPen(self._hover_pen)
        self._canvas._on_hover_enter(self._vnf)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setBrush(self._normal_brush)
        if self._normal_pen is not None:
            self.setPen(self._normal_pen)
        self._canvas._on_hover_leave()
        super().hoverLeaveEvent(event)
