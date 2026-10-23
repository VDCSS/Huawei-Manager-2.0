"""Estado privado da aba Info do Sistema (F2-info)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit


@dataclass
class InfoState:
    """Widgets da aba — o App nunca lê estes campos."""

    out: QTextEdit | None = None
