"""
topology.py — Device Topology + Canvas (PySide6)
================================================
Gerenciamento de Devices via inventário local (vnf_inventory.json),
probe TCP real e simulação de status (modo mock).
Canvas baseado em QGraphicsView / QGraphicsScene.

O Device selecionado no canvas é usado como alvo para conexão SSH via Netmiko.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.topology_effects import draw_background_grid, draw_sdn_bar
from huawei_manager.topology_items import (
    ITEM_DATA_KEY,
    _build_tooltip_text,
    _color_for,
    _status_color,
    _to_qfont,
)
from huawei_manager.topology_nodes import _DeviceNodeRect

log = logging.getLogger("huawei.topology")


# ═══════════════════════════════════════════════════════════════════════
#  CUSTOM GRAPHICS VIEW — trata menu de contexto + resize
# ═══════════════════════════════════════════════════════════════════════

class _TopoView(QGraphicsView):
    """QGraphicsView que delega context menu e resize ao canvas."""

    def __init__(self, scene: QGraphicsScene, canvas: TopologyCanvas) -> None:
        super().__init__(scene)
        self._canvas = canvas

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item:
            device_id = item.data(ITEM_DATA_KEY)
            if device_id is not None and device_id in self._canvas._device_map:
                self._canvas._on_context_menu(event, self._canvas._device_map[device_id])
                return
        super().contextMenuEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._canvas._draw()


# ═══════════════════════════════════════════════════════════════════════
#  TOPOLOGY CANVAS (Qt)
# ═══════════════════════════════════════════════════════════════════════

class TopologyCanvas(QWidget):
    """
    Canvas de topologia baseado em QGraphicsView / QGraphicsScene.

    Renderiza Devices num grid de 4 colunas com barra SDN no topo.
    Suporta seleção, tooltip, menu de contexto e destaque hover.
    """

    NODE_W, NODE_H = 180, 70

    def __init__(
        self,
        parent: QWidget | None = None,
        on_select: Callable[[Device], None] | None = None,
        on_edit:   Callable[[Device], None] | None = None,
        on_delete: Callable[[Device], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._edit_cb = on_edit
        self._delete_cb = on_delete
        self._devices: list[Device] = []
        self._selected: Device | None = None
        self._access_level: str = "user"
        self._device_map: dict[str, Device] = {}
        self._last_hover_device_id: str | None = None

        self.setStyleSheet(f"background: {C.BG_BASE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(QColor(C.BG_BASE)))

        self._view = _TopoView(self._scene, self)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        self._view.setStyleSheet(f"background: {C.BG_BASE}; border: none;")
        self._view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._view.setMouseTracking(True)
        layout.addWidget(self._view)

    # ── Interface pública ───────────────────────────────────────────

    def set_access(self, level: str) -> None:
        """Define o nível de acesso (user / admin / tecnico)."""
        self._access_level = level
        # tooltip text depende do nível → redesenha
        self._draw()

    def update_devices(self, devices: list[Device]) -> None:
        """Atualiza a lista de Devices e redesenha."""
        if not devices and self._devices:
            log.warning("update_devices: ignorando lista vazia (existem %d Devices)", len(self._devices))
            return
        self._devices = devices
        self._device_map = {v.id: v for v in devices}
        self._draw()

    def get_selected(self) -> Device | None:
        """Retorna o Device atualmente selecionado ou None."""
        return self._selected

    def deselect(self) -> None:
        """Limpa a seleção e redesenha."""
        self._selected = None
        self._draw()

    def set_device_status(self, device_id: str, status: str) -> None:
        """Atualiza o status de um dispositivo (evento SDN) e redesenha."""
        node = self._device_map.get(device_id)
        if node is None:
            log.warning("set_device_status: device %s nao encontrado no canvas", device_id)
            return
        node.status = status
        self._draw()

    # ── Drawing ─────────────────────────────────────────────────────

    def _draw(self) -> None:
        """Redesenha todo o canvas: barra SDN + nós Device."""
        self._scene.clear()
        self._device_map = {v.id: v for v in self._devices}

        # Atualiza cor de fundo (pode ter mudado com o tema)
        self._scene.setBackgroundBrush(QBrush(QColor(C.BG_BASE)))

        if not self._devices:
            self._draw_empty_state()
            return

        positions = self._layout()
        vw = self._view.viewport().width()
        vh = self._view.viewport().height()
        draw_background_grid(self._scene, vw, vh)
        draw_sdn_bar(self._scene, vw, len(self._devices))
        for device in self._devices:
            x, y = positions.get(device.id, (0, 0))
            self._draw_device_node(device, x, y)

    def _layout(self) -> dict[str, tuple[float, float]]:
        """Calcula posições dos nós Device em grade adaptativa (máx. 4 colunas)."""
        positions: dict[str, tuple[float, float]] = {}
        n = len(self._devices)
        if n == 0:
            return positions

        w = self._view.viewport().width() or 800
        vh = self._view.viewport().height() or 400
        pad_x, pad_y = 24, 24
        cols = max(1, min(4, (w - pad_x) // (self.NODE_W + pad_x)))
        grid_w = cols * self.NODE_W + (cols - 1) * pad_x
        start_x = (w - grid_w) / 2 + self.NODE_W / 2
        start_y = 100  # 8 px abaixo da SDN bar (bar_y=0 + bar_h=40 + gap=8 + nh/2=35)

        for i, device in enumerate(self._devices):
            col = i % cols
            row = i // cols
            x = start_x + col * (self.NODE_W + pad_x)
            y = start_y + row * (self.NODE_H + pad_y)
            positions[device.id] = (x, y)

        # Define scene rect para cobrir todos os itens
        max_y = start_y + (n // cols) * (self.NODE_H + pad_y) + self.NODE_H + 40
        self._scene.setSceneRect(0, 0, w, max(float(max_y), float(vh)))

        return positions

    def _draw_empty_state(self) -> None:
        """Desenha mensagem de estado vazio."""
        w = self._view.viewport().width() or 800
        h = self._view.viewport().height() or 400
        self._scene.setSceneRect(0, 0, w, h)

        txt = QGraphicsSimpleTextItem(
            "Nenhum dispositivo cadastrado.\n"
            "Clique em 'Cadastrar Dispositivo' para adicionar."
        )
        txt.setBrush(QBrush(QColor(C.FG_DIM)))
        txt.setFont(_to_qfont(C.FONT_LARGE))
        br = txt.boundingRect()
        txt.setPos(w / 2 - br.width() / 2, h / 2 - br.height() / 2)
        self._scene.addItem(txt)

    def _draw_device_node(self, device: Device, x: float, y: float) -> None:
        """Desenha um nó Device com sombra, glow de seleção, pulse de status."""
        nw, nh = self.NODE_W, self.NODE_H
        is_selected = (self._selected is not None
                       and self._selected.id == device.id)
        admin = role_meets(self._access_level, "tecnico")

        type_color_str = _color_for(device)
        st_color_str = _status_color(device, type_color_str)
        st_color_q = QColor(st_color_str)

        border_w = 3 if is_selected else 2
        fill_col = QColor(C.BG_INPUT) if is_selected else QColor(C.BG_CARD)
        hover_fill = QColor(C.BG_INPUT)

        # ── Anel de seleção + glow ─────────────────────────────────
        if is_selected:
            glow_sel = QGraphicsRectItem(
                x - nw / 2 - 11, y - nh / 2 - 11,
                nw + 22, nh + 22,
            )
            glow_sel.setPen(QPen(QColor(st_color_str), 6))
            glow_sel.setBrush(Qt.BrushStyle.NoBrush)
            glow_sel.setOpacity(0.12)
            glow_sel.setData(ITEM_DATA_KEY, device.id)
            self._scene.addItem(glow_sel)

            sel = QGraphicsRectItem(
                x - nw / 2 - 8, y - nh / 2 - 8,
                nw + 16, nh + 16,
            )
            sel.setPen(QPen(st_color_q, 1.5, Qt.PenStyle.DashDotDotLine))
            sel.setBrush(Qt.BrushStyle.NoBrush)
            sel.setData(ITEM_DATA_KEY, device.id)
            self._scene.addItem(sel)

        # ── Rect principal com sombra ───────────────────────────────
        rect = _DeviceNodeRect(
            x - nw / 2, y - nh / 2, nw, nh,
            device, self,
            QBrush(fill_col), QBrush(hover_fill),
        )
        normal_pen = QPen(st_color_q, border_w)
        hover_pen = QPen(st_color_q.lighter(130), border_w + 1)
        rect.set_pen_pair(normal_pen, hover_pen)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(2, 3)
        shadow.setColor(QColor(0, 0, 0, 60))
        rect.setGraphicsEffect(shadow)
        self._scene.addItem(rect)

        # Tooltip
        rect.setToolTip(_build_tooltip_text(device, show_admin_info=admin))

        # ── Status dot — pulse ──────────────────────────────────────
        glow_dot = QGraphicsEllipseItem(
            x - nw / 2 + 2, y - nh / 2 + 2, 14, 14,
        )
        glow_dot.setBrush(QBrush(st_color_q))
        glow_dot.setPen(Qt.PenStyle.NoPen)
        glow_dot.setOpacity(0.30)
        glow_dot.setData(ITEM_DATA_KEY, device.id)
        self._scene.addItem(glow_dot)

        dot = QGraphicsEllipseItem(x - nw / 2 + 4, y - nh / 2 + 4, 10, 10)
        dot.setBrush(QBrush(st_color_q))
        dot.setPen(Qt.PenStyle.NoPen)
        dot.setData(ITEM_DATA_KEY, device.id)
        self._scene.addItem(dot)

        # ── Nome ────────────────────────────────────────────────────
        name_item = QGraphicsSimpleTextItem(device.label())
        name_item.setBrush(QBrush(st_color_q))
        name_item.setFont(_to_qfont(C.FONT_MEDIUM_B))
        name_rect = name_item.boundingRect()
        name_item.setPos(x - name_rect.width() / 2, y - 18 - name_rect.height() / 2)
        name_item.setData(ITEM_DATA_KEY, device.id)
        self._scene.addItem(name_item)

        # ── Endereço ────────────────────────────────────────────────
        addr = device.host if not admin else device.address()
        addr_item = QGraphicsSimpleTextItem(addr)
        addr_item.setBrush(QBrush(QColor(C.FG_DIM)))
        addr_item.setFont(_to_qfont(C.FONT_CANVAS_BODY))
        address_rect = addr_item.boundingRect()
        addr_item.setPos(x - address_rect.width() / 2, y + 2 - address_rect.height() / 2)
        addr_item.setData(ITEM_DATA_KEY, device.id)
        self._scene.addItem(addr_item)

        # ── Label de tipo ───────────────────────────────────────────
        type_label = device.type.replace("-", "\n")
        type_item = QGraphicsSimpleTextItem(type_label)
        type_item.setBrush(QBrush(QColor(type_color_str)))
        type_item.setFont(_to_qfont(C.FONT_XSMALL))
        type_rect = type_item.boundingRect()
        type_item.setPos(
            x + nw / 2 - 8 - type_rect.width(),
            y + nh / 2 - 8 - type_rect.height(),
        )
        type_item.setData(ITEM_DATA_KEY, device.id)
        self._scene.addItem(type_item)

    # ── Event handlers ───────────────────────────────────────────────

    def _on_click(self, device: Device) -> None:
        """Seleciona o Device e chama o callback on_select."""
        self._selected = device
        try:
            if self._on_select:
                self._on_select(device)
        except Exception:
            log.exception("_on_click: on_select falhou para %s", device.id)
        self._draw()

    def _on_hover_enter(self, device: Device) -> None:
        """Registra o Device sob o mouse (tooltip é nativo do Qt)."""
        self._last_hover_device_id = device.id

    def _on_hover_leave(self) -> None:
        """Limpa o registro de hover."""
        self._last_hover_device_id = None

    def _on_context_menu(self, event, device: Device) -> None:
        """Exibe menu de contexto com editar/excluir (admin/tecnico)."""
        can_edit = role_meets(self._access_level, "tecnico")
        if not can_edit:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C.BG_INPUT}; color: {C.FG_MAIN};
                border: 1px solid {C.BORDER_NRM};
                font: 11px 'Inter';
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background: {C.NEON_PURP}; color: {C.BG_BASE};
            }}
        """)
        edit_action = menu.addAction("\u270f\ufe0f  Editar Dispositivo")
        delete_action = menu.addAction("\ud83d\uddd1  Excluir Dispositivo")

        # Converte coordenadas do evento para global
        if hasattr(event, "globalPos"):
            gpos = event.globalPos()
        elif hasattr(event, "screenPos"):
            gpos = event.screenPos().toPoint()
        else:
            gpos = self.mapToGlobal(self._view.mapFromScene(
                event.scenePos() if hasattr(event, "scenePos") else QPoint(0, 0)))

        action = menu.exec(gpos)
        if action == edit_action and self._edit_cb:
            self._edit_cb(device)
        elif action == delete_action and self._delete_cb:
            self._delete_cb(device)
