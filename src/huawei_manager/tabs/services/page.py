"""Aba Serviços — módulo TabModule (F2-services).

Migrado de ``pages/services.py`` (``PageBuilderServicesMixin``): a
construção virou ``ServicesTab.build(ctx) -> QWidget`` e a execução vive
em :class:`ServicesHandlers`. Sub-builders e handlers de seleção ficam
como métodos privados desta aba (nunca veem o ``App``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.constants import SERVICE_CAT_LABELS
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.services import (
    DEVICE_TYPES,
    ServiceDef,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.services.form_registry import get_form_spec, render_form
from huawei_manager.tabs import _ui
from huawei_manager.tabs.services.form_widgets import FormWidget
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.state import ServicesState
from huawei_manager.widgets.icons import icon
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class ServicesTab:
    """Módulo da aba Serviços (TabModule)."""

    def __init__(self) -> None:
        self.state = ServicesState()
        self._ctx: TabContext | None = None
        self._handlers: ServicesHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas."""
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = ServicesHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página do Catálogo de Serviços."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("services")
        _ui.page_title(p, "Catálogo de Serviços", C.NEON_AMBER,
                       "Serviços de configuração por tipo de device "
                       "(ROUTER | SWITCH | …) — comandos show e consultas: "
                       "use o Editor de Comandos")

        self._build_info_row(p)
        self._build_filter_row(p)
        self._build_split(p)

        state.output = output_text(p)
        # Altura fixa ~12 linhas (DPI-independente) com scroll próprio.
        _line_h = state.output.fontMetrics().lineSpacing()
        state.output.setFixedHeight(_line_h * 12 + 12)
        _ui.page_layout(p).addWidget(state.output)
        _ui.page_layout(p).addSpacing(4)

        # Timer com "context": cancelado quando a página é destruída — evita
        # callbacks em widgets já deletados (o singleShot sem context mantém
        # a aba viva e dispara sobre C++ objects destruídos).
        QTimer.singleShot(500, p, self.refresh_service_list)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        state = self.state
        state.output = None
        state.device_lbl = None
        state.type_lbl = None
        state.status_lbl = None
        state.cat_var = "Todas as Categorias"
        state.cat_cb = None
        state.listbox = None
        state.detail_frame = None
        state.action_bar = None
        state.param_entries.clear()
        state.services.clear()
        state.current_svc = None
        state.form_state = None
        self.state.save_chk = None

    # ── Fachadas (usadas pelo shell: F5, Devices, Ctrl+L) ────────────
    def refresh_service_list(self) -> None:
        """Repovoa o listbox de serviços (fachada preserva o nome legado)."""
        ctx = self._ctx
        if ctx is None:
            return
        state = self.state
        listbox = state.listbox
        device_lbl = state.device_lbl
        type_lbl = state.type_lbl
        status_lbl = state.status_lbl
        cat_cb = state.cat_cb
        if (listbox is None or device_lbl is None or type_lbl is None
                or status_lbl is None or cat_cb is None):
            return
        listbox.clear()
        state.services.clear()

        device = ctx.device()
        if not device:
            device_lbl.setText("Device: (nenhum selecionado)")
            type_lbl.setText("Tipo: ")
            cat_cb.blockSignals(True)
            cat_cb.clear()
            cat_cb.addItems(["Todas as Categorias"])
            cat_cb.blockSignals(False)
            self._clear_detail_panel()
            return

        device_type = device.type.upper()
        host_info = (f"{device.host}:{device.port}"
                     if role_meets(ctx.role(), "tecnico") else device.host)
        device_lbl.setText(f"Device: {device.name} ({host_info})")
        type_lbl.setText(f"Tipo: {DEVICE_TYPES.get(device_type, device_type)}")

        status_color = {"online": C.NEON_CYAN, "offline": C.NEON_RED,
                        "unknown": C.NEON_AMBER}.get(device.status, C.NEON_AMBER)
        status_lbl.setText(f"Status: {device.status}")
        status_lbl.setStyleSheet(
            f"color: {status_color}; background: {C.rgba(status_color, 0.10)};"
            f" border: 1px solid {C.rgba(status_color, 0.32)}; border-radius: 8px;"
            f" padding: 3px 8px; font: 600 10px {C.FONT_UI_FAMILY};")

        all_cats = get_categories_for(device_type)
        config_cats = [c for c in all_cats if c.startswith("config-")]
        # Tipos sem serviços de configuração (ex.: FIREWALL, AP) passam a listar
        # as categorias de leitura, para não deixar a aba vazia.
        type_has_config = any(s.config_mode and s.visible
                              for s in get_services_for(device_type))
        cats = config_cats if type_has_config else all_cats
        cat_labels = [SERVICE_CAT_LABELS.get(c, c) for c in cats]
        all_labels = ["Todas as Categorias"] + cat_labels

        cat_cb.blockSignals(True)
        cat_cb.clear()
        cat_cb.addItems(all_labels)
        if state.cat_var in all_labels:
            cat_cb.setCurrentText(state.cat_var)
        else:
            cat_cb.setCurrentText("Todas as Categorias")
            state.cat_var = "Todas as Categorias"
        cat_cb.blockSignals(False)

        selected_cat = state.cat_var
        label_to_cat = dict(zip(cat_labels, cats))
        cat_filter = None if selected_cat == "Todas as Categorias" else label_to_cat.get(selected_cat)
        services = get_services_for(device_type, category=cat_filter)
        services = [s for s in services if s.visible]
        if type_has_config:
            services = [s for s in services if s.config_mode]
        state.services = services

        if not services:
            listbox.addItem("  Nenhum serviço disponível para este tipo de Device")
            self._clear_detail_panel()
            return

        for svc in services:
            item = QListWidgetItem(f"  {svc.name}")
            item.setIcon(icon(
                "i-settings" if svc.config_mode else "i-play",
                C.NEON_AMBER if svc.config_mode else C.NEON_CYAN, 16))
            listbox.addItem(item)

        # (opção (ii)) Não auto-selecionar: o painel começa vazio;
        # o usuário escolhe o serviço — e cada seleção recolhe a barra.

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída da aba)."""
        return self.state.output

    # ── Services: sub-builders ───────────────────────────────────────
    def _build_info_row(self, parent: QWidget) -> None:
        state = self.state
        info_row = QFrame(parent)
        info_row.setObjectName("servicesInfoBar")
        info_row.setStyleSheet(
            f"#servicesInfoBar {{ background: {C.BG_SURFACE_2};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        info_row.setMinimumHeight(44)
        info_layout = QHBoxLayout(info_row)
        info_layout.setContentsMargins(14, 6, 14, 6)
        info_layout.setSpacing(0)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(info_row)
        parent_layout.addSpacing(10)

        state.device_lbl = QLabel("Device: (selecione um device na aba Topologia)", info_row)
        state.device_lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, "", 12, True))
        info_layout.addWidget(state.device_lbl)
        info_layout.addSpacing(18)

        state.type_lbl = QLabel("Tipo: ", info_row)
        state.type_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, "", 11))
        info_layout.addWidget(state.type_lbl)
        info_layout.addSpacing(18)

        state.status_lbl = QLabel("", info_row)
        state.status_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, "", 10, True))
        info_layout.addWidget(state.status_lbl)
        info_layout.addStretch()

    def _build_filter_row(self, parent: QWidget) -> None:
        state = self.state
        filt_row = QWidget(parent)
        filt_row.setStyleSheet("background: transparent;")
        filt_row.setMaximumHeight(40)
        filt_layout = QHBoxLayout(filt_row)
        filt_layout.setContentsMargins(2, 0, 0, 0)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(filt_row)
        parent_layout.addSpacing(8)

        cat_lbl = QLabel("Categoria:", filt_row)
        cat_lbl.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 11, True))
        filt_layout.addWidget(cat_lbl)
        filt_layout.addSpacing(8)

        state.cat_var = "Todas as Categorias"
        state.cat_cb = QComboBox(filt_row)
        state.cat_cb.setEditable(False)
        state.cat_cb.addItems(["Todas as Categorias"])
        state.cat_cb.setMinimumWidth(190)
        state.cat_cb.setMinimumHeight(38)
        state.cat_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.FG_MAIN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 6px;
                         padding: 0px 11px; font: 13px {C.FONT_UI_FAMILY}; }}
            QComboBox:hover {{ border-color: {C.BORDER_STRONG}; }}
            QComboBox:focus {{ border-color: {C.NEON_CYAN}; }}
            QComboBox::drop-down {{ border: none; border-left: 1px solid {C.BORDER_SOFT}; width: 22px; }}
            QComboBox QAbstractItemView {{ background: {C.BG_CARD};
                                           color: {C.FG_MAIN};
                                           border: 1px solid {C.BORDER_STRONG};
                                           border-radius: 6px; padding: 4px;
                                           outline: none;
                                           selection-background-color: {C.rgba(C.NEON_CYAN, 0.16)};
                                           selection-color: {C.NEON_CYAN}; }}
        """)
        filt_layout.addWidget(state.cat_cb)
        filt_layout.addStretch()

        state.cat_cb.currentTextChanged.connect(self._on_svc_cat_changed)

    def _build_split(self, parent: QWidget) -> None:
        state = self.state
        card = QFrame(parent)
        card.setObjectName("servicesCard")
        card.setStyleSheet(
            f"QFrame#servicesCard {{ background: {C.BG_CARD};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        card_layout.setSpacing(10)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QVBoxLayout):
            raise TypeError("parent layout must be a QVBoxLayout")
        parent_layout.addWidget(card, stretch=1)
        parent_layout.addSpacing(8)

        split = QWidget(card)
        split.setStyleSheet("background: transparent;")
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(18)
        card_layout.addWidget(split, stretch=1)

        left = QWidget(split)
        left.setMinimumWidth(240)
        left.setMaximumWidth(340)
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        split_layout.addWidget(left)

        # Header com toggle — fica visível sempre; o botão [MENU] aparece só
        # quando o painel está recolhido.
        header_row = QWidget(left)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(6, 4, 6, 4)

        svc_header = QLabel("SERVIÇOS", left)
        svc_header.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        header_layout.addWidget(svc_header)
        header_layout.addStretch()

        state.list_toggle = QPushButton("[MENU]", left)
        state.list_toggle.setFixedSize(24, 24)
        state.list_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_BASE}; color: {C.NEON_CYAN};
                border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                font: 14px {C.FONT_UI_FAMILY};
            }}
            QPushButton:hover {{ border: 1px solid {C.NEON_CYAN}; }}
        """)
        state.list_toggle.setToolTip("Reabrir barra de serviços")
        state.list_toggle.setVisible(False)
        state.list_toggle.clicked.connect(lambda _=False: self._set_list_open(True))
        header_layout.addWidget(state.list_toggle)

        left_layout.addWidget(header_row)
        state.list_header = svc_header

        state.listbox = QListWidget(left)
        state.listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_CARD}; color: {C.FG_MAIN};
                border: none; font: 13px {C.FONT_UI_FAMILY};
                outline: none;
            }}
            QListWidget:focus {{
                border: 1px solid {C.NEON_CYAN};
                border-radius: 8px;
            }}
            QListWidget::item {{
                padding: 8px 11px;
                border-radius: 5px;
            }}
            QListWidget::item:selected {{
                background: {C.rgba(C.NEON_CYAN, 0.09)};
                color: {C.NEON_CYAN};
            }}
            QListWidget::item:hover {{
                background: {C.BG_HOVER};
            }}
        """)
        left_layout.addWidget(state.listbox, stretch=1)
        state.listbox.currentRowChanged.connect(self._on_service_select)

        # Detecta enter/leave do mouse no painel esquerdo (hover do trilho).
        left.enterEvent = lambda event: self._on_left_enter(event)
        left.leaveEvent = lambda event: self._on_left_leave(event)

        state.left_panel = left

        right = QWidget(split)
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        split_layout.addWidget(right, stretch=1)

        detail_header = QLabel("DETALHES DO SERVIÇO", right)
        detail_header.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 9, True))
        right_layout.addWidget(detail_header)

        # O conteúdo do detalhe rola dentro de um QScrollArea; a barra de
        # ações (botões) fica fora, fixa no rodapé da coluna direita.
        scroll = QScrollArea(right)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background: {C.BG_INPUT}; border: none;")

        state.detail_frame = QWidget()
        state.detail_frame.setStyleSheet(f"background: {C.BG_INPUT};")
        state.detail_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        detail_layout = QVBoxLayout(state.detail_frame)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(state.detail_frame)
        state.detail_scroll = scroll
        right_layout.addWidget(scroll, stretch=1)

        # Barra de ações fixa (botões EXCUTAR / PRÉ-VISUALIZAR / CONSULTAR /
        # REVERTER / Salvar / Limpar output). Fica fora do QScrollArea, presa
        # no rodapé da coluna direita, acima do output. Começa oculta; é
        # populada e mostrada quando um serviço é selecionado.
        action_bar = QWidget(right)
        action_bar.setStyleSheet(f"background: {C.BG_INPUT};")
        action_bar_layout = QHBoxLayout(action_bar)
        action_bar_layout.setContentsMargins(0, 4, 0, 4)
        action_bar_layout.setSpacing(6)
        right_layout.addWidget(action_bar)
        state.action_bar = action_bar
        action_bar.setVisible(False)

    # ── Services: seleção / detalhe ──────────────────────────────────
    def _on_svc_cat_changed(self, text: str) -> None:
        self.state.cat_var = text
        self.refresh_service_list()

    def _on_service_select(self, row: int) -> None:
        if row < 0 or row >= len(self.state.services):
            self._clear_detail_panel()
            return
        svc = self.state.services[row]
        # (regra A) Recolhe a barra esquerda a cada seleção de serviço.
        self._set_list_open(False)
        self._show_service_detail(svc)
        self.state.current_svc = svc

    # ── Barra esquerda: colapso / expansão ──────────────────────────

    def _set_list_open(self, open_: bool) -> None:
        """Abre ou recolhe a barra esquerda de serviços.

        Recolhida: vira um trilho (~36 px) com só o botão [MENU].
        Aberta: volta aos 240–340 px com header + lista.
        """
        state = self.state
        left = state.left_panel
        listbox = state.listbox
        header = state.list_header
        toggle = state.list_toggle
        if left is None or listbox is None or header is None or toggle is None:
            return
        state.list_open = open_
        if open_:
            left.setMinimumWidth(240)
            left.setMaximumWidth(340)
            header.setVisible(True)
            listbox.setVisible(True)
            toggle.setVisible(False)
        else:
            left.setMinimumWidth(36)
            left.setMaximumWidth(36)
            header.setVisible(False)
            listbox.setVisible(False)
            toggle.setVisible(True)

    def _on_left_enter(self, event: QEvent) -> None:
        """Hover sobre o trilho recolhido abre a lista temporariamente."""
        state = self.state
        # Só acontece quando estamos dentro de um serviço (barra recolhida).
        if state.current_svc is None:
            return
        self._set_list_open(True)

    def _on_left_leave(self, event: QEvent) -> None:
        """Sair do trilho fecha a lista (volta a recolher)."""
        state = self.state
        # Só acontece quando estamos dentro de um serviço.
        if state.current_svc is None:
            return
        self._set_list_open(False)

    def _clear_detail_panel(self) -> None:
        frame = self.state.detail_frame
        if frame is not None:
            layout = frame.layout()
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    w = item.widget() if item is not None else None
                    if w is not None:
                        w.deleteLater()
        self.state.param_entries.clear()
        self.state.current_svc = None
        self.state.form_state = None
        self.state.save_chk = None
        self.state.block_internet_btn = None
        self.state.block_site_btn = None

        # Barra de ações fixa: oculta e limpa quando não há serviço selecionado.
        abar = self.state.action_bar
        if abar is not None:
            abar.setVisible(False)
            abar_layout = abar.layout()
            if abar_layout is not None:
                while abar_layout.count():
                    item = abar_layout.takeAt(0)
                    w = item.widget() if item is not None else None
                    if w is not None:
                        w.deleteLater()

    def _show_service_detail(self, svc: ServiceDef) -> None:
        self._clear_detail_panel()
        p = self.state.detail_frame
        if p is None:
            return
        p_layout = _ui.page_layout(p)

        mode_label = "Configurando" if svc.config_mode else "Executando"
        title_color = C.NEON_AMBER if svc.config_mode else C.NEON_CYAN

        head = QWidget(p)
        head.setStyleSheet("background: transparent;")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(8)
        p_layout.addWidget(head)
        p_layout.addSpacing(4)

        mode_chip = _ui.chip(head, mode_label.upper(), title_color)
        head_layout.addWidget(mode_chip)

        title_lbl = QLabel(f"{mode_label}: {svc.name}", head)
        title_lbl.setStyleSheet(
            f"color: {C.FG_MAIN}; background: transparent;"
            f" font: 600 18px '{C.FONT_UI_FAMILY}';")
        head_layout.addWidget(title_lbl)

        cat_lbl = _ui.chip(head, svc.category.upper(), C.NEON_PURP)
        head_layout.addWidget(cat_lbl)
        head_layout.addStretch()


        if svc.form_kind == "acl":
            # Botões pré-definidos de bloqueio (pedido): à direita do
            # cabeçalho (após o stretch), mesmo comportamento da main.
            self.state.block_internet_btn = action_button(
                head, "Bloquear Internet",
                lambda _checked=False: self._h().block_internet(),
                C.NEON_RED,
            )
            self.state.block_site_btn = action_button(
                head, "Bloquear site",
                lambda _checked=False: self._h().block_site(),
                C.NEON_AMBER,
            )
            head_layout.addWidget(self.state.block_internet_btn)
            head_layout.addWidget(self.state.block_site_btn)

        cmd_frame = QFrame(p)
        cmd_frame.setObjectName("serviceCmdBox")
        cmd_frame.setStyleSheet(
            f"QFrame#serviceCmdBox {{ background: {C.BG_CODE};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 8px; }}")
        cmd_frame_layout = QVBoxLayout(cmd_frame)
        cmd_frame_layout.setContentsMargins(14, 12, 14, 12)
        p_layout.addWidget(cmd_frame)
        p_layout.addSpacing(10)

        desc_lbl = QLabel(svc.description, cmd_frame)
        desc_lbl.setStyleSheet(
            f"color: {C.FG_CODE}; background: transparent;"
            f" font: 11px '{C.FONT_MONO_FAMILY}';")
        desc_lbl.setWordWrap(True)
        cmd_frame_layout.addWidget(desc_lbl)

        if svc.config_mode:
            if svc.form_kind:
                self._build_composite_form(p, svc)
            else:
                self._build_param_fields(p, svc)

        # Barra de ações fixa (fora do QScrollArea). Limpa widgets anteriores
        # (troca de serviço) e reconstrói com os callbacks deste serviço.
        abar = self.state.action_bar
        if abar is None:
            return
        abar_layout = abar.layout()
        if abar_layout is None or not isinstance(abar_layout, QHBoxLayout):
            return
        # Remove widgets anteriores (ex.: save_chk de serviço anterior).
        while abar_layout.count():
            item = abar_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

        # NOTA: ``QPushButton.clicked`` emite ``checked: bool`` — o callback
        # precisa absorver esse argumento, senão o ``bool`` sobrescreve o
        # default ``s=svc`` e o handler recebe ``False`` (AttributeError
        # engolido pelo Qt → botão "morto").
        btn_svc_exec = action_button(abar, mode_label,
                                     lambda _checked=False, s=svc: self._h().run_service(s),
                                     title_color)
        btn_svc_exec.setIcon(icon("i-play", title_color, 16))
        btn_svc_exec.setIconSize(QSize(16, 16))
        abar_layout.addWidget(btn_svc_exec)
        if svc.form_kind:
            btn_preview = action_button(
                abar, "visualizar  Pré-visualizar",
                lambda _checked=False, s=svc: self._h().preview_form(s),
                C.NEON_AMBER,
            )
            abar_layout.addWidget(btn_preview)
            abar_layout.addSpacing(6)
            btn_consult = action_button(
                abar, "consultar  Consultar",
                lambda _checked=False, s=svc: self._h().consult_form(s),
                C.NEON_CYAN,
            )
            abar_layout.addWidget(btn_consult)
            abar_layout.addSpacing(6)
            btn_rollback = action_button(
                abar, "↩  Reverter (rollback)",
                self._h().rollback_last,
                C.NEON_RED,
            )
            abar_layout.addWidget(btn_rollback)
            abar_layout.addSpacing(12)
            self.state.save_chk = QCheckBox(
                "Salvar na startup-config (save)", abar)
            self.state.save_chk.setChecked(False)
            self.state.save_chk.setToolTip(
                "Desmarcado: a configuração fica apenas no running-config. "
                "Marcado: também é persistida (save all virtual-systems na "
                "VRP8, save nas demais)."
            )
            self.state.save_chk.setStyleSheet(
                _ui.css_label(C.FG_DIM, C.BG_INPUT, 10))
            abar_layout.addWidget(self.state.save_chk)
        abar_layout.addSpacing(6)
        abar_layout.addStretch()
        btn_svc_clr = action_button(abar, "Limpar output",
                                    self._clear_output,
                                    C.NEON_PURP, variant="ghost")
        btn_svc_clr.setIcon(icon("i-x", C.NEON_PURP, 16))
        btn_svc_clr.setIconSize(QSize(16, 16))
        abar_layout.addWidget(btn_svc_clr)

        abar.setVisible(True)

    def _build_composite_form(self, parent: QWidget, svc: ServiceDef) -> None:
        """Constrói o formulário composto (ACL, rota estática) do serviço."""
        if not svc.form_kind:
            return
        spec = get_form_spec(svc.form_kind)

        pf = QFrame(parent)
        pf.setStyleSheet(
            f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; "
            "border-radius: 4px;"
        )
        pf_layout = QVBoxLayout(pf)
        pf_layout.setContentsMargins(8, 4, 8, 6)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(pf)
        parent_layout.addSpacing(8)

        header = QLabel(spec.title.upper(), pf)
        header.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        pf_layout.addWidget(header)

        form = FormWidget(spec, pf)
        pf_layout.addWidget(form)
        self.state.form_state = form

        # ── Pré-visualização viva do bloco ──────────────────────────
        # Mostra exatamente o que será enviado ao device enquanto o
        # operador preenche — evita adivinhação de sintaxe e deixa
        # explícito o papel de cada campo (classificador/behavior/policy).
        preview_header = QLabel("BLOCO ENVIADO AO DEVICE", pf)
        preview_header.setStyleSheet(
            _ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True)
        )
        pf_layout.addWidget(preview_header)

        preview = QPlainTextEdit(pf)
        preview.setReadOnly(True)
        preview.setMaximumHeight(130)
        preview.setStyleSheet(
            f"background: {C.BG_BASE}; color: {C.FG_CODE}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"font-family: {C.FONT_LARGE[0]}; font-size: 11px;"
        )
        pf_layout.addWidget(preview)

        form.changed.connect(
            lambda s=svc, f=form, w=preview: self._refresh_form_preview(s, f, w)
        )
        self._refresh_form_preview(svc, form, preview)

    def _refresh_form_preview(
        self, svc: ServiceDef, form: FormWidget, preview: QPlainTextEdit
    ) -> None:
        """Atualiza a pré-visualização do bloco com os valores atuais."""
        try:
            rendered = render_form(svc.form_kind or "", form.values())
        except SdnValidationError as err:
            preview.setPlainText(f"aviso  {err}")
            return
        except (KeyError, TypeError, ValueError) as err:
            preview.setPlainText(f"aviso  Formulário inconsistente: {err}")
            return
        preview.setPlainText("\n".join(rendered.lines))

    def _build_param_fields(self, parent: QWidget, svc: ServiceDef) -> None:
        params = parse_params(svc)
        if not params:
            return

        pf = QFrame(parent)
        pf.setObjectName("serviceParams")
        pf.setStyleSheet(
            f"QFrame#serviceParams {{ background: {C.BG_SURFACE_2};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 8px; }}")
        pf_layout = QVBoxLayout(pf)
        pf_layout.setContentsMargins(12, 8, 12, 8)
        pf_layout.setSpacing(4)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(pf)
        parent_layout.addSpacing(8)

        param_header = QLabel("PARÂMETROS", pf)
        param_header.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 11, True))
        pf_layout.addWidget(param_header)

        self.state.param_entries.clear()
        # Mapeia segredos por label se o serviço definir params tipados
        secret_labels = {
            spec.label for spec in svc.params if getattr(spec, "secret", False)
        }
        for label, default in params:
            row = QWidget(pf)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            pf_layout.addWidget(row)

            lbl = QLabel(f"{label}:", row)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet(_ui.css_label(C.FG_DIM, "", 11))
            row_layout.addWidget(lbl)

            entry = QLineEdit(row)
            if label in secret_labels:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            entry.setText(default)
            entry.setMinimumHeight(38)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.BG_INPUT}; color: {C.FG_MAIN};
                    border: 1px solid {C.BORDER_NRM}; border-radius: 6px;
                    padding: 0px 11px; font: 13px {C.FONT_UI_FAMILY};
                    selection-background-color: {C.NEON_CYAN};
                    selection-color: {C.BG_BASE};
                }}
                QLineEdit:hover {{
                    border-color: {C.BORDER_STRONG};
                }}
                QLineEdit:focus {{
                    border: 1px solid {C.NEON_CYAN};
                    background: {C.BG_SURFACE_2};
                }}
            """)
            row_layout.addWidget(entry, stretch=1)
            self.state.param_entries[label] = entry

    # ── Internos ─────────────────────────────────────────────────────
    def _clear_output(self) -> None:
        if self._ctx is None:
            return
        _ui.write(self.state.output, "", self._ctx.dispatch)

    def _h(self) -> ServicesHandlers:
        if self._handlers is None:
            raise RuntimeError("ServicesTab não foi construído (build ausente)")
        return self._handlers
