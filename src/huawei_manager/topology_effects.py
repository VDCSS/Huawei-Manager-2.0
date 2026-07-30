"""
topology_effects.py — Visual effect helpers for TopologyCanvas.
==============================================================
Standalone drawing functions extracted from topology.py:
SDN bar with glow/gradient/accent.
Theme-aware via ``huawei_manager.constants`` module-level colors.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

import huawei_manager.constants as C
from huawei_manager.topology_items import _to_qfont


def draw_background_grid(
    scene: QGraphicsScene,
    view_width: int,
    view_height: int,
) -> None:
    """Draw subtle tech-grid lines covering the full viewport (z=-100).

    Auto-redimensiona com o canvas porque usa viewport width/height, não scene rect.
    """
    c = QColor(C.BORDER_NRM)
    c.setAlpha(40)
    pen = QPen(c, 1)
    spacing = 40.0

    x = 0.0
    while x <= view_width:
        scene.addLine(x, 0.0, x, view_height, pen).setZValue(-100)
        x += spacing

    y = 0.0
    while y <= view_height:
        scene.addLine(0.0, y, view_width, y, pen).setZValue(-100)
        y += spacing


def draw_sdn_bar(scene: QGraphicsScene, view_width: int, vnf_count: int) -> None:
    """Draw the SDN controller bar with glow, gradient, accent, and device counter.

    Parameters
    ----------
    scene : QGraphicsScene
        The scene to draw into.
    view_width : int
        Width of the viewport (used to centre the bar).
    vnf_count : int
        Number of managed VNFs shown in the counter label.
    """
    cw = view_width
    bar_w = max(cw - 40, 200)
    bar_h = 40
    bar_x = (cw - bar_w) / 2
    bar_y = 12

    # ── Glow externo ───────────────────────────────────────────────
    glow = QGraphicsRectItem(bar_x - 6, bar_y - 6, bar_w + 12, bar_h + 12)
    glow_color = QColor(C.NEON_PURP)
    glow_color.setAlpha(30)
    glow.setBrush(QBrush(glow_color))
    glow.setPen(Qt.PenStyle.NoPen)
    scene.addItem(glow)

    # ── Fundo com gradiente ────────────────────────────────────────
    bg_rect = QGraphicsRectItem(bar_x, bar_y, bar_w, bar_h)
    gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_h)
    gradient.setColorAt(0.0, QColor(C.NEON_PURP).darker(160))
    gradient.setColorAt(0.35, QColor(C.BG_INPUT))
    gradient.setColorAt(1.0, QColor(C.BG_INPUT))
    bg_rect.setBrush(QBrush(gradient))
    bg_rect.setPen(QPen(QColor(C.NEON_PURP), 1))
    scene.addItem(bg_rect)

    # ── Linha decorativa (accent) na base ──────────────────────────
    accent_path = QPainterPath()
    accent_path.moveTo(bar_x + 12, bar_y + bar_h - 2)
    accent_path.lineTo(bar_x + bar_w - 12, bar_y + bar_h - 2)
    accent_line = QGraphicsPathItem(accent_path)
    accent_line.setPen(QPen(QColor(C.NEON_PURP), 1))
    accent_line.setOpacity(0.5)
    scene.addItem(accent_line)

    # ── Símbolo ⬡ ─────────────────────────────────────────────────
    symbol_text = QGraphicsSimpleTextItem("\u2b61")
    symbol_text.setBrush(QBrush(QColor(C.NEON_PURP)))
    symbol_text.setFont(_to_qfont(C.FONT_H1))
    symbol_rect = symbol_text.boundingRect()
    symbol_text.setPos(bar_x + 20, bar_y + bar_h / 2 - symbol_rect.height() / 2)
    scene.addItem(symbol_text)

    # ── Label ──────────────────────────────────────────────────────
    title_text = QGraphicsSimpleTextItem("SDN CONTROLLER")
    title_text.setBrush(QBrush(QColor(C.NEON_PURP)))
    title_text.setFont(_to_qfont(C.FONT_LARGE_B))
    title_rect = title_text.boundingRect()
    title_text.setPos(bar_x + 44, bar_y + bar_h / 2 - title_rect.height() / 2)
    scene.addItem(title_text)

    # ── Contador ───────────────────────────────────────────────────
    counter_text = QGraphicsSimpleTextItem(
        f"{vnf_count} dispositivo(s) gerenciado(s)",
    )
    counter_text.setBrush(QBrush(QColor(C.FG_DIM)))
    counter_text.setFont(_to_qfont(C.FONT_BODY))
    counter_rect = counter_text.boundingRect()
    counter_text.setPos(
        bar_x + bar_w - 20 - counter_rect.width(),
        bar_y + bar_h / 2 - counter_rect.height() / 2,
    )
    scene.addItem(counter_text)
