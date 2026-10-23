"""Estado privado da aba Roteamento (F2-route)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QComboBox, QTextEdit


@dataclass
class RouteState:
    """Widgets e flags da aba — o App nunca lê estes campos."""

    out: QTextEdit | None = None
    filter_cb: QComboBox | None = None
    filter_var: str = ""
