#!/usr/bin/env python3
"""Page builders (PySide6) — all _build_*_page methods."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.topology import TopologyCanvas
from huawei_manager.widgets.elide_label import ElideLabel
from huawei_manager.widgets.neon_button import action_button


class PageBuilder:
    """Mixin com métodos de construção das páginas da interface PySide6."""

    # ── Helpers ────────────────────────────────────────────────────────

    def _make_page(self: AppCoreProtocol, key: str) -> QWidget:
        """Cria uma QWidget page e a adiciona ao _page_container (se existir)."""
        p = QWidget()
        p.setObjectName(f"page_{key}")
        layout = QVBoxLayout(p)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(0)
        if self._page_container is not None:
            from PySide6.QtWidgets import QStackedWidget

            if isinstance(self._page_container, QStackedWidget):
                self._page_container.addWidget(p)
            elif self._page_container.layout() is not None:
                self._page_container.layout().addWidget(p)
        return p

    def _page_layout(self, p: QWidget) -> QVBoxLayout:
        layout = p.layout()
        if not isinstance(layout, QVBoxLayout):
            raise TypeError("page layout must be a QVBoxLayout")
        return layout

    def _page_title(self, parent: QWidget, title: str, color: str, subtitle: str = "") -> None:
        layout = self._page_layout(parent)
        lbl = QLabel(title, parent)
        lbl.setStyleSheet(f"color: {color}; font: bold {C.FONT_TITLE}px {C.FONT_UI_FAMILY}; padding: 0px; margin: 0px;")
        layout.addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle, parent)
            sub.setStyleSheet(f"color: {C.FG_DIM}; font: {C.FONT_SUBHEAD}px {C.FONT_UI_FAMILY}; padding: 0px;")
            layout.addWidget(sub)
        layout.addSpacing(8)

    def _css_label(self, color: str, bg: str = "", font_size: int = 12, bold: bool = False) -> str:
        weight = "bold" if bold else "normal"
        bg_css = f"background: {bg};" if bg else ""
        return f"color: {color}; {bg_css} font: {weight} {font_size}px {C.FONT_UI_FAMILY};"

    # ── Topology ──────────────────────────────────────────────────────
    def _build_topology_page(self: AppCoreProtocol) -> None:
        p = self._make_page("topology")
        self._page_title(p, "Topologia / Devices", C.NEON_AMBER,
                         "Cadastro manual + alvo SSH clicavel")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(ctrl)

        admin_label = "\U0001f512  Acesso"
        if role_meets(self._access_level, "tecnico"):
            admin_label = "\U0001f513  Sair (Admin)" if self._access_level == "admin" else "\U0001f6e0  Sair (Tecnico)"
        self._admin_btn = action_button(ctrl, admin_label,
                                        self._show_auth_dialog, C.NEON_PURP)
        ctrl_layout.addWidget(self._admin_btn)
        ctrl_layout.addSpacing(8)

        if role_meets(self._access_level, "tecnico"):
            cad_btn = action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                                    lambda: self._show_device_dialog(), C.NEON_CYAN)
            ctrl_layout.addWidget(cad_btn)
            ctrl_layout.addSpacing(8)

        btn_refresh = action_button(ctrl, "\u21bb  Atualizar",
                                    lambda: self._spawn_io(self._refresh_devices),
                                    C.NEON_AMBER)
        ctrl_layout.addWidget(btn_refresh)
        ctrl_layout.addSpacing(8)
        btn_back = action_button(ctrl, "\u2716  Voltar",
                                 self._clear_device_target, C.NEON_PURP)
        ctrl_layout.addWidget(btn_back)

        ctrl_layout.addStretch()

        self._device_info_lbl = ElideLabel("  Nenhum device selecionado", ctrl)
        self._device_info_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        self._device_info_lbl.setMinimumWidth(220)
        ctrl_layout.addWidget(self._device_info_lbl)
        ctrl_layout.addSpacing(8)

        self._topo_canvas = TopologyCanvas(
            p,
            on_select=self._on_device_selected,
            on_edit=self._show_device_dialog,
            on_delete=self._delete_device,
        )
        self._page_layout(p).addWidget(self._topo_canvas, stretch=1)

        self._device_status_lbl = QLabel("Invent\u00e1rio: 0 devices", p)
        self._device_status_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_CARD, 10))
        self._page_layout(p).addWidget(self._device_status_lbl)
        self._page_layout(p).addSpacing(4)

        self._spawn_io(self._refresh_devices)

