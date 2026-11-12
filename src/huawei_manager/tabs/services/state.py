"""Estado privado da aba Serviços (F2-services)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLineEdit

from huawei_manager.services import ServiceDef

if TYPE_CHECKING:
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QListWidget, QTextEdit, QWidget

    from huawei_manager.basic_config.vrp_version import VrpVersion
    from huawei_manager.tabs.services.form_widgets import FormWidget


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

    # ── Formulários compostos (ACL, rota estática) ──────────────────
    #: Widget do formulário selecionado (``form_kind`` do serviço).
    form_state: FormWidget | None = None
    #: Persistência na startup-config — desmarcado por padrão.
    save_chk: QCheckBox | None = None
    #: Versão VRP detectada (cache por host, evita round-trip por serviço).
    vrp_version: VrpVersion | None = None
    vrp_host: str | None = None
