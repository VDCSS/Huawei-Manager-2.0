"""Estado privado da aba Serviços (F2-services)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLineEdit

from huawei_manager.services import ServiceDef

if TYPE_CHECKING:
    from PySide6.QtWidgets import QComboBox, QLabel, QListWidget, QTextEdit, QWidget


@dataclass
class ServicesState:
    """Widgets/estado da aba — o App nunca lê estes campos."""

    output: QTextEdit | None = None
    device_lbl: QLabel | None = None
    type_lbl: QLabel | None = None
    status_lbl: QLabel | None = None
    cat_var: str = "Todas as Categorias"
    cat_cb: QComboBox | None = None
    listbox: QListWidget | None = None
    detail_frame: QWidget | None = None
    param_entries: dict[str, QLineEdit] = field(default_factory=dict[str, QLineEdit])
    services: list[ServiceDef] = field(default_factory=list[ServiceDef])
    current_svc: ServiceDef | None = None
