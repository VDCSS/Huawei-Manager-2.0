"""PageBuilder mixin — Services page (Catálogo de Serviços)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
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
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.constants import SERVICE_CAT_LABELS
from huawei_manager.services import (
    VNF_TYPES,
    ServiceDef,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text


class PageBuilderServicesMixin:
    """Mixin com métodos de construção da página de Serviços."""

    # ── Services: sub-builders ────────────────────────────────────────

    def _build_services_info_row(self, parent: QWidget) -> None:
        info_row = QWidget(parent)
        info_row.setStyleSheet(f"background: {C.BG_CARD};")
        info_row.setMaximumHeight(40)
        info_layout = QHBoxLayout(info_row)
        info_layout.setContentsMargins(0, 0, 0, 0)
        parent.layout().addWidget(info_row)
        parent.layout().addSpacing(10)

        self._svc_vnf_lbl = QLabel("VNF: (selecione um VNF na aba Topologia)", info_row)
        self._svc_vnf_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_CARD, 12, True))
        info_layout.addWidget(self._svc_vnf_lbl)
        info_layout.addSpacing(16)

        self._svc_type_lbl = QLabel("Tipo: \u2014", info_row)
        self._svc_type_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addWidget(self._svc_type_lbl)
        info_layout.addSpacing(16)

        self._svc_status_lbl = QLabel("", info_row)
        self._svc_status_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        info_layout.addStretch()

    def _build_services_filter_row(self, parent: QWidget) -> None:
        filt_row = QWidget(parent)
        filt_row.setStyleSheet(f"background: {C.BG_CARD};")
        filt_row.setMaximumHeight(40)
        filt_layout = QHBoxLayout(filt_row)
        filt_layout.setContentsMargins(0, 0, 0, 0)
        parent.layout().addWidget(filt_row)
        parent.layout().addSpacing(8)

        cat_lbl = QLabel("Categoria:", filt_row)
        cat_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 11))
        filt_layout.addWidget(cat_lbl)
        filt_layout.addSpacing(8)

        self._svc_cat_var = "Todas as Categorias"
        self._svc_cat_cb = QComboBox(filt_row)
        self._svc_cat_cb.setEditable(False)
        self._svc_cat_cb.addItems(["Todas as Categorias"])
        self._svc_cat_cb.setMinimumWidth(180)
        self._svc_cat_cb.setStyleSheet(f"""
            QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                         border: 1px solid {C.BORDER_NRM}; border-radius: 4px;
                         padding: 4px 8px; font: 11px 'Inter'; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {C.BG_INPUT};
                                           color: {C.NEON_CYAN};
                                           selection-background-color: {C.NEON_PURP}; }}
        """)
        filt_layout.addWidget(self._svc_cat_cb)
        filt_layout.addStretch()

        self._svc_cat_cb.currentTextChanged.connect(self._on_svc_cat_changed)

    def _build_services_split(self, parent: QWidget) -> None:
        card = QFrame(parent)
        card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        parent_layout = parent.layout()
        assert isinstance(parent_layout, QVBoxLayout)
        parent_layout.addWidget(card, stretch=1)
        parent.layout().addSpacing(8)

        split = QWidget(card)
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(split, stretch=1)

        left = QWidget(split)
        left.setFixedWidth(280)
        left.setStyleSheet(f"background: {C.BG_INPUT};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(left)
        split_layout.addSpacing(10)

        svc_header = QLabel("SERVI\u00c7OS", left)
        svc_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        left_layout.addWidget(svc_header)

        self._svc_listbox = QListWidget(left)
        self._svc_listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                border: none; font: 12px 'Inter';
                outline: none;
            }}
            QListWidget::item:selected {{
                background: {C.NEON_PURP}; color: white;
            }}
            QListWidget::item:hover {{
                background: #2a2a4a;
            }}
        """)
        left_layout.addWidget(self._svc_listbox, stretch=1)
        self._svc_listbox.currentRowChanged.connect(self._on_service_select)

        right = QWidget(split)
        right.setStyleSheet(f"background: {C.BG_INPUT};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(right, stretch=1)

        self._svc_detail_frame = QWidget(right)
        self._svc_detail_frame.setStyleSheet(f"background: {C.BG_INPUT};")
        self._svc_detail_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout = QVBoxLayout(self._svc_detail_frame)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._svc_detail_frame, stretch=1)

        self._svc_param_entries: dict[str, QLineEdit] = {}
        self._svc_services: list[ServiceDef] = []
        self._svc_current_svc: ServiceDef | None = None

    # ── Services: main page ───────────────────────────────────────────

    def _build_services_page(self: AppCoreProtocol) -> None:
        p = self._make_page("services")
        self._page_title(p, "Catalogo de Servicos", C.NEON_AMBER,
                         "Comandos SHOW e CONFIG por tipo de VNF "
                         "(ROUTER | SWITCH | FIREWALL | \u2026)")

        self._build_services_info_row(p)
        self._build_services_filter_row(p)
        self._build_services_split(p)

        self._svc_output = output_text(p)
        self._page_layout(p).addWidget(self._svc_output)
        self._page_layout(p).addSpacing(4)

        QTimer.singleShot(500, self._refresh_service_list)

    # ── Services: listbox population ──────────────────────────────────

    def _refresh_service_list(self: AppCoreProtocol) -> None:
        if "_svc_listbox" not in self.__dict__ or self._svc_listbox is None:
            return
        self._svc_listbox.clear()
        self._svc_services.clear()

        vnf = self._target_vnf
        if not vnf:
            self._svc_vnf_lbl.setText("VNF: (nenhum selecionado)")
            self._svc_type_lbl.setText("Tipo: \u2014")
            self._svc_cat_cb.blockSignals(True)
            self._svc_cat_cb.clear()
            self._svc_cat_cb.addItems(["Todas as Categorias"])
            self._svc_cat_cb.blockSignals(False)
            self._clear_detail_panel()
            return

        vnf_type = vnf.type.upper()
        host_info = f"{vnf.host}:{vnf.port}" if self._access_level in ("admin", "tecnico") else vnf.host
        self._svc_vnf_lbl.setText(f"VNF: {vnf.name} ({host_info})")
        self._svc_type_lbl.setText(f"Tipo: {VNF_TYPES.get(vnf_type, vnf_type)}")

        status_color = {"online": C.NEON_CYAN, "offline": C.NEON_RED,
                        "unknown": C.NEON_AMBER}.get(vnf.status, C.NEON_AMBER)
        self._svc_status_lbl.setText(f"Status: {vnf.status}")
        self._svc_status_lbl.setStyleSheet(
            f"color: {status_color}; background: {C.BG_CARD}; font: 11px 'Inter';")

        all_cats = get_categories_for(vnf_type)
        config_cats = [c for c in all_cats if c.startswith("config-")]
        cat_labels = [SERVICE_CAT_LABELS.get(c, c) for c in config_cats]
        all_labels = ["Todas as Categorias"] + cat_labels

        self._svc_cat_cb.blockSignals(True)
        self._svc_cat_cb.clear()
        self._svc_cat_cb.addItems(all_labels)
        if self._svc_cat_var in all_labels:
            self._svc_cat_cb.setCurrentText(self._svc_cat_var)
        else:
            self._svc_cat_cb.setCurrentText("Todas as Categorias")
            self._svc_cat_var = "Todas as Categorias"
        self._svc_cat_cb.blockSignals(False)

        selected_cat = self._svc_cat_var
        label_to_cat = {v: k for k, v in SERVICE_CAT_LABELS.items()}
        cat_filter = None if selected_cat == "Todas as Categorias" else label_to_cat.get(selected_cat)
        services = get_services_for(vnf_type, category=cat_filter)
        services = [s for s in services if s.config_mode]
        self._svc_services = services

        if not services:
            self._svc_listbox.addItem("  Nenhum servico de configuracao para este tipo de VNF")
            self._clear_detail_panel()
            return

        for svc in services:
            self._svc_listbox.addItem(f"  \u2699 {svc.name}")

        self._svc_listbox.setCurrentRow(0)

    def _on_svc_cat_changed(self, text: str) -> None:
        self._svc_cat_var = text
        self._refresh_service_list()

    def _on_service_select(self, row: int) -> None:
        if row < 0 or row >= len(self._svc_services):
            self._clear_detail_panel()
            return
        svc = self._svc_services[row]
        self._svc_current_svc = svc
        self._show_service_detail(svc)

    def _clear_detail_panel(self) -> None:
        layout = self._svc_detail_frame.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        self._svc_param_entries.clear()
        self._svc_current_svc = None

    def _show_service_detail(self: AppCoreProtocol, svc: ServiceDef) -> None:
        self._clear_detail_panel()
        p = self._svc_detail_frame
        p_layout = self._page_layout(p)

        mode_label = "Configurando" if svc.config_mode else "Executando"
        title_color = C.NEON_AMBER if svc.config_mode else C.NEON_CYAN

        title_lbl = QLabel(f"{mode_label}: {svc.name}", p)
        title_lbl.setStyleSheet(self._css_label(title_color, C.BG_INPUT, 13, True))
        p_layout.addWidget(title_lbl, alignment=Qt.AlignLeft)
        p_layout.addSpacing(4)

        cat_lbl = QLabel(f"Categoria: {svc.category}", p)
        cat_lbl.setStyleSheet(self._css_label(C.NEON_PURP, C.BG_INPUT, 10))
        p_layout.addWidget(cat_lbl, alignment=Qt.AlignLeft)
        p_layout.addSpacing(2)

        cmd_frame = QFrame(p)
        cmd_frame.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        cmd_frame_layout = QVBoxLayout(cmd_frame)
        cmd_frame_layout.setContentsMargins(8, 6, 8, 6)
        p_layout.addWidget(cmd_frame)
        p_layout.addSpacing(8)

        desc_lbl = QLabel(svc.description, cmd_frame)
        desc_lbl.setStyleSheet(self._css_label(C.FG_CODE, C.BG_INPUT, 11))
        desc_lbl.setWordWrap(True)
        cmd_frame_layout.addWidget(desc_lbl)

        if svc.config_mode:
            self._build_param_fields(p, svc)

        abar = QWidget(p)
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.addWidget(abar)
        p_layout.addSpacing(4)

        btn_svc_exec = action_button(abar, f"\u25b6 {mode_label}",
                                     lambda s=svc: self._run_service(s),
                                     C.NEON_CYAN)
        abar_layout.addWidget(btn_svc_exec)
        abar_layout.addSpacing(6)
        btn_svc_clr = action_button(abar, "\u2716  Limpar output",
                                    lambda: self._write(self._svc_output, ""),
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
        parent.layout().addWidget(pf)
        parent.layout().addSpacing(8)

        param_header = QLabel("PAR\u00c2METROS", pf)
        param_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        pf_layout.addWidget(param_header)

        self._svc_param_entries.clear()
        for label, default in params:
            row = QWidget(pf)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            pf_layout.addWidget(row)

            lbl = QLabel(f"{label}:", row)
            lbl.setFixedWidth(100)
            lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 11))
            row_layout.addWidget(lbl)

            entry = QLineEdit(row)
            entry.setText(default)
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.BG_BASE}; color: {C.NEON_CYAN};
                    border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                    padding: 3px 6px; font: 12px 'Inter';
                }}
                QLineEdit:focus {{
                    border: 1px solid {C.NEON_CYAN};
                }}
            """)
            row_layout.addWidget(entry, stretch=1)
            self._svc_param_entries[label] = entry
