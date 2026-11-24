"""Estado privado da aba Tabela ARP (F2-arp)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit


@dataclass
class ArpState:
    """Widgets da aba — o App nunca lê estes campos."""

    out: QTextEdit | None = None
