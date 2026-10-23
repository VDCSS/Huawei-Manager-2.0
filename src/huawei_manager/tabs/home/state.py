"""Estado privado da aba Dashboard/Home (F2-home)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLabel, QTextEdit


@dataclass
class HomeState:
    """Widgets da aba — o App nunca lê estes campos."""

    conn_status: QLabel | None = None
    conn_host: QLabel | None = None
    device_online: QLabel | None = None
    device_offline: QLabel | None = None
    device_unknown: QLabel | None = None
    audit_text: QTextEdit | None = None
    shortcut_btns: dict[str, str] = field(default_factory=dict[str, str])
