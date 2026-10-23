"""Aba Topologia / Devices — módulo TabModule (F2-topology).

Migrado de ``pages/builder.py`` (``_build_topology_page``): os widgets
(canvas, labels, botões) vivem no estado do módulo; a orquestração de
inventário (DevicesMixin) permanece no App e entra aqui via ``TabContext``
(callbacks) — a aba nunca vê o ``App``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

import huawei_manager.constants as C
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.tabs import _ui
from huawei_manager.topology import TopologyCanvas
from huawei_manager.widgets.elide_label import ElideLabel
from huawei_manager.widgets.neon_button import action_button

from .state import TopologyState

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext


class TopologyTab:
    """Módulo da aba Topologia (TabModule)."""

    def __init__(self) -> None:
        self.state = TopologyState()
        self._ctx: TabContext | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas."""
        if self._ctx is None:
            self._ctx = ctx

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página Topologia / Devices (verbatim do builder legado)."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("topology")
        _ui.page_title(p, "Topologia / Devices", C.NEON_AMBER,
                       "Cadastro manual + alvo SSH clicavel")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        _ui.page_layout(p).addWidget(ctrl)

        access = ctx.role()
        admin_label = "\U0001f512  Acesso"
        if role_meets(access, "tecnico"):
            admin_label = ("\U0001f513  Sair (Admin)" if access == "admin"
                           else "\U0001f6e0  Sair (Tecnico)")
        admin_btn = action_button(ctrl, admin_label,
                                  ctx.show_auth_dialog, C.NEON_PURP)
        state.admin_btn = admin_btn
        ctrl_layout.addWidget(admin_btn)
        ctrl_layout.addSpacing(8)

        if role_meets(access, "tecnico"):
            cad_btn = action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                                    lambda: ctx.show_device_dialog(),
                                    C.NEON_CYAN)
            ctrl_layout.addWidget(cad_btn)
            ctrl_layout.addSpacing(8)

        btn_refresh = action_button(ctrl, "\u21bb  Atualizar",
                                    lambda: ctx.spawn_io(ctx.refresh_devices),
                                    C.NEON_AMBER)
        ctrl_layout.addWidget(btn_refresh)
        ctrl_layout.addSpacing(8)
        btn_back = action_button(ctrl, "\u2716  Voltar",
                                 ctx.clear_device_target, C.NEON_PURP)
        ctrl_layout.addWidget(btn_back)

        ctrl_layout.addStretch()

        info_lbl = ElideLabel("  Nenhum device selecionado", ctrl)
        info_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        info_lbl.setMinimumWidth(220)
        state.device_info_lbl = info_lbl
        ctrl_layout.addWidget(info_lbl)
        ctrl_layout.addSpacing(8)

        canvas = TopologyCanvas(
            p,
            on_select=ctx.on_device_selected,
            on_edit=ctx.show_device_dialog,
            on_delete=ctx.delete_device,
        )
        state.topo_canvas = canvas
        _ui.page_layout(p).addWidget(canvas, stretch=1)

        status_lbl = QLabel("Inventário: 0 devices", p)
        status_lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_CARD, 10))
        state.device_status_lbl = status_lbl
        _ui.page_layout(p).addWidget(status_lbl)
        _ui.page_layout(p).addSpacing(4)

        ctx.spawn_io(ctx.refresh_devices)
        return p

    def dispose(self) -> None:
        """Zera as refs de widgets (rebuild da aba)."""
        self.state.topo_canvas = None
        self.state.device_info_lbl = None
        self.state.device_status_lbl = None
        self.state.admin_btn = None
        self._ctx = None
