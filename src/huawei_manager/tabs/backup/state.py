"""Estado privado da aba Backup (F2-backup)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLabel, QLineEdit, QTextEdit


@dataclass
class BackupState:
    """Widgets e caminho de destino — o App nunca lê estes campos.

    ``backup_path`` é resetado a cada build (paridade com o mixin legado,
    que recriava o QLineEdit apontando para ``~`` a cada visita).
    """

    out: QTextEdit | None = None
    backup_entry: QLineEdit | None = None
    fmt_lbl: QLabel | None = None
    backup_path: str = ""
