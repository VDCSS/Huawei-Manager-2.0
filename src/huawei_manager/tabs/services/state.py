"""Estado privado da aba Serviços (F2-services)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QWidget,
)

from huawei_manager.services import ServiceDef

if TYPE_CHECKING:
    from huawei_manager.basic_config.vrp_version import VrpVersion
    from huawei_manager.command import ConfigCommand
    from huawei_manager.tabs.services.form_widgets import FormWidget


@dataclass
class ServicesState:
    """Widgets/estado da aba — o App nunca lê destes campos."""

    output: QTextEdit | None = None
    device_lbl: QLabel | None = None
    type_lbl: QLabel | None = None
    status_lbl: QLabel | None = None
    cat_var: str = "Todas as Categorias"
    cat_cb: QComboBox | None = None
    listbox: QListWidget | None = None
    #: Painel esquerdo (barra de serviços). Quando recolhido vira um trilho.
    left_panel: QWidget | None = None
    #: Cabeçalho da barra esquerda (com o botão de toggle).
    list_header: QLabel | None = None
    #: Botão de toggle ([MENU]) mostrado no trilho recolhido.
    list_toggle: QPushButton | None = None
    #: Se a barra esquerda está aberta.
    list_open: bool = True
    #: Se o usuário reabriu manualmente (não recua sozinho na próxima seleção).
    list_pinned: bool = False
    #: QScrollArea que envolve o detail_frame (para rolagem do formulário).
    detail_scroll: QScrollArea | None = None
    detail_frame: QWidget | None = None
    #: Botões pré-definidos no cabeçalho do detalhe da ACL
    #: ("Bloquear Internet" / "Bloquear site"). Só existem quando o
    #: serviço selecionado tem ``form_kind == "acl"``; ficam no conteúdo
    #: rolável (linha do título), não na barra fixa.
    block_internet_btn: QPushButton | None = None
    block_site_btn: QPushButton | None = None
    #: Container fixo da barra de ações (botões EXCUTAR / PRÉ-VISUALIZAR /
    #: CONSULTAR / REVERTER / Salvar / Limpar output). Fica fora do
    #: QScrollArea, presa no rodapé da coluna direita, acima do output.
    action_bar: QWidget | None = None
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

    #: Último comando de configuração aplicado **nesta aba** (com snapshot)
    #: — alvo do botão "Reverter (rollback)" da aba Serviços.
    #:
    #: Deliberadamente **privado da aba**: o rollback de Serviços desfaz
    #: apenas o que foi aplicado aqui, sem tocar na Config Básica (cada aba
    #: mantém o seu próprio alvo de rollback).
    last_config_command: ConfigCommand | None = None
