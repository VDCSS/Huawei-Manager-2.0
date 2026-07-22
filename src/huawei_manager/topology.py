"""
topology.py — VNF Topology + Canvas (PySide6)
==============================================
Gerenciamento de VNFs via inventário local (vnf_inventory.json),
probe TCP real e simulação de status (modo mock).
Canvas baseado em QGraphicsView / QGraphicsScene.

O VNF selecionado no canvas é usado como alvo para conexão SSH via Netmiko.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
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
from huawei_manager.topology_items import (
    ITEM_DATA_KEY,
    _build_tooltip_text,
    _color_for,
    _status_color,
    _to_qfont,
)
from huawei_manager.topology_nodes import _VNFNodeRect
from huawei_manager.vnf_models import VNF

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
            vnf_id = item.data(ITEM_DATA_KEY)
            if vnf_id is not None and vnf_id in self._canvas._vnf_map:
                self._canvas._on_context_menu(event, self._canvas._vnf_map[vnf_id])
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

    Renderiza VNFs num grid de 4 colunas com barra SDN no topo.
    Suporta seleção, tooltip, menu de contexto e destaque hover.
    """

    NODE_W, NODE_H = 180, 70

    def __init__(
        self,
        parent: QWidget | None = None,
        on_select: Callable[[VNF], None] | None = None,
        on_edit:   Callable[[VNF], None] | None = None,
        on_delete: Callable[[VNF], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._edit_cb = on_edit
        self._delete_cb = on_delete
        self._vnfs: list[VNF] = []
        self._selected: VNF | None = None
        self._access_level: str = "user"
        self._vnf_map: dict[str, VNF] = {}
        self._last_hover_vnf_id: str | None = None

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
        self._view.setMouseTracking(True)
        layout.addWidget(self._view)

    # ── Interface pública ───────────────────────────────────────────

    def set_access(self, level: str) -> None:
        """Define o nível de acesso (user / admin / tecnico)."""
        self._access_level = level
        # tooltip text depende do nível → redesenha
        self._draw()

    def update_vnfs(self, vnfs: list[VNF]) -> None:
        """Atualiza a lista de VNFs e redesenha."""
        self._vnfs = vnfs
        self._vnf_map = {v.id: v for v in vnfs}
        self._draw()

    def get_selected(self) -> VNF | None:
        """Retorna o VNF atualmente selecionado ou None."""
        return self._selected

    def deselect(self) -> None:
        """Limpa a seleção e redesenha."""
        self._selected = None
        self._draw()

    # ── Drawing ─────────────────────────────────────────────────────

    def _draw(self) -> None:
        """Redesenha todo o canvas: barra SDN + nós VNF."""
        self._scene.clear()
        self._vnf_map = {v.id: v for v in self._vnfs}

        # Atualiza cor de fundo (pode ter mudado com o tema)
        self._scene.setBackgroundBrush(QBrush(QColor(C.BG_BASE)))

        if not self._vnfs:
            self._draw_empty_state()
            return

        positions = self._layout()

        self._draw_sdn_bar()
        for vnf in self._vnfs:
            x, y = positions.get(vnf.id, (0, 0))
            self._draw_vnf_node(vnf, x, y)

    def _layout(self) -> dict[str, tuple[float, float]]:
        """Calcula posições dos nós VNF em grid de 4 colunas."""
        positions: dict[str, tuple[float, float]] = {}
        n = len(self._vnfs)
        if n == 0:
            return positions

        w = self._view.viewport().width() or 800
        cols = 4
        pad_x, pad_y = 24, 24
        grid_w = cols * self.NODE_W + (cols - 1) * pad_x
        start_x = (w - grid_w) / 2 + self.NODE_W / 2
        start_y = 100  # abaixo da SDN bar

        for i, vnf in enumerate(self._vnfs):
            col = i % cols
            row = i // cols
            x = start_x + col * (self.NODE_W + pad_x)
            y = start_y + row * (self.NODE_H + pad_y)
            positions[vnf.id] = (x, y)

        # Define scene rect para cobrir todos os itens
        max_y = start_y + (n // cols) * (self.NODE_H + pad_y) + self.NODE_H + 40
        self._scene.setSceneRect(0, 0, max(w, 800), max(float(max_y), 400.0))

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

    def _draw_sdn_bar(self) -> None:
        """Desenha a barra SDN com contador de dispositivos."""
        cw = self._view.viewport().width() or 800
        bar_w = max(cw - 40, 200)
        bar_h = 40
        bar_x = (cw - bar_w) / 2
        bar_y = 16

        # Fundo
        bg_rect = QGraphicsRectItem(bar_x, bar_y, bar_w, bar_h)
        bg_rect.setBrush(QBrush(QColor(C.BG_INPUT)))
        bg_rect.setPen(QPen(QColor(C.NEON_PURP), 2))
        self._scene.addItem(bg_rect)

        # Símbolo
        symbol_text = QGraphicsSimpleTextItem("\u2b61")  # ⬡
        symbol_text.setBrush(QBrush(QColor(C.NEON_PURP)))
        symbol_text.setFont(_to_qfont(C.FONT_H1))
        symbol_rect = symbol_text.boundingRect()
        symbol_text.setPos(bar_x + 20, bar_y + bar_h / 2 - symbol_rect.height() / 2)
        self._scene.addItem(symbol_text)

        # Label
        title_text = QGraphicsSimpleTextItem("SDN CONTROLLER")
        title_text.setBrush(QBrush(QColor(C.NEON_PURP)))
        title_text.setFont(_to_qfont(C.FONT_LARGE_B))
        title_rect = title_text.boundingRect()
        title_text.setPos(bar_x + 44, bar_y + bar_h / 2 - title_rect.height() / 2)
        self._scene.addItem(title_text)

        # Contador
        counter_text = QGraphicsSimpleTextItem(
            f"{len(self._vnfs)} dispositivo(s) gerenciado(s)")
        counter_text.setBrush(QBrush(QColor(C.FG_DIM)))
        counter_text.setFont(_to_qfont(C.FONT_BODY))
        counter_rect = counter_text.boundingRect()
        counter_text.setPos(bar_x + bar_w - 20 - counter_rect.width(),
                            bar_y + bar_h / 2 - counter_rect.height() / 2)
        self._scene.addItem(counter_text)

    def _draw_vnf_node(self, vnf: VNF, x: float, y: float) -> None:
        """Desenha um nó VNF no scene com cor, status e tooltip."""
        nw, nh = self.NODE_W, self.NODE_H
        is_selected = (self._selected is not None
                       and self._selected.id == vnf.id)
        admin = self._access_level in ("admin", "tecnico")

        type_color_str = _color_for(vnf)
        st_color_str = _status_color(vnf, type_color_str)
        st_color_q = QColor(st_color_str)

        border_w = 2
        fill_col = QColor(C.BG_CARD)
        hover_fill = QColor(C.BG_INPUT)

        if is_selected:
            # Anel de seleção (tracejado)
            sel = QGraphicsRectItem(
                x - nw / 2 - 6, y - nh / 2 - 6,
                nw + 12, nh + 12,
            )
            sel.setPen(QPen(st_color_q, 1, Qt.PenStyle.DashLine))
            sel.setBrush(Qt.BrushStyle.NoBrush)
            sel.setData(ITEM_DATA_KEY, vnf.id)
            self._scene.addItem(sel)
            fill_col = QColor(C.BG_INPUT)
            border_w = 3

        # Rect principal (com hover)
        rect = _VNFNodeRect(
            x - nw / 2, y - nh / 2, nw, nh,
            vnf, self,
            QBrush(fill_col), QBrush(hover_fill),
        )
        rect.setPen(QPen(st_color_q, border_w))
        self._scene.addItem(rect)

        # Tooltip
        rect.setToolTip(_build_tooltip_text(vnf, show_admin_info=admin))

        # Status dot (canto superior esquerdo)
        dot = QGraphicsEllipseItem(x - nw / 2 + 4, y - nh / 2 + 4, 10, 10)
        dot.setBrush(QBrush(st_color_q))
        dot.setPen(Qt.PenStyle.NoPen)
        dot.setData(ITEM_DATA_KEY, vnf.id)
        self._scene.addItem(dot)

        # Nome (centro, acima do meio)
        name_item = QGraphicsSimpleTextItem(vnf.label())
        name_item.setBrush(QBrush(st_color_q))
        name_item.setFont(_to_qfont(C.FONT_MEDIUM_B))
        name_rect = name_item.boundingRect()
        name_item.setPos(x - name_rect.width() / 2, y - 18 - name_rect.height() / 2)
        name_item.setData(ITEM_DATA_KEY, vnf.id)
        self._scene.addItem(name_item)

        # Endereço (centro, abaixo do meio)
        addr = vnf.host if not admin else vnf.address()
        addr_item = QGraphicsSimpleTextItem(addr)
        addr_item.setBrush(QBrush(QColor(C.FG_DIM)))
        addr_item.setFont(_to_qfont(C.FONT_BODY))
        address_rect = addr_item.boundingRect()
        addr_item.setPos(x - address_rect.width() / 2, y + 2 - address_rect.height() / 2)
        addr_item.setData(ITEM_DATA_KEY, vnf.id)
        self._scene.addItem(addr_item)

        # Label de tipo (canto inferior direito)
        type_label = vnf.type.replace("-", "\n")
        type_item = QGraphicsSimpleTextItem(type_label)
        type_item.setBrush(QBrush(QColor(type_color_str)))
        type_item.setFont(_to_qfont(C.FONT_XSMALL))
        type_rect = type_item.boundingRect()
        type_item.setPos(
            x + nw / 2 - 8 - type_rect.width(),
            y + nh / 2 - 8 - type_rect.height(),
        )
        type_item.setData(ITEM_DATA_KEY, vnf.id)
        self._scene.addItem(type_item)

    # ── Event handlers ───────────────────────────────────────────────

    def _on_click(self, vnf: VNF) -> None:
        """Seleciona o VNF e chama o callback on_select."""
        self._selected = vnf
        self._draw()
        if self._on_select:
            self._on_select(vnf)

    def _on_hover_enter(self, vnf: VNF) -> None:
        """Registra o VNF sob o mouse (tooltip é nativo do Qt)."""
        self._last_hover_vnf_id = vnf.id

    def _on_hover_leave(self) -> None:
        """Limpa o registro de hover."""
        self._last_hover_vnf_id = None

    def _on_context_menu(self, event, vnf: VNF) -> None:
        """Exibe menu de contexto com editar/excluir (admin/tecnico)."""
        can_edit = self._access_level in ("admin", "tecnico")
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
            self._edit_cb(vnf)
        elif action == delete_action and self._delete_cb:
            self._delete_cb(vnf)
