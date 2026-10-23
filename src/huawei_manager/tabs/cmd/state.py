"""Estado privado da aba Editor de Comandos (F2-cmd)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QListWidget, QTextEdit


@dataclass
class CmdState:
    """Widgets e flags da aba — o App nunca lê estes campos.

    ``sysview_var`` é resetado a cada build (paridade com o mixin legado,
    que recriava o QCheckBox zerado a cada visita).
    """

    editor: QTextEdit | None = None
    out: QTextEdit | None = None
    tpl_listbox: QListWidget | None = None
    tpl_cmd_map: dict[str, str] = field(default_factory=dict[str, str])
    sysview_var: bool = False
