"""Aba Serviços — módulo TabModule (F2-services).

Migrado de ``pages/services.py`` (``PageBuilderServicesMixin``): a
construção virou ``ServicesTab.build(ctx) -> QWidget`` e a execução vive
em :class:`ServicesHandlers`. Sub-builders e handlers de seleção ficam
como métodos privados desta aba (nunca veem o ``App``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.constants import SERVICE_CAT_LABELS
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.services import (
    DEVICE_TYPES,
    ServiceDef,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.tabs import _ui
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.state import ServicesState
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
        _ui.page_title(p, "Catalogo de Servicos", C.NEON_AMBER,
                       "Serviços de configuração por tipo de device "
                       "(ROUTER | SWITCH | …) — comandos show e consultas: "
                       "use o Editor de Comandos")

        self._build_info_row(p)
        self._build_filter_row(p)
        self._build_split(p)

        state.output = output_text(p)
        _ui.page_layout(p).addWidget(state.output)
        _ui.page_layout(p).addSpacing(4)

        QTimer.singleShot(500, self.refresh_service_list)

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
        state.param_entries.clear()
        state.services.clear()
        state.current_svc = None

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
            type_lbl.setText("Tipo: —")
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
            f"color: {status_color}; background: {C.BG_CARD}; font: 11px {C.FONT_UI_FAMILY};")

        all_cats = get_categories_for(device_type)
        config_cats = [c for c in all_cats if c.startswith("config-")]
        # Tipos sem serviços de configuração (ex.: FIREWALL, AP) passam a listar
        # as categorias de leitura, para não deixar a aba vazia.
        type_has_config = any(s.config_mode
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
        if type_has_config:
            services = [s for s in services if s.config_mode]
        state.services = services

        if not services:
            listbox.addItem("  Nenhum servico disponivel para este tipo de Device")
            self._clear_detail_panel()
            return

        for svc in services:
            icon = "⚙" if svc.config_mode else "▶"
            listbox.addItem(f"  {icon} {svc.name}")

        listbox.setCurrentRow(0)

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída da aba)."""
        return self.state.output

    # ── Services: sub-builders ───────────────────────────────────────
    def _build_info_row(self, parent: QWidget) -> None:
        state = self.state
        info_row = QWidget(parent)
        info_row.setStyleSheet(f"background: {C.BG_CARD};")
        info_row.setMaximumHeight(40)
        info_layout = QHBoxLayout(info_row)
        info_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(info_row)
        parent_layout.addSpacing(10)

        state.device_lbl = QLabel("Device: (selecione um device na aba Topologia)", info_row)
        state.device_lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_CARD, 12, True))
        info_layout.addWidget(state.device_lbl)
        info_layout.addSpacing(16)

        state.type_lbl = QLabel("Tipo: —", info_row)
        state.type_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addWidget(state.type_lbl)
        info_layout.addSpacing(16)

        state.status_lbl = QLabel("", info_row)
        state.status_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addStretch()

    def _build_filter_row(self, parent: QWidget) -> None:
        state = self.state
        filt_row = QWidget(parent)
        filt_row.setStyleSheet(f"background: {C.BG_CARD};")
        filt_row.setMaximumHeight(40)
        filt_layout = QHBoxLayout(filt_row)
        filt_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(filt_row)
        parent_layout.addSpacing(8)

        cat_lbl = QLabel("Categoria:", filt_row)
        cat_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        filt_layout.addWidget(cat_lbl)
        filt_layout.addSpacing(8)

        state.cat_var = "Todas as Categorias"
        state.cat_cb = QComboBox(filt_row)
        state.cat_cb.setEditable(False)
        state.cat_cb.addItems(["Todas as Categorias"])
        state.cat_cb.setMinimumWidth(180)
        state.cat_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px {C.FONT_UI_FAMILY}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        filt_layout.addWidget(state.cat_cb)
        filt_layout.addStretch()

        state.cat_cb.currentTextChanged.connect(self._on_svc_cat_changed)

    def _build_split(self, parent: QWidget) -> None:
        state = self.state
        card = QFrame(parent)
        card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QVBoxLayout):
            raise TypeError("parent layout must be a QVBoxLayout")
        parent_layout.addWidget(card, stretch=1)
        parent_layout.addSpacing(8)

        split = QWidget(card)
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(split, stretch=1)

        left = QWidget(split)
        left.setMinimumWidth(240)
        left.setMaximumWidth(340)
        left.setStyleSheet(f"background: {C.BG_INPUT};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(left)
        split_layout.addSpacing(10)

        svc_header = QLabel("SERVIÇOS", left)
        svc_header.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        left_layout.addWidget(svc_header)

        state.listbox = QListWidget(left)
        state.listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                border: none; font: 12px {C.FONT_UI_FAMILY};
                outline: none;
            }}
            QListWidget:focus {{
                border: 1px solid {C.NEON_CYAN};
            }}
            QListWidget::item:selected {{
                background: {C.NEON_PURP}; color: white;
            }}
            QListWidget::item:hover {{
                background: #2a2a4a;
            }}
        """)
        left_layout.addWidget(state.listbox, stretch=1)
        state.listbox.currentRowChanged.connect(self._on_service_select)

        right = QWidget(split)
        right.setStyleSheet(f"background: {C.BG_INPUT};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(right, stretch=1)

        state.detail_frame = QWidget(right)
        state.detail_frame.setStyleSheet(f"background: {C.BG_INPUT};")
        state.detail_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout = QVBoxLayout(state.detail_frame)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(state.detail_frame, stretch=1)

    # ── Services: seleção / detalhe ──────────────────────────────────
    def _on_svc_cat_changed(self, text: str) -> None:
        self.state.cat_var = text
        self.refresh_service_list()

    def _on_service_select(self, row: int) -> None:
        if row < 0 or row >= len(self.state.services):
            self._clear_detail_panel()
            return
        svc = self.state.services[row]
        self.state.current_svc = svc
        self._show_service_detail(svc)

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

    def _show_service_detail(self, svc: ServiceDef) -> None:
        self._clear_detail_panel()
        p = self.state.detail_frame
        if p is None:
            return
        p_layout = _ui.page_layout(p)

        mode_label = "Configurando" if svc.config_mode else "Executando"
        title_color = C.NEON_AMBER if svc.config_mode else C.NEON_CYAN

        title_lbl = QLabel(f"{mode_label}: {svc.name}", p)
        title_lbl.setStyleSheet(_ui.css_label(title_color, C.BG_INPUT, 13, True))
        p_layout.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignLeft)
        p_layout.addSpacing(4)

        cat_lbl = QLabel(f"Categoria: {svc.category}", p)
        cat_lbl.setStyleSheet(_ui.css_label(C.NEON_PURP, C.BG_INPUT, 10))
        p_layout.addWidget(cat_lbl, alignment=Qt.AlignmentFlag.AlignLeft)
        p_layout.addSpacing(2)

        cmd_frame = QFrame(p)
        cmd_frame.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        cmd_frame_layout = QVBoxLayout(cmd_frame)
        cmd_frame_layout.setContentsMargins(8, 6, 8, 6)
        p_layout.addWidget(cmd_frame)
        p_layout.addSpacing(8)

        desc_lbl = QLabel(svc.description, cmd_frame)
        desc_lbl.setStyleSheet(_ui.css_label(C.FG_CODE, C.BG_INPUT, 11))
        desc_lbl.setWordWrap(True)
        cmd_frame_layout.addWidget(desc_lbl)

        if svc.config_mode:
            self._build_param_fields(p, svc)

        abar = QWidget(p)
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.addWidget(abar)
        p_layout.addSpacing(4)

        btn_svc_exec = action_button(abar, f"▶ {mode_label}",
                                     lambda s=svc: self._h().run_service(s),
                                     C.NEON_CYAN)
        abar_layout.addWidget(btn_svc_exec)
        abar_layout.addSpacing(6)
        btn_svc_clr = action_button(abar, "✖  Limpar output",
                                    self._clear_output,
                                    C.NEON_PURP)
        abar_layout.addWidget(btn_svc_clr)

    def _build_param_fields(self, parent: QWidget, svc: ServiceDef) -> None:
        params = parse_params(svc)
        if not params:
            return

        pf = QFrame(parent)
        pf.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        pf_layout = QVBoxLayout(pf)
        pf_layout.setContentsMargins(8, 4, 8, 4)
        parent_layout = parent.layout()
        if not isinstance(parent_layout, QBoxLayout):
            raise TypeError("parent layout must be a QBoxLayout")
        parent_layout.addWidget(pf)
        parent_layout.addSpacing(8)

        param_header = QLabel("PARÂMETROS", pf)
        param_header.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        pf_layout.addWidget(param_header)

        self.state.param_entries.clear()
        for label, default in params:
            row = QWidget(pf)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            pf_layout.addWidget(row)

            lbl = QLabel(f"{label}:", row)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 11))
            row_layout.addWidget(lbl)

            entry = QLineEdit(row)
            entry.setText(default)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.BG_BASE}; color: {C.NEON_CYAN};
                    border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                    padding: 3px 6px; font: 12px {C.FONT_UI_FAMILY};
                }}
                QLineEdit:focus {{
                    border: 1px solid {C.NEON_CYAN};
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
