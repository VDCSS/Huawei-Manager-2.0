#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false
"""Page builders — all _build_*_page methods live here."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk

import huawei_manager.constants as C
from huawei_manager.constants import (
    CMD_TEMPLATES,
    FONT_BODY,
    FONT_LARGE,
    FONT_LARGE_B,
    FONT_MEDIUM,
    FONT_MEDIUM_B,
    FONT_SMALL,
    FONT_SMALL_B,
    FONT_XLARGE_B,
    ROUTE_FILTER_LABELS,
    SERVICE_CAT_LABELS,
    THEME,
)
from huawei_manager.services import (
    VNF_TYPES,
    ServiceDef,
    get_all_show_commands,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.topology import TopologyCanvas
from huawei_manager.widgets import (
    action_button,
    neon_entry,
    output_text,
    styled_text,
)


class PageBuilder:
    """Mixin com métodos de construção das páginas da interface Tkinter."""

    # ── Config ────────────────────────────────────────────────────────
    def _build_config_page(self) -> None:
        """Constrói a página de Configuração Atual com output e botão de carregamento."""
        p = self._make_page("config")
        self._page_title(p, "Configuracao Atual", C.NEON_CYAN, "")
        self.out_config = output_text(p)
        self.out_config.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  Carregar Configuracao Atual",
                      lambda: self._run(self._fetch_config), C.NEON_CYAN).pack()

    # ── Route ─────────────────────────────────────────────────────────
    def _build_route_page(self) -> None:
        """Constrói a página de Roteamento com filtro e output."""
        p = self._make_page("route")
        self._page_title(p, "Tabelas e Status do Roteador", C.NEON_CYAN,
                         "Visualizacao de tabelas, vizinhos e metricas do dispositivo")
        row = tk.Frame(p, bg=C.BG_CARD)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text="Filtro:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.route_filter_var = tk.StringVar(value="Tabela de Rotas do Roteador")
        ttk.Combobox(row, textvariable=self.route_filter_var,
             values=list(ROUTE_FILTER_LABELS.values()),
             state="readonly", width=48, font=FONT_BODY).pack(side="left")
        self.out_route = output_text(p)
        self.out_route.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  Carregar",
                      lambda: self._run(self._fetch_route), C.NEON_CYAN).pack()

    # ── ARP ───────────────────────────────────────────────────────────
    def _build_arp_page(self) -> None:
        """Constrói a página da Tabela ARP com output e botão de consulta."""
        p = self._make_page("arp")
        self._page_title(p, "Tabela ARP", C.NEON_CYAN,
                         "CLI: display arp")
        self.out_arp = output_text(p)
        self.out_arp.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  get arp",
                      lambda: self._run(self._fetch_arp), C.NEON_CYAN).pack()

    # ── Info ──────────────────────────────────────────────────────────
    def _build_info_page(self) -> None:
        """Constrói a página de Informações do Sistema com output."""
        p = self._make_page("info")
        self._page_title(p, "Informacoes do Sistema", C.NEON_MAG,
                         "CLI: display version / cpu-usage / memory-usage")
        self.out_info = output_text(p)
        self.out_info.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  get system info",
                      lambda: self._run(self._fetch_info), C.NEON_MAG).pack()

    # ── Cmd / Editor ──────────────────────────────────────────────────
    def _build_cmd_page(self) -> None:
        """Constrói a página do Editor de Comandos com listbox de templates e editor."""
        p = self._make_page("cmd")
        self._page_title(p, "Editor de Comandos", C.NEON_MAG, "")

        card = tk.Frame(p, bg=C.BG_INPUT, highlightthickness=1,
                        highlightbackground=C.BORDER_NRM)
        card.pack(fill="both", expand=True, pady=(0, 8))
        inner = tk.Frame(card, bg=C.BG_INPUT)
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        split = tk.Frame(inner, bg=C.BG_INPUT)
        split.pack(fill="both", expand=True)

        left = tk.Frame(split, bg=C.BG_INPUT, width=260)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="COMANDOS DISPONIVEIS", bg=C.BG_INPUT, fg=C.FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w")
        self._tpl_listbox = tk.Listbox(left, bg=C.BG_INPUT, fg=C.NEON_CYAN,
            selectbackground=C.NEON_PURP, selectforeground="white",
            relief="flat", borderwidth=0,
            font=FONT_MEDIUM, highlightthickness=0)
        self._tpl_listbox.pack(fill="both", expand=True, pady=(4, 0))

        _EXCLUDED_CMDS: set[str] = {
            "display current-configuration",
            "display version", "display device", "display license",
            "display cpu-usage", "display memory-usage",
            "display interface brief", "display lldp neighbor brief",
            "display arp",
            "display interface", "display counters interface",
            "display ip routing-table", "display bgp peer",
            "display ip vpn-instance", "display ospf peer",
            "display qos policy", "display mpls ldp peer",
        }

        self._tpl_cmd_map: dict[str, str] = {}
        for name in CMD_TEMPLATES:
            cmd = CMD_TEMPLATES[name]
            if cmd and cmd not in _EXCLUDED_CMDS:
                self._tpl_cmd_map[name] = cmd

        existing_cmds = set(self._tpl_cmd_map.values())
        show_cmds = get_all_show_commands()
        for svc_name, cmd in show_cmds:
            if cmd not in existing_cmds and cmd not in _EXCLUDED_CMDS:
                existing_cmds.add(cmd)
                self._tpl_cmd_map[svc_name] = cmd

        for name in self._tpl_cmd_map:
            self._tpl_listbox.insert("end", name)
        self._tpl_listbox.bind("<<ListboxSelect>>", self._on_tpl_select)

        right = tk.Frame(split, bg=C.BG_INPUT)
        right.pack(side="left", fill="both", expand=True)

        self._cmd_editor = styled_text(right, height=8)
        self._cmd_editor.pack(fill="x", pady=(0, 6))
        self._cmd_editor.insert("end", 'display ip interface brief')
        def _on_cmd_return(event):
            """Executa comando config ao pressionar Enter."""
            self._run(self._exec_cmd)
            return "break"
        self._cmd_editor.bind("<Return>", _on_cmd_return)
        def _on_cmd_shift_return(event):
            """Insere quebra de linha com Shift+Enter."""
            event.widget.insert("insert", "\n")
            return "break"
        self._cmd_editor.bind("<Shift-Return>", _on_cmd_shift_return)

        abar = tk.Frame(right, bg=C.BG_INPUT)
        abar.pack(fill="x", pady=(0, 6))
        action_button(abar, "\u25b6 Executar",
                      lambda: self._run(self._exec_cmd), C.NEON_CYAN).pack(side="left", padx=(0, 6))
        action_button(abar, "\u2699 Enviar Config",
                      lambda: self._run(self._exec_config), C.NEON_AMBER).pack(side="left")

        self._sysview_var = tk.BooleanVar(value=False)
        sysview_cb = tk.Checkbutton(
            abar, text="system-view", variable=self._sysview_var,
            bg=C.BG_INPUT, fg=C.FG_DIM, selectcolor=C.BG_INPUT,
            activebackground=C.BG_INPUT, activeforeground=C.NEON_CYAN,
            font=FONT_BODY, relief="flat",
        )
        sysview_cb.pack(side="left", padx=(12, 0))

        tk.Label(right,
                 text="\u26a0  Todas as operacoes sao registradas em huawei_audit_structured.jsonl",
                 bg=C.BG_INPUT, fg=C.NEON_AMBER, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))

        self.out_cmd = output_text(right)
        self.out_cmd.pack(fill="both", expand=True)

    # ── Backup ────────────────────────────────────────────────────────
    def _build_backup_page(self) -> None:
        """Constrói a página de Backup com seletor de destino e formato."""
        p = self._make_page("backup")
        self._page_title(p, "Backup de Configuracao", C.NEON_PURP,
                         "display current-configuration \u2192 arquivo")
        ctrl = tk.Frame(p, bg=C.BG_CARD)
        ctrl.pack(fill="x", pady=(0, 12))
        tk.Label(ctrl, text="Destino:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.backup_path = tk.StringVar(value=os.path.expanduser("~"))
        neon_entry(ctrl, textvariable=self.backup_path,
                   width=44, state="normal").pack(side="left", ipady=5)
        action_button(ctrl, "\U0001f4c1 Escolha",
                      self._choose_backup_dir, C.NEON_PURP).pack(side="left", padx=8)
        fmt_frame = tk.Frame(p, bg=C.BG_CARD)
        fmt_frame.pack(fill="x", pady=(0, 8))
        tk.Label(fmt_frame, text="Formato:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.backup_fmt = tk.StringVar(value="Texto (CLI)")
        ttk.Combobox(fmt_frame, textvariable=self.backup_fmt,
                     values=["Texto (CLI)"],
                     state="readonly", width=16,
                     font=FONT_BODY).pack(side="left")
        self.out_backup = output_text(p)
        self.out_backup.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\U0001f4be  Fazer Backup",
                      lambda: self._run(self._do_backup), C.NEON_PURP).pack()

    # ── Topology ──────────────────────────────────────────────────────
    def _build_topology_page(self) -> None:
        """Constrói a página de Topologia com canvas SDN e controles de VNF."""
        p = self._make_page("topology")
        self._page_title(p, "Topologia / VNFs", C.NEON_AMBER,
                         "Cadastro manual + alvo SSH clicavel")

        ctrl = tk.Frame(p, bg=C.BG_CARD)
        ctrl.pack(fill="x", pady=(0, 10))

        admin_label = "\U0001f512  Acesso"
        if self._access_level in ("admin", "tecnico"):
            admin_label = "\U0001f513  Admin" if self._access_level == "admin" else "\U0001f6e0  Tecnico"
        self._admin_btn = action_button(ctrl, admin_label,
                                        self._show_auth_dialog, C.NEON_PURP)
        self._admin_btn.pack(side="left", padx=(0, 8))

        if self._access_level in ("admin", "tecnico"):
            action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                          lambda: self._show_device_dialog(), C.NEON_CYAN).pack(side="left", padx=(0, 8))
        action_button(ctrl, "\u21bb  Atualizar",
                      lambda: self._spawn(self._refresh_vnfs),
                      C.NEON_AMBER).pack(side="left", padx=(0, 8))
        action_button(ctrl, "\u2716  Voltar",
                      self._clear_vnf_target, C.NEON_PURP).pack(side="left")

        self._vnf_info_lbl = tk.Label(
            ctrl, text="  Nenhum VNF selecionado", bg=C.BG_CARD,
            fg=C.FG_DIM, font=FONT_BODY)
        self._vnf_info_lbl.pack(side="right", padx=8)

        canvas_frame = tk.Frame(p, bg=C.BG_BASE,
                                highlightthickness=1, highlightbackground=C.BORDER_NRM)
        canvas_frame.pack(fill="both", expand=True)

        self._topo_canvas = TopologyCanvas(
            canvas_frame, theme=THEME,
            on_select=self._on_vnf_selected,
            on_edit=self._show_device_dialog,
            on_delete=self._delete_device)
        self._topo_canvas.pack(fill="both", expand=True)

        self._vnf_status_lbl = tk.Label(
            p, text="Inventario: vnf_inventory.json",
            bg=C.BG_CARD, fg=C.NEON_AMBER,
            font=FONT_SMALL)
        self._vnf_status_lbl.pack(anchor="w", pady=(4, 0))

        self._spawn(self._refresh_vnfs)

    # ── Services: sub-builders ────────────────────────────────────────
    def _build_services_info_row(self, parent: tk.Frame) -> None:
        """Constrói a linha de informações do VNF selecionado na aba Serviços."""
        info_row = tk.Frame(parent, bg=C.BG_CARD)
        info_row.pack(fill="x", pady=(0, 10))

        self._svc_vnf_lbl = tk.Label(info_row,
            text="VNF: (selecione um VNF na aba Topologia)",
            bg=C.BG_CARD, fg=C.NEON_AMBER, font=FONT_MEDIUM_B)
        self._svc_vnf_lbl.pack(side="left", padx=(0, 16))

        self._svc_type_lbl = tk.Label(info_row,
            text="Tipo: \u2014", bg=C.BG_CARD, fg=C.FG_DIM, font=FONT_BODY)
        self._svc_type_lbl.pack(side="left", padx=(0, 16))

        self._svc_status_lbl = tk.Label(info_row,
            text="", bg=C.BG_CARD, fg=C.FG_DIM, font=FONT_BODY)
        self._svc_status_lbl.pack(side="left")

    def _build_services_filter_row(self, parent: tk.Frame) -> None:
        """Constrói a linha de filtros (categoria, modo) na aba Serviços."""
        filt_row = tk.Frame(parent, bg=C.BG_CARD)
        filt_row.pack(fill="x", pady=(0, 8))

        tk.Label(filt_row, text="Categoria:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self._svc_cat_var = tk.StringVar(value="Todas as Categorias")
        self._svc_cat_cb = ttk.Combobox(filt_row,
            textvariable=self._svc_cat_var, state="readonly",
            width=20, font=FONT_BODY)
        self._svc_cat_cb.pack(side="left", padx=(0, 12))
        self._svc_cat_cb.bind("<<ComboboxSelected>>",
                              lambda _: self._refresh_service_list())

        self._svc_refresh_btn = action_button(filt_row,
            "\u21bb  Atualizar servicos",
            self._refresh_service_list, C.NEON_AMBER)
        self._svc_refresh_btn.pack(side="left", padx=(0, 8))

        self._svc_mode_var = tk.StringVar(value="mock")
        mode_cb = ttk.Combobox(filt_row, textvariable=self._svc_mode_var,
            values=["mock", "cli"], state="readonly",
            width=10, font=FONT_BODY)
        mode_cb.pack(side="left", padx=(8, 0))
        tk.Label(filt_row, text="Modo:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(4, 0))

    def _build_services_split(self, parent: tk.Frame) -> None:
        """Constrói o split horizontal com listbox de serviços e painel de detalhe."""
        card = tk.Frame(parent, bg=C.BG_INPUT,
                        highlightthickness=1, highlightbackground=C.BORDER_NRM)
        card.pack(fill="both", expand=True, pady=(0, 8))

        inner = tk.Frame(card, bg=C.BG_INPUT)
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        split = tk.Frame(inner, bg=C.BG_INPUT)
        split.pack(fill="both", expand=True)

        left = tk.Frame(split, bg=C.BG_INPUT, width=280)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="SERVIÇOS", bg=C.BG_INPUT, fg=C.FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w")

        lbf = tk.Frame(left, bg=C.BG_INPUT)
        lbf.pack(fill="both", expand=True, pady=(4, 0))

        self._svc_listbox = tk.Listbox(lbf, bg=C.BG_INPUT, fg=C.NEON_CYAN,
            selectbackground=C.NEON_PURP, selectforeground="white",
            relief="flat", borderwidth=0,
            font=FONT_MEDIUM, highlightthickness=0)
        self._svc_listbox.pack(side="left", fill="both", expand=True)

        svc_scroll = tk.Scrollbar(lbf, orient="vertical",
                                  command=self._svc_listbox.yview)
        svc_scroll.pack(side="right", fill="y")
        self._svc_listbox.configure(yscrollcommand=svc_scroll.set)
        self._svc_listbox.bind("<<ListboxSelect>>", self._on_service_select)

        right = tk.Frame(split, bg=C.BG_INPUT)
        right.pack(side="left", fill="both", expand=True)

        self._svc_detail_frame = tk.Frame(right, bg=C.BG_INPUT)
        self._svc_detail_frame.pack(fill="both", expand=True)

        self._svc_param_entries: dict[str, tk.Entry] = {}
        self._svc_services: list[ServiceDef] = []
        self._svc_current_svc: ServiceDef | None = None

    # ── Services: main page ───────────────────────────────────────────
    def _build_services_page(self) -> None:
        """Constrói a página do Catálogo de Serviços com info, filtros e split."""
        p = self._make_page("services")
        self._page_title(p, "Catalogo de Servicos", C.NEON_AMBER,
                         "Comandos SHOW e CONFIG por tipo de VNF "
                         "(ROUTER | SWITCH | FIREWALL | \u2026)")

        self._build_services_info_row(p)
        self._build_services_filter_row(p)
        self._build_services_split(p)

        self._svc_output = output_text(p, height=8)
        self._svc_output.pack(fill="x", pady=(0, 4))

        self.root.after(500, self._refresh_service_list)

    # ── Services: listbox population ──────────────────────────────────
    def _refresh_service_list(self) -> None:
        """Recarrega a listbox de serviços conforme VNF selecionado e filtro de categoria."""
        self._svc_listbox.delete(0, "end")
        self._svc_services.clear()

        vnf = self._target_vnf
        if not vnf:
            self._svc_vnf_lbl.configure(text="VNF: (nenhum selecionado)")
            self._svc_type_lbl.configure(text="Tipo: \u2014")
            self._svc_cat_cb.configure(values=["Todas as Categorias"])
            self._svc_cat_var.set("Todas as Categorias")
            self._clear_detail_panel()
            return

        vnf_type = vnf.type.upper()
        host_info = f"{vnf.host}:{vnf.port}" if self._access_level in ("admin", "tecnico") else vnf.host
        self._svc_vnf_lbl.configure(
            text=f"VNF: {vnf.name} ({host_info})")
        self._svc_type_lbl.configure(
            text=f"Tipo: {VNF_TYPES.get(vnf_type, vnf_type)}")
        self._svc_status_lbl.configure(
            text=f"Status: {vnf.status}",
            fg={"online": C.NEON_CYAN, "offline": "#ff4d4d",
                "unknown": C.NEON_AMBER}.get(vnf.status, C.NEON_AMBER))

        all_cats = get_categories_for(vnf_type)
        config_cats = [c for c in all_cats if c.startswith("config-")]
        cat_labels = [SERVICE_CAT_LABELS.get(c, c) for c in config_cats]
        self._svc_cat_cb.configure(values=["Todas as Categorias"] + cat_labels)
        if self._svc_cat_var.get() not in ["Todas as Categorias"] + cat_labels:
            self._svc_cat_var.set("Todas as Categorias")

        selected_cat = self._svc_cat_var.get()
        label_to_cat = {v: k for k, v in SERVICE_CAT_LABELS.items()}
        cat_filter = None if selected_cat == "Todas as Categorias" else label_to_cat.get(selected_cat)
        services = get_services_for(vnf_type, category=cat_filter)
        services = [s for s in services if s.config_mode]
        self._svc_services = services

        if not services:
            self._svc_listbox.insert(
                "end", "  Nenhum servico de configuracao para este tipo de VNF")
            self._clear_detail_panel()
            return

        for svc in services:
            self._svc_listbox.insert("end", f"  \u2699 {svc.name}")

        self._svc_listbox.selection_set(0)
        self._on_service_select()

    def _on_service_select(self, _event=None) -> None:
        """Callback ao selecionar um serviço na listbox — exibe o detalhe."""
        sel = self._svc_listbox.curselection()
        if not sel:
            self._clear_detail_panel()
            return
        idx = sel[0]
        if idx >= len(self._svc_services):
            return
        svc = self._svc_services[idx]
        self._svc_current_svc = svc
        self._show_service_detail(svc)

    def _clear_detail_panel(self) -> None:
        """Limpa o painel de detalhe do serviço e reseta entradas."""
        for w in self._svc_detail_frame.winfo_children():
            w.destroy()
        self._svc_param_entries.clear()
        self._svc_current_svc = None

    def _show_service_detail(self, svc: ServiceDef) -> None:
        """Exibe o formulário de detalhe e parâmetros para um serviço."""
        self._clear_detail_panel()
        p = self._svc_detail_frame

        mode_label = "Configurando" if svc.config_mode else "Executando"
        tk.Label(p, text=f"{mode_label}: {svc.name}", bg=C.BG_INPUT,
                 fg=C.NEON_AMBER if svc.config_mode else C.NEON_CYAN,
                 font=FONT_LARGE_B).pack(anchor="w", pady=(0, 4))

        tk.Label(p, text=f"Categoria: {svc.category}", bg=C.BG_INPUT,
                 fg=C.NEON_PURP, font=FONT_SMALL).pack(anchor="w", pady=(0, 2))

        cmd_frame = tk.Frame(p, bg=C.BG_INPUT,
                             highlightthickness=1, highlightbackground=C.BORDER_NRM)
        cmd_frame.pack(fill="x", pady=(0, 8))
        tk.Label(cmd_frame, text=svc.description, bg=C.BG_INPUT,
                 fg=C.FG_CODE, font=FONT_BODY, anchor="w",
                 wraplength=500).pack(fill="x", padx=8, pady=6)

        if svc.config_mode:
            self._build_param_fields(p, svc)

        abar = tk.Frame(p, bg=C.BG_INPUT)
        abar.pack(fill="x", pady=(4, 0))
        action_button(abar, f"\u25b6 {mode_label}",
                      lambda s=svc: self._run_service(s),
                      C.NEON_CYAN).pack(side="left", padx=(0, 6))
        action_button(abar, "\u2716  Limpar output",
                      lambda: self._write(self._svc_output, ""),
                      C.NEON_PURP).pack(side="left")

    def _build_param_fields(self, parent: tk.Frame, svc: ServiceDef) -> None:
        """Constrói campos de entrada para parâmetros extraídos da descrição do serviço."""
        params = parse_params(svc)
        if not params:
            return

        pf = tk.Frame(parent, bg=C.BG_INPUT,
                      highlightthickness=1, highlightbackground=C.BORDER_NRM)
        pf.pack(fill="x", pady=(0, 8))

        tk.Label(pf, text="PARÂMETROS", bg=C.BG_INPUT, fg=C.FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w", padx=8, pady=(4, 2))

        self._svc_param_entries.clear()
        for label, default in params:
            row = tk.Frame(pf, bg=C.BG_INPUT)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=f"{label}:", bg=C.BG_INPUT, fg=C.FG_DIM,
                     font=FONT_BODY, width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            entry = tk.Entry(row, textvariable=var, bg=C.BG_BASE, fg=C.NEON_CYAN,
                             font=FONT_MEDIUM, relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=C.BORDER_NRM)
            entry.pack(side="left", fill="x", expand=True, ipady=3)
            self._svc_param_entries[label] = entry

    # ── Dashboard ─────────────────────────────────────────────────────
    def _build_home_page(self) -> None:
        """Constrói a página Dashboard com cards de conexão, VNFs, operações e atalhos."""
        p = self._make_page("home")
        self._page_title(p, "Dashboard", C.NEON_CYAN,
                         "Painel de controle — conectividade, VNFs, operacoes recentes")

        self._dash_labels: dict[str, tk.Label] = {}

        row1 = tk.Frame(p, bg=C.BG_CARD)
        row1.pack(fill="both", expand=True, pady=(0, 10))

        # ── Card: Conexão ──
        card = tk.Frame(row1, bg=C.BG_INPUT, highlightthickness=1,
                        highlightbackground=C.BORDER_NRM)
        card.pack(side="left", fill="both", expand=True, padx=(0, 5))

        tk.Label(card, text="\U0001f50c CONEXAO", bg=C.BG_INPUT, fg=C.NEON_CYAN,
                 font=FONT_MEDIUM_B).pack(anchor="w", padx=12, pady=(10, 6))

        self._dash_conn_status = tk.Label(card, text="Desconectado",
                                          bg=C.BG_INPUT, fg="#ff4d4d",
                                          font=FONT_XLARGE_B)
        self._dash_conn_status.pack(anchor="w", padx=12, pady=(0, 2))

        self._dash_conn_host = tk.Label(card, text="Host: ---",
                                        bg=C.BG_INPUT, fg=C.FG_DIM, font=FONT_BODY)
        self._dash_conn_host.pack(anchor="w", padx=12, pady=(0, 10))

        # ── Card: VNFs ──
        card = tk.Frame(row1, bg=C.BG_INPUT, highlightthickness=1,
                        highlightbackground=C.BORDER_NRM)
        card.pack(side="left", fill="both", expand=True, padx=5)

        tk.Label(card, text="\U0001f4e1 VNFs", bg=C.BG_INPUT, fg=C.NEON_MAG,
                 font=FONT_MEDIUM_B).pack(anchor="w", padx=12, pady=(10, 6))

        self._dash_vnf_online = tk.Label(card, text="Online: 0",
                                         bg=C.BG_INPUT, fg=C.NEON_CYAN, font=FONT_BODY)
        self._dash_vnf_online.pack(anchor="w", padx=12, pady=1)

        self._dash_vnf_offline = tk.Label(card, text="Offline: 0",
                                          bg=C.BG_INPUT, fg="#ff4d4d", font=FONT_BODY)
        self._dash_vnf_offline.pack(anchor="w", padx=12, pady=1)

        self._dash_vnf_unknown = tk.Label(card, text="Desconhecido: 0",
                                          bg=C.BG_INPUT, fg=C.NEON_AMBER, font=FONT_BODY)
        self._dash_vnf_unknown.pack(anchor="w", padx=12, pady=(1, 10))

        # ── Card: Últimas Operações ──
        card = tk.Frame(row1, bg=C.BG_INPUT, highlightthickness=1,
                        highlightbackground=C.BORDER_NRM)
        card.pack(side="left", fill="both", expand=True, padx=(5, 0))

        tk.Label(card, text="\U0001f4cb ULTIMAS OPERACOES", bg=C.BG_INPUT, fg=C.NEON_AMBER,
                 font=FONT_MEDIUM_B).pack(anchor="w", padx=12, pady=(10, 6))

        self._dash_audit_text = tk.Text(card, height=5, bg=C.BG_BASE, fg=C.FG_CODE,
                                        font=FONT_SMALL, relief="flat", bd=0,
                                        highlightthickness=1,
                                        highlightbackground=C.BORDER_NRM)
        self._dash_audit_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._dash_audit_text.configure(state="disabled")

        # ── Card: Atalhos Rápidos (full width) ──
        card = tk.Frame(p, bg=C.BG_INPUT, highlightthickness=1,
                        highlightbackground=C.BORDER_NRM)
        card.pack(fill="x")

        tk.Label(card, text="\u2328 ATALHOS RAPIDOS", bg=C.BG_INPUT, fg=C.NEON_PURP,
                 font=FONT_MEDIUM_B).pack(anchor="w", padx=12, pady=(10, 6))

        bar = tk.Frame(card, bg=C.BG_INPUT)
        bar.pack(padx=12, pady=(0, 10))

        self._dash_shortcut_btns = {
            "config": "  \U0001f4cb Config  ",
            "route":  "  \U0001f310 Rotas   ",
            "backup": "  \U0001f4be Backup  ",
            "cmd":    "  \u2328  Editor  ",
        }
        for key, label in self._dash_shortcut_btns.items():
            btn = action_button(bar, label,
                                lambda k=key: self._show_page(k),
                                C.FG_MAIN)
            btn.pack(side="left", padx=(0, 6))

    # ── Manutenção ─────────────────────────────────────────────────────
    def _build_manutencao_page(self) -> None:
        """Constrói a página de Manutenção com botões DEV, Agentes e Setup."""
        if self._access_level == "user":
            p = self._make_page("manutencao")
            self._page_title(p, "Acesso Restrito", C.NEON_AMBER)
            tk.Label(p, text="\U0001f512  Esta pagina e exclusiva para usuarios Tecnico ou Admin.",
                     bg=C.BG_CARD, fg=C.FG_DIM, font=FONT_LARGE).pack(pady=(40, 10))
            action_button(p, "\U0001f511  Autenticar como Tecnico / Admin",
                          self._show_auth_dialog, C.NEON_PURP).pack()
            return

        p = self._make_page("manutencao")
        self._page_title(p, "Manutencao e Diagnostico", C.NEON_MAG,
                         "Testes + Agentes + Setup")

        top = tk.Frame(p, bg=C.BG_CARD)
        top.pack(fill="x", pady=(0, 12))

        grp_dev = tk.LabelFrame(top, text="  DEV  ", bg=C.BG_CARD,
                                fg=C.NEON_CYAN, font=FONT_SMALL_B,
                                highlightbackground=C.BORDER_NRM, highlightthickness=1)
        grp_dev.pack(side="left", fill="x", expand=True, padx=(0, 6))

        action_button(grp_dev, "\u2699  Lint",
                      lambda: self._run_dev_cmd("lint"), C.NEON_CYAN).pack(side="left", padx=2, pady=4)
        action_button(grp_dev, "\U0001f9ea  Testes",
                      lambda: self._run_dev_cmd("test"), C.NEON_MAG).pack(side="left", padx=2, pady=4)
        action_button(grp_dev, "\U0001f50d  Types",
                      lambda: self._run_dev_cmd("typecheck"), C.NEON_PURP).pack(side="left", padx=2, pady=4)
        action_button(grp_dev, "\u25b6  Todos",
                      lambda: self._run_dev_cmd("all"), C.NEON_AMBER).pack(side="left", padx=2, pady=4)

        grp_agents = tk.LabelFrame(top, text="  AGENTES  ", bg=C.BG_CARD,
                                   fg=C.NEON_PURP, font=FONT_SMALL_B,
                                   highlightbackground=C.BORDER_NRM, highlightthickness=1)
        grp_agents.pack(side="left", fill="x", expand=True, padx=(6, 0))

        action_button(grp_agents, "\U0001f50d  Agora",
                      lambda: self._run_agents(), C.NEON_PURP).pack(side="left", padx=2, pady=4)
        self._watcher_btn = action_button(grp_agents, "\U0001f504  Auto: ON",
                                          self._toggle_watcher, C.NEON_CYAN)
        self._watcher_btn.pack(side="left", padx=2, pady=4)

        grp_setup = tk.LabelFrame(top, text="  SETUP  ", bg=C.BG_CARD,
                                  fg=C.NEON_AMBER, font=FONT_SMALL_B,
                                  highlightbackground=C.BORDER_NRM, highlightthickness=1)
        grp_setup.pack(side="left", fill="x", expand=True, padx=(6, 0))

        action_button(grp_setup, "\U0001f4cb  Check",
                      lambda: self._run_setup("check"), C.NEON_AMBER).pack(side="left", padx=2, pady=4)
        action_button(grp_setup, "\u2699  Install",
                      lambda: self._run_setup("install"), C.NEON_CYAN).pack(side="left", padx=2, pady=4)
        action_button(grp_setup, "\U0001f504  Reset",
                      lambda: self._run_setup("reset"), C.NEON_MAG).pack(side="left", padx=2, pady=4)

        summary = tk.Frame(p, bg=C.BG_CARD, highlightthickness=1,
                           highlightbackground=C.BORDER_NRM)
        summary.pack(fill="x", pady=(0, 10))
        self._manut_summary = tk.Text(summary, bg=C.BG_INPUT, fg=C.FG_CODE,
                                       font=FONT_BODY, height=5,
                                       relief="flat", bd=0, padx=10, pady=8)
        self._manut_summary.pack(fill="x")
        self._manut_summary.configure(state="disabled")

        # Barra de filtros para resultados dos agentes
        filter_frame = tk.Frame(p, bg=C.BG_CARD, highlightthickness=1,
                                highlightbackground=C.BORDER_NRM)
        filter_frame.pack(fill="x", pady=(0, 4))
        tk.Label(filter_frame, text="  Filtro:", bg=C.BG_CARD, fg=C.FG_DIM,
                 font=FONT_SMALL_B).pack(side="left", padx=(4, 2))
        self._manut_filter = tk.StringVar(value="all")
        for fval, flbl, fcol in [
            ("all",    "Todas",    C.FG_MAIN),
            ("error",  "Erros",    C.NEON_AMBER),
            ("warning","Avisos",   C.NEON_MAG),
            ("info",   "Info",     C.NEON_CYAN),
        ]:
            tk.Radiobutton(filter_frame, text=flbl, variable=self._manut_filter,
                           value=fval, bg=C.BG_CARD, fg=fcol, selectcolor=C.BG_CARD,
                           font=FONT_SMALL, activebackground=C.BG_INPUT,
                           activeforeground=fcol,
                           command=self._apply_manut_filter
                           ).pack(side="left", padx=4, pady=2)

        output_frame = tk.Frame(p, bg=C.BG_CARD, highlightthickness=1,
                                highlightbackground=C.BORDER_NRM)
        output_frame.pack(fill="both", expand=True, pady=(0, 4))
        self._manut_output = output_text(output_frame, height=12)
        self._manut_output.pack(fill="both", expand=True, padx=4, pady=4)

        bottom = tk.Frame(p, bg=C.BG_CARD)
        bottom.pack(fill="x", pady=(0, 0))
        action_button(bottom, "\u2716  Limpar",
                      lambda: self._write(self._manut_output, ""), C.NEON_PURP).pack(side="right")

        if self._watcher_results:
            self._display_watcher_results(self._watcher_results)
        else:
            self._loading(self._manut_output, "Pronto. Clique em 'Agora' para varrer o projeto.")
            if self._watcher.is_active:
                self._loading(self._manut_output, "Watcher ativo — resultados em ate 60s...")

    def _run_dev_cmd(self, target: str) -> None:
        """Executa um comando make (lint, test, typecheck, all) em background."""
        import subprocess

        from huawei_manager._config import PROJECT_ROOT

        cmds = {
            "lint":      ["make", "lint"],
            "test":      ["make", "test"],
            "typecheck": ["make", "typecheck"],
            "all":       ["make", "ci"],
        }
        cmd_list = cmds.get(target, ["true"])
        self._loading(self._manut_output, f"Executando: {' '.join(cmd_list)}...")

        def target_fn():
            """Executa o comando make em subprocesso e exibe a saída."""
            try:
                result = subprocess.run(cmd_list, capture_output=True, text=True,
                                        timeout=180, cwd=str(PROJECT_ROOT))
                output = result.stdout or result.stderr
                if result.returncode != 0:
                    output = result.stderr or result.stdout
                self._write(self._manut_output, output or "Sem saída")
            except Exception as e:
                self._write(self._manut_output, f"Erro: {e}")

        self._spawn(target_fn)

    def _run_agents(self) -> None:
        """Executa todos os agentes de auditoria em background e exibe resultados."""
        from agents.runner import run_all

        self._loading(self._manut_output, "Varrendo projeto com agentes...")

        def target_fn():
            """Executa todos os agentes em paralelo e atualiza resultados."""
            try:
                results = run_all()
                self._watcher_results = results
                self._dispatch(lambda: self._display_watcher_results(results))
            except Exception as e:
                self._write(self._manut_output, f"Erro nos agentes: {e}")

        self._spawn(target_fn)

    def _toggle_watcher(self) -> None:
        """Liga/desliga o watcher automático de auditoria."""
        if self._watcher.is_active:
            self._watcher.stop()
            self._watcher_btn.configure(text="\U0001f504  Auto: OFF")
            self._write(self._manut_output, "Watcher desligado.")
        else:
            self._watcher.start()
            self._watcher_btn.configure(text="\U0001f504  Auto: ON")
            self._write(self._manut_output, "Watcher ligado — varredura a cada 60s.")

    def _apply_manut_filter(self) -> None:
        """Re-aplica o filtro de severidade aos resultados armazenados."""
        if hasattr(self, "_last_manut_results") and self._last_manut_results:
            self._display_watcher_results(self._last_manut_results)

    def _display_watcher_results(self, results) -> None:
        """Exibe os resultados dos agentes com suporte a filtro e métricas."""
        self._last_manut_results = results

        # Summary: contadores por severidade
        counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        lines = []
        for r in results:
            icon = {"ok": "\u2705", "warning": "\u26a0", "error": "\u274c",
                    "info": "\U0001f4a1"}.get(r.status, "\u2753")
            lines.append(f"{icon}  {r.name:<12}  {r.summary}")
        total = sum(counts.values())
        lines.insert(0, f"  Total: {total} scans | "
                        f"\u274c{counts.get('error',0)}  "
                        f"\u26a0{counts.get('warning',0)}  "
                        f"\U0001f4a1{counts.get('info',0)}  "
                        f"\u2705{counts.get('ok',0)}")
        lines.insert(1, "")
        self._manut_summary.configure(state="normal")
        self._manut_summary.delete("1.0", "end")
        self._manut_summary.insert("end", "\n".join(lines))
        self._manut_summary.configure(state="disabled")

        # Detail: filtrar por severidade
        filter_val = self._manut_filter.get() if hasattr(self, "_manut_filter") else "all"
        items = []
        for r in results:
            for it in r.items:
                if filter_val != "all" and it.severity != filter_val:
                    continue
                icon = {"warning": "\u26a0", "error": "\u274c",
                        "info": "\U0001f4a1"}.get(it.severity, "\u2022")
                items.append(f"{icon}  {r.name}: {it.file}\n"
                             f"   \U0001f4cb  {it.message}\n"
                             f"   \U0001f4a1  {it.suggestion}")
        if items:
            label = {"all": "Todos", "error": "Erros", "warning": "Avisos",
                     "info": "Info"}.get(filter_val, filter_val)
            header = f"\u2500 Filtro: {label} ({len(items)} itens) \u2500\n"
            self._write(self._manut_output, header + "\n".join(items))
        else:
            self._write(self._manut_output, "\u2705  Nenhum problema encontrado para o filtro atual.")

    def _run_setup(self, mode: str) -> None:
        """Executa setup.sh (check, install, reset) em background."""
        import subprocess

        from huawei_manager._config import PROJECT_ROOT

        setup_script = str(PROJECT_ROOT / "setup" / "setup.sh")
        self._loading(self._manut_output, f"setup.sh {mode}...")

        def target_fn():
            """Executa setup.sh em subprocesso e exibe a saída."""
            try:
                result = subprocess.run(
                    [setup_script, mode],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(PROJECT_ROOT),
                )
                output = (result.stdout or result.stderr).strip()
                if not output:
                    output = f"setup.sh {mode} concluído (código {result.returncode})"
                self._write(self._manut_output, output)
            except Exception as e:
                self._write(self._manut_output, f"Erro: {e}")

        self._spawn(target_fn)

    # ── Backup helper ─────────────────────────────────────────────────
    def _choose_backup_dir(self) -> None:
        """Abre diálogo para seleção do diretório de backup."""
        d = filedialog.askdirectory(title="Escolha o diretorio",
                                    initialdir=self.backup_path.get())
        if d:
            self.backup_path.set(d)
