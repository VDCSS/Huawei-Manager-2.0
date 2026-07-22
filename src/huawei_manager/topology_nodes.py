"""
topology_nodes.py — VNF node graphics items for TopologyCanvas.
================================================================
Custom QGraphicsRectItem representing a VNF node in the topology.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QGraphicsRectItem

from huawei_manager.topology_items import ITEM_DATA_KEY

if TYPE_CHECKING:
    from huawei_manager.topology import TopologyCanvas
    from huawei_manager.vnf_models import VNF


class _VNFNodeRect(QGraphicsRectItem):
    """Rectângulo principal do nó VNF — trata clique e hover visual."""

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
        self.setAcceptHoverEvents(True)
        self.setBrush(normal_brush)
        self.setData(ITEM_DATA_KEY, vnf.id)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._canvas._on_click(self._vnf)
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(self._hover_brush)
        self._canvas._on_hover_enter(self._vnf)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setBrush(self._normal_brush)
        self._canvas._on_hover_leave()
        super().hoverLeaveEvent(event)
