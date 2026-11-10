"""Estado privado da aba Topologia (F2-topology)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLabel

    from huawei_manager.topology import TopologyCanvas
    from huawei_manager.widgets.elide_label import ElideLabel
    from huawei_manager.widgets.neon_button import ActionButton


@dataclass
class TopologyState:
    """Widgets da aba — o App lê via fachadas (_topo_canvas_widget etc.)."""

    topo_canvas: TopologyCanvas | None = None
    device_info_lbl: ElideLabel | None = None
    device_status_lbl: QLabel | None = None
    admin_btn: ActionButton | None = None
