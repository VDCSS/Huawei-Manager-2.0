#!/usr/bin/env python3
from __future__ import annotations

import datetime
import io
import logging
import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from huawei_manager.audit_log import AuditLogger
from huawei_manager.constants import (
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BG_SIDEBAR,
    BORDER_NRM,
    CLI_FILTERS,
    CMD_TEMPLATES,
    FG_CODE,
    FG_DIM,
    FG_MAIN,
    FONT_BODY,
    FONT_H1,
    FONT_H2_B,
    FONT_HERO_B,
    FONT_LARGE,
    FONT_LARGE_B,
    FONT_MEDIUM,
    FONT_MEDIUM_B,
    FONT_SMALL,
    FONT_SMALL_B,
    FONT_XLARGE,
    FONT_XLARGE_B,
    FONT_XSMALL,
    NEON_AMBER,
    NEON_CYAN,
    NEON_MAG,
    NEON_PURP,
    ROUTE_FILTER_LABELS,
    SERVICE_CAT_LABELS,
    THEME,
)
from huawei_manager.services import (
    VNF_TYPES,
    ServiceDef,
    execute_service,
    get_all_show_commands,
    get_categories_for,
    get_services_for,
    parse_params,
)
from huawei_manager.session import NetmikoSession
from huawei_manager.topology import (
    VNF,
    NorthboundController,
    TopologyCanvas,
    load_vnf_inventory,
    save_vnf_inventory,
)
from huawei_manager.vault import SecretsBackend, get_backend
from huawei_manager.widgets import (
    action_button,
    neon_button,
    neon_entry,
    output_text,
    styled_text,
)

# ─── LOG ─────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_fh = RotatingFileHandler(
    LOG_DIR / "huawei-manager.log",
    maxBytes=5_000_000,
    backupCount=3,
    encoding="utf-8",
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(name)s \u2014 %(message)s"
))

_sh = logging.StreamHandler()
_sh.setLevel(logging.INFO)
_sh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s \u2014 %(message)s",
    datefmt="%H:%M:%S"
))

_root = logging.getLogger("huawei")
_root.setLevel(logging.DEBUG)
_root.addHandler(_fh)
_root.addHandler(_sh)

log = logging.getLogger("huawei_manager")
log.info("Logging iniciado \u2014 %s", LOG_DIR.resolve())

# ─── SECRETS / AUDIT ─────────────────────────────────────────────────
try:
    _secrets: SecretsBackend = get_backend()
except Exception as _e:
    log.error("Falha ao inicializar secrets backend: %s \u2014 usando fallback env", _e)
    from huawei_manager.vault import EnvBackend
    _secrets = EnvBackend()

audit = AuditLogger()

# ─── CONFIG ───────────────────────────────────────────────────────────
def _s(key: str, default: str = "") -> str:
    return _secrets.get(key, default)

HOST      = _s("ROUTER_HOST")
PORT      = int(_s("ROUTER_PORT", "2222"))
USER      = _s("ROUTER_USERNAME")
PASS      = _s("ROUTER_PASSWORD")
SSH_KEY   = os.path.expanduser(_s("ROUTER_SSH_KEY", "~/.ssh/huawei_ed25519"))
HK_VERIFY = _s("ROUTER_HOSTKEY_VERIFY", "true").lower() == "true"

NCE_HOST       = _s("NCE_HOST")
NCE_PORT       = int(_s("NCE_PORT", "18002"))
NCE_USER       = _s("NCE_USERNAME")
NCE_PASS       = _s("NCE_PASSWORD")
NCE_VERIFY_SSL = _s("NCE_VERIFY_SSL", "false").lower() == "true"


# ═══════════════════════════════════════════════════════════════════════
#  APLICACAO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════
class HuaweiRouterApp:

    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30

    # ── Inicializacao ────────────────────────────────────────────────
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("HUAWEI MANAGER")
        self.root.geometry("1220x740")
        self.root.configure(bg=BG_BASE)
        self.root.resizable(True, True)

        self.session  = NetmikoSession(_secrets, audit)
        self._active_btn: tk.Frame | None = None
        self._admin_authenticated: bool = False

        # rate limit admin
        self._admin_attempts = 0
        self._admin_locked_until: float = 0

        self._target_vnf: VNF | None = None
        self._nce_ctrl:   NorthboundController | None = None
        self._vnfs:       list[VNF] = []
        self._topo_canvas: TopologyCanvas | None = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hw")

        self._build_layout()
        self._show_page("topology")
        self._tick_clock()
        self._init_topology_backend()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ───────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        self.sidebar = tk.Frame(self.root, bg=BG_SIDEBAR, width=228)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        right = tk.Frame(self.root, bg=BG_BASE)
        right.pack(side="left", fill="both", expand=True)

        self._build_header(right)
        tk.Frame(right, bg=BORDER_NRM, height=1).pack(fill="x")

        self.content = tk.Frame(right, bg=BG_BASE)
        self.content.pack(fill="both", expand=True, padx=18, pady=18)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        self._build_sidebar()
        self._build_footer()

        self.pages: dict[str, tk.Frame] = {}
        self._page_builders = {
            "config":   self._build_config_page,
            "route":    self._build_route_page,
            "arp":      self._build_arp_page,
            "info":     self._build_info_page,
            "cmd":      self._build_cmd_page,
            "backup":   self._build_backup_page,
            "topology": self._build_topology_page,
            "services": self._build_services_page,
        }

    # ── Header ───────────────────────────────────────────────────────
    def _build_header(self, parent) -> None:
        hdr = tk.Frame(parent, bg=BG_BASE, height=56)
        hdr.pack(fill="x", padx=18, pady=(10, 6))
        hdr.pack_propagate(False)

        tk.Label(hdr, text="HUAWEI",    bg=BG_BASE, fg=NEON_CYAN,
                 font=FONT_HERO_B).pack(side="left")
        tk.Label(hdr, text=" MANAGER",  bg=BG_BASE, fg=FG_MAIN,
                 font=FONT_HERO_B).pack(side="left")
        tk.Label(hdr, text="  SSH/CLI + SDN", bg=BG_BASE, fg=NEON_PURP,
                 font=FONT_LARGE).pack(side="left")

        badge = tk.Frame(hdr, bg=BG_BASE)
        badge.pack(side="right")

        self.status_dot = tk.Label(badge, text="\u25cf", bg=BG_BASE, fg=NEON_PURP,
                                   font=FONT_H1)
        self.status_dot.pack(side="left", padx=(0, 4))
        self.status_lbl = tk.Label(badge, text="Desconectado", bg=BG_BASE, fg=FG_DIM,
                                   font=FONT_BODY)
        self.status_lbl.pack(side="left", padx=(0, 12))
        self.conn_btn = action_button(badge, "  CONECTAR  ",
                                      self._toggle_connect, NEON_CYAN)
        self.conn_btn.pack(side="left")

    # ── Sidebar ──────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        logo = tk.Frame(self.sidebar, bg=BG_SIDEBAR)
        logo.pack(fill="x", pady=(18, 8))
        tk.Label(logo, text="[ MODULOS ]", bg=BG_SIDEBAR,
                 fg=FG_DIM, font=FONT_SMALL).pack(padx=16, anchor="w")
        tk.Frame(self.sidebar, bg=BORDER_NRM, height=1).pack(fill="x", padx=16, pady=6)

        self._nav_buttons: dict[str, tk.Frame] = {}
        items = (
            ("topology", "\U0001f5fa", "Topologia / VNFs",     NEON_AMBER),
            ("config",   "\U0001f4cb", "Config Atual",       NEON_CYAN),
            ("route",    "\U0001f310", "Roteamento",          NEON_CYAN),
            ("arp",      "\U0001f4e1", "Tabela ARP",           NEON_CYAN),
            ("info",     "\U0001f4bb", "Info do Sistema",      NEON_MAG),
            ("cmd",      "\u2328",  "Editor de Comandos",       NEON_MAG),
            ("backup",   "\U0001f4be", "Backup",               NEON_PURP),
            ("services", "\u26a1", "Servicos",              NEON_AMBER),
        )
        for key, icon, label, color in items:
            btn = neon_button(self.sidebar, label,
                              lambda k=key: self._show_page(k),
                              color=color, icon=icon)
            btn.pack(fill="x", pady=1)
            self._nav_buttons[key] = btn

        tk.Frame(self.sidebar, bg=BORDER_NRM, height=1).pack(
            fill="x", padx=16, pady=(16, 4))
        tk.Label(self.sidebar, text="ALVO VNF", bg=BG_SIDEBAR,
                 fg=FG_DIM, font=FONT_BODY).pack(padx=16, anchor="w")
        self._vnf_target_lbl = tk.Label(
            self.sidebar, text="(roteador padrao)", bg=BG_SIDEBAR,
            fg=NEON_AMBER, font=FONT_MEDIUM_B, wraplength=180)
        self._vnf_target_lbl.pack(padx=16, anchor="w")

    # ── Footer ───────────────────────────────────────────────────────
    def _build_footer(self) -> None:
        foot = tk.Frame(self.root, bg="#08081a", height=22)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot,
                 text="Huawei Manager  \u2022  Netmiko  \u2022  SDN  \u2022  Multi-VNF",
                 bg="#08081a", fg=FG_DIM, font=FONT_XSMALL).pack(side="left", padx=12)
        self.clock_lbl = tk.Label(foot, bg="#08081a", fg=NEON_PURP,
                                  font=FONT_XSMALL)
        self.clock_lbl.pack(side="right", padx=12)

    # ── Helpers de pagina ─────────────────────────────────────────────
    def _make_page(self, key: str) -> tk.Frame:
        f = tk.Frame(self.content, bg=BG_CARD,
                     highlightthickness=1, highlightbackground=BORDER_NRM)
        f.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(f, bg=BG_CARD)
        inner.pack(fill="both", expand=True, padx=18, pady=18)
        self.pages[key] = inner
        return inner

    def _page_title(self, parent, text, color, subtitle="") -> None:
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=(0, 14))
        tk.Frame(row, bg=color, width=4).pack(side="left", fill="y", padx=(0, 10))
        col = tk.Frame(row, bg=BG_CARD)
        col.pack(side="left")
        tk.Label(col, text=text.upper(), bg=BG_CARD, fg=color,
                 font=FONT_H2_B).pack(anchor="w")
        if subtitle:
            tk.Label(col, text=subtitle, bg=BG_CARD, fg=FG_DIM,
                     font=FONT_SMALL).pack(anchor="w")

    # ══════════════════════════════════════════════════════════════════
    #  PAGE BUILDERS
    # ══════════════════════════════════════════════════════════════════

    def _build_config_page(self) -> None:
        p = self._make_page("config")
        self._page_title(p, "Configuracao Atual", NEON_CYAN, "")
        self.out_config = output_text(p)
        self.out_config.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  Carregar Configuracao Atual",
                      lambda: self._run(self._fetch_config), NEON_CYAN).pack()

    def _build_route_page(self) -> None:
        p = self._make_page("route")
        self._page_title(p, "Tabelas e Status do Roteador", NEON_CYAN,
                         "Visualizacao de tabelas, vizinhos e metricas do dispositivo")
        row = tk.Frame(p, bg=BG_CARD)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text="Filtro:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.route_filter_var = tk.StringVar(value="Tabela de Rotas do Roteador")
        ttk.Combobox(row, textvariable=self.route_filter_var,
                     values=list(ROUTE_FILTER_LABELS.values()),
                     state="readonly", width=48, font=FONT_BODY).pack(side="left")
        self.out_route = output_text(p)
        self.out_route.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  Carregar",
                      lambda: self._run(self._fetch_route), NEON_CYAN).pack()

    def _build_arp_page(self) -> None:
        p = self._make_page("arp")
        self._page_title(p, "Tabela ARP", NEON_CYAN,
                         "CLI: display arp")
        self.out_arp = output_text(p)
        self.out_arp.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  get arp",
                      lambda: self._run(self._fetch_arp), NEON_CYAN).pack()

    def _build_info_page(self) -> None:
        p = self._make_page("info")
        self._page_title(p, "Informacoes do Sistema", NEON_MAG,
                         "CLI: display version / cpu-usage / memory-usage")
        self.out_info = output_text(p)
        self.out_info.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\u21bb  get system info",
                      lambda: self._run(self._fetch_info), NEON_MAG).pack()

    def _build_cmd_page(self) -> None:
        p = self._make_page("cmd")
        self._page_title(p, "Editor de Comandos", NEON_MAG, "")

        card = tk.Frame(p, bg=BG_INPUT, highlightthickness=1,
                        highlightbackground=BORDER_NRM)
        card.pack(fill="both", expand=True, pady=(0, 8))
        inner = tk.Frame(card, bg=BG_INPUT)
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        split = tk.Frame(inner, bg=BG_INPUT)
        split.pack(fill="both", expand=True)

        # ── Left: command listbox ─────────────────────────────────────
        left = tk.Frame(split, bg=BG_INPUT, width=260)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="COMANDOS DISPONIVEIS", bg=BG_INPUT, fg=FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w")
        self._tpl_listbox = tk.Listbox(left, bg=BG_INPUT, fg=NEON_CYAN,
            selectbackground=NEON_PURP, selectforeground="white",
            relief="flat", borderwidth=0,
            font=FONT_MEDIUM, highlightthickness=0)
        self._tpl_listbox.pack(fill="both", expand=True, pady=(4, 0))

        # Comandos cobertos por abas dedicadas — excluir da listbox
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

        # ── Right: editor + output ────────────────────────────────────
        right = tk.Frame(split, bg=BG_INPUT)
        right.pack(side="left", fill="both", expand=True)

        self._cmd_editor = styled_text(right, height=8)
        self._cmd_editor.pack(fill="x", pady=(0, 6))
        self._cmd_editor.insert("end", 'display ip interface brief')

        abar = tk.Frame(right, bg=BG_INPUT)
        abar.pack(fill="x", pady=(0, 6))
        action_button(abar, "\u25b6 Executar",
                      lambda: self._run(self._exec_cmd), NEON_CYAN).pack(side="left", padx=(0, 6))
        action_button(abar, "\u2699 Enviar Config",
                      lambda: self._run(self._exec_config), NEON_AMBER).pack(side="left")

        self._sysview_var = tk.BooleanVar(value=False)
        sysview_cb = tk.Checkbutton(
            abar, text="system-view", variable=self._sysview_var,
            bg=BG_INPUT, fg=FG_DIM, selectcolor=BG_INPUT,
            activebackground=BG_INPUT, activeforeground=NEON_CYAN,
            font=FONT_BODY, relief="flat",
        )
        sysview_cb.pack(side="left", padx=(12, 0))

        tk.Label(right,
                 text="\u26a0  Todas as operacoes sao registradas em huawei_audit_structured.jsonl",
                 bg=BG_INPUT, fg=NEON_AMBER, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))

        self.out_cmd = output_text(right)
        self.out_cmd.pack(fill="both", expand=True)

    def _build_backup_page(self) -> None:
        p = self._make_page("backup")
        self._page_title(p, "Backup de Configuracao", NEON_PURP,
                         "display current-configuration \u2192 arquivo")
        ctrl = tk.Frame(p, bg=BG_CARD)
        ctrl.pack(fill="x", pady=(0, 12))
        tk.Label(ctrl, text="Destino:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.backup_path = tk.StringVar(value=os.path.expanduser("~"))
        neon_entry(ctrl, textvariable=self.backup_path,
                   width=44, state="normal").pack(side="left", ipady=5)
        action_button(ctrl, "\U0001f4c1 Escolha",
                      self._choose_backup_dir, NEON_PURP).pack(side="left", padx=8)
        fmt_frame = tk.Frame(p, bg=BG_CARD)
        fmt_frame.pack(fill="x", pady=(0, 8))
        tk.Label(fmt_frame, text="Formato:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        self.backup_fmt = tk.StringVar(value="Texto (CLI)")
        ttk.Combobox(fmt_frame, textvariable=self.backup_fmt,
                     values=["Texto (CLI)"],
                     state="readonly", width=16,
                     font=FONT_BODY).pack(side="left")
        self.out_backup = output_text(p)
        self.out_backup.pack(fill="both", expand=True, pady=(0, 10))
        action_button(p, "\U0001f4be  Fazer Backup",
                      lambda: self._run(self._do_backup), NEON_PURP).pack()

    def _build_topology_page(self) -> None:
        p = self._make_page("topology")
        self._page_title(p, "Topologia / VNFs", NEON_AMBER,
                         "Cadastro manual + alvo SSH clicavel")

        ctrl = tk.Frame(p, bg=BG_CARD)
        ctrl.pack(fill="x", pady=(0, 10))

        self._admin_btn = action_button(ctrl, "\U0001f512  Admin",
                                        self._show_admin_login, NEON_PURP)
        self._admin_btn.pack(side="left", padx=(0, 8))

        action_button(ctrl, "\u2795  Cadastrar Dispositivo",
                      lambda: self._show_device_dialog(), NEON_CYAN).pack(side="left", padx=(0, 8))
        action_button(ctrl, "\u21bb  Atualizar",
                      lambda: self._spawn(self._refresh_vnfs),
                      NEON_AMBER).pack(side="left", padx=(0, 8))
        action_button(ctrl, "\u2716  Voltar",
                      self._clear_vnf_target, NEON_PURP).pack(side="left")

        self._vnf_info_lbl = tk.Label(
            ctrl, text="  Nenhum VNF selecionado", bg=BG_CARD,
            fg=FG_DIM, font=FONT_BODY)
        self._vnf_info_lbl.pack(side="right", padx=8)

        canvas_frame = tk.Frame(p, bg=BG_BASE,
                                highlightthickness=1, highlightbackground=BORDER_NRM)
        canvas_frame.pack(fill="both", expand=True)

        self._topo_canvas = TopologyCanvas(
            canvas_frame, theme=THEME,
            on_select=self._on_vnf_selected,
            on_edit=self._show_device_dialog,
            on_delete=self._delete_device)
        self._topo_canvas.pack(fill="both", expand=True)

        nce_mode = "MOCK (vnf_inventory.json)" if not NCE_HOST else f"REAL ({NCE_HOST}:{NCE_PORT})"
        self._nce_status_lbl = tk.Label(
            p, text=f"Inventario: local ({nce_mode})",
            bg=BG_CARD, fg=NEON_AMBER if not NCE_HOST else NEON_CYAN,
            font=FONT_SMALL)
        self._nce_status_lbl.pack(anchor="w", pady=(4, 0))

        self._spawn(self._refresh_vnfs)

    def _build_services_info_row(self, parent: tk.Frame) -> None:
        info_row = tk.Frame(parent, bg=BG_CARD)
        info_row.pack(fill="x", pady=(0, 10))

        self._svc_vnf_lbl = tk.Label(info_row,
            text="VNF: (selecione um VNF na aba Topologia)",
            bg=BG_CARD, fg=NEON_AMBER, font=FONT_MEDIUM_B)
        self._svc_vnf_lbl.pack(side="left", padx=(0, 16))

        self._svc_type_lbl = tk.Label(info_row,
            text="Tipo: \u2014", bg=BG_CARD, fg=FG_DIM, font=FONT_BODY)
        self._svc_type_lbl.pack(side="left", padx=(0, 16))

        self._svc_status_lbl = tk.Label(info_row,
            text="", bg=BG_CARD, fg=FG_DIM, font=FONT_BODY)
        self._svc_status_lbl.pack(side="left")

    def _build_services_filter_row(self, parent: tk.Frame) -> None:
        filt_row = tk.Frame(parent, bg=BG_CARD)
        filt_row.pack(fill="x", pady=(0, 8))

        tk.Label(filt_row, text="Categoria:", bg=BG_CARD, fg=FG_DIM,
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
            self._refresh_service_list, NEON_AMBER)
        self._svc_refresh_btn.pack(side="left", padx=(0, 8))

        self._svc_mode_var = tk.StringVar(value="mock")
        mode_cb = ttk.Combobox(filt_row, textvariable=self._svc_mode_var,
            values=["mock", "cli"], state="readonly",
            width=10, font=FONT_BODY)
        mode_cb.pack(side="left", padx=(8, 0))
        tk.Label(filt_row, text="Modo:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(4, 0))

    def _build_services_split(self, parent: tk.Frame) -> None:
        card = tk.Frame(parent, bg=BG_INPUT,
                        highlightthickness=1, highlightbackground=BORDER_NRM)
        card.pack(fill="both", expand=True, pady=(0, 8))

        inner = tk.Frame(card, bg=BG_INPUT)
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        split = tk.Frame(inner, bg=BG_INPUT)
        split.pack(fill="both", expand=True)

        left = tk.Frame(split, bg=BG_INPUT, width=280)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="SERVIÇOS", bg=BG_INPUT, fg=FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w")

        lbf = tk.Frame(left, bg=BG_INPUT)
        lbf.pack(fill="both", expand=True, pady=(4, 0))

        self._svc_listbox = tk.Listbox(lbf, bg=BG_INPUT, fg=NEON_CYAN,
            selectbackground=NEON_PURP, selectforeground="white",
            relief="flat", borderwidth=0,
            font=FONT_MEDIUM, highlightthickness=0)
        self._svc_listbox.pack(side="left", fill="both", expand=True)

        svc_scroll = tk.Scrollbar(lbf, orient="vertical",
                                  command=self._svc_listbox.yview)
        svc_scroll.pack(side="right", fill="y")
        self._svc_listbox.configure(yscrollcommand=svc_scroll.set)
        self._svc_listbox.bind("<<ListboxSelect>>", self._on_service_select)

        right = tk.Frame(split, bg=BG_INPUT)
        right.pack(side="left", fill="both", expand=True)

        self._svc_detail_frame = tk.Frame(right, bg=BG_INPUT)
        self._svc_detail_frame.pack(fill="both", expand=True)

        self._svc_param_entries: dict[str, tk.Entry] = {}
        self._svc_services: list[ServiceDef] = []
        self._svc_current_svc: ServiceDef | None = None

    def _build_services_page(self) -> None:
        p = self._make_page("services")
        self._page_title(p, "Catalogo de Servicos", NEON_AMBER,
                         "Comandos SHOW e CONFIG por tipo de VNF "
                         "(ROUTER | SWITCH | FIREWALL | \u2026)")

        self._build_services_info_row(p)
        self._build_services_filter_row(p)
        self._build_services_split(p)

        self._svc_output = output_text(p, height=8)
        self._svc_output.pack(fill="x", pady=(0, 4))

        self.root.after(500, self._refresh_service_list)

    def _refresh_service_list(self) -> None:
        self._svc_listbox.delete(0, "end")
        self._svc_services.clear()

        vnf = self._target_vnf
        if not vnf:
            self._svc_vnf_lbl.configure(text="VNF: (nenhum selecionado)")
            self._svc_type_lbl.configure(text="Tipo: \u2014")
            self._svc_cat_cb.configure(values=["Todas as Categorias"])
            self._svc_cat_var.set("Todas as Categorias")
            self._svc_listbox.insert("end", "  Selecione um VNF na aba Topologia")
            self._clear_detail_panel()
            return

        vnf_type = vnf.type.upper()
        host_info = f"{vnf.host}:{vnf.port}" if self._admin_authenticated else vnf.host
        self._svc_vnf_lbl.configure(
            text=f"VNF: {vnf.name} ({host_info})")
        self._svc_type_lbl.configure(
            text=f"Tipo: {VNF_TYPES.get(vnf_type, vnf_type)}")
        self._svc_status_lbl.configure(
            text=f"Status: {vnf.status}",
            fg={"online": NEON_CYAN, "offline": "#ff4d4d",
                "unknown": NEON_AMBER}.get(vnf.status, NEON_AMBER))

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
        for w in self._svc_detail_frame.winfo_children():
            w.destroy()
        self._svc_param_entries.clear()
        self._svc_current_svc = None

    def _show_service_detail(self, svc: ServiceDef) -> None:
        self._clear_detail_panel()
        p = self._svc_detail_frame

        mode_label = "Configurando" if svc.config_mode else "Executando"
        tk.Label(p, text=f"{mode_label}: {svc.name}", bg=BG_INPUT,
                 fg=NEON_AMBER if svc.config_mode else NEON_CYAN,
                 font=FONT_LARGE_B).pack(anchor="w", pady=(0, 4))

        tk.Label(p, text=f"Categoria: {svc.category}", bg=BG_INPUT,
                 fg=NEON_PURP, font=FONT_SMALL).pack(anchor="w", pady=(0, 2))

        cmd_frame = tk.Frame(p, bg=BG_INPUT,
                             highlightthickness=1, highlightbackground=BORDER_NRM)
        cmd_frame.pack(fill="x", pady=(0, 8))
        tk.Label(cmd_frame, text=svc.description, bg=BG_INPUT,
                 fg=FG_CODE, font=FONT_BODY, anchor="w",
                 wraplength=500).pack(fill="x", padx=8, pady=6)

        if svc.config_mode:
            self._build_param_fields(p, svc)

        abar = tk.Frame(p, bg=BG_INPUT)
        abar.pack(fill="x", pady=(4, 0))
        action_button(abar, f"\u25b6 {mode_label}",
                      lambda s=svc: self._run_service(s),
                      NEON_CYAN).pack(side="left", padx=(0, 6))
        action_button(abar, "\u2716  Limpar output",
                      lambda: self._write(self._svc_output, ""),
                      NEON_PURP).pack(side="left")

    def _build_param_fields(self, parent: tk.Frame, svc: ServiceDef) -> None:
        params = parse_params(svc)
        if not params:
            return

        pf = tk.Frame(parent, bg=BG_INPUT,
                      highlightthickness=1, highlightbackground=BORDER_NRM)
        pf.pack(fill="x", pady=(0, 8))

        tk.Label(pf, text="PARÂMETROS", bg=BG_INPUT, fg=FG_DIM,
                 font=FONT_SMALL_B).pack(anchor="w", padx=8, pady=(4, 2))

        self._svc_param_entries.clear()
        for label, default in params:
            row = tk.Frame(pf, bg=BG_INPUT)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=f"{label}:", bg=BG_INPUT, fg=FG_DIM,
                     font=FONT_BODY, width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            entry = tk.Entry(row, textvariable=var, bg=BG_BASE, fg=NEON_CYAN,
                             font=FONT_MEDIUM, relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=BORDER_NRM)
            entry.pack(side="left", fill="x", expand=True, ipady=3)
            self._svc_param_entries[label] = entry

    def _run_service(self, svc: ServiceDef) -> None:
        mode = self._svc_mode_var.get()
        vnf = self._target_vnf
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if vnf:
            label += f"  |  Alvo: {vnf.name} ({vnf.host})"
        self._svc_vnf_lbl.configure(text=label)

        final_svc = svc
        if svc.config_mode and self._svc_param_entries:
            cmd = svc.description
            for name, entry in self._svc_param_entries.items():
                cmd = cmd.replace(f"<{name}>", entry.get().strip())
            final_svc = ServiceDef(
                id=svc.id, name=svc.name, description=svc.description,
                category=svc.category, vnf_types=svc.vnf_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        def _do():
            self._loading(self._svc_output, f"Executando: {svc.name} ({mode})\u2026")

            if mode == "mock":
                result = execute_service(final_svc, session_type="mock")
                self._write(self._svc_output, result)
                return

            if not self.session.is_connected:
                self._write(self._svc_output,
                    "\u2718  Sem sessao SSH ativa. Conecte-se primeiro.")
                return

            if mode == "cli":
                result = execute_service(final_svc, session_type="cli",
                                         session=self.session._conn)
                self._write(self._svc_output, result)
                return

            self._write(self._svc_output, f"Modo desconhecido: {mode}")

        self._spawn(_do)

    # ══════════════════════════════════════════════════════════════════
    #  NAVEGACAO
    # ══════════════════════════════════════════════════════════════════
    def _show_page(self, key: str) -> None:
        if self._active_btn:
            self._active_btn._deactivate()  # type: ignore[attr-defined]
        if key not in self.pages:
            fn = self._page_builders.get(key)
            if fn:
                fn()
        target = self.pages.get(key)
        if target:
            target.master.lift()
        btn = self._nav_buttons.get(key)
        if btn:
            btn._activate()  # type: ignore[attr-defined]
            self._active_btn = btn

    def _tick_clock(self) -> None:
        self.clock_lbl.configure(
            text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _set_status(self, text: str, color: str) -> None:
        self.status_dot.configure(fg=color)
        self.status_lbl.configure(text=text)

    def _set_conn_btn(self, text: str = "  CONECTAR  ", disabled: bool = False) -> None:
        state = "disabled" if disabled else "normal"
        self.root.after(0, lambda: self.conn_btn.configure(text=text, state=state))

    # ══════════════════════════════════════════════════════════════════
    #  CONEXAO SSH (Netmiko)
    # ══════════════════════════════════════════════════════════════════
    def _get_selected_vnf(self) -> VNF | None:
        return (self._topo_canvas.get_selected()
                if self._topo_canvas else None) or self._target_vnf

    def _toggle_connect(self) -> None:
        if self.session.is_connected:
            self.session.disconnect()
            self._set_status("Desconectado", NEON_PURP)
            self._set_conn_btn()
            return

        vnf = self._get_selected_vnf()
        if vnf:
            self._connect_with_vnf(vnf)
        else:
            self._connect_default()

    def _do_connect(self, on_success_fmt: str, on_error_msg: str) -> None:
        def _do():
            try:
                self.session.connect()
                sid = self.session._session_id or "?"
                self.root.after(0, lambda: self._set_status(
                    on_success_fmt.format(sid=sid), NEON_CYAN))
                self._set_conn_btn("  DESCONECTAR  ")
            except NetmikoAuthenticationException:
                self.root.after(0, lambda: self._set_status(
                    "Falha de autenticacao", NEON_AMBER))
                self._set_conn_btn()
            except NetmikoTimeoutException:
                self.root.after(0, lambda: self._set_status(
                    "Timeout de conexao", NEON_AMBER))
                self._set_conn_btn()
            except ValueError as exc:
                msg = f"Config: {exc}"
                self.root.after(0, lambda m=msg: self._set_status(m, NEON_AMBER))
                self._set_conn_btn()
            except Exception as exc:
                log.exception("Falha inesperada em _do_connect: %s", exc)
                self.root.after(0, lambda: self._set_status(
                    on_error_msg, NEON_AMBER))
                self._set_conn_btn()

        self._spawn(_do)

    def _connect_default(self) -> None:
        self._set_status("Conectando SSH\u2026", NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect("SSH \u2714  {sid}", "Erro ao conectar")

    def _connect_with_vnf(self, vnf: VNF) -> None:
        if self.session.is_connected:
            self.session.disconnect()
        self.session.override_host = vnf.host
        self.session.override_port = vnf.port
        self.session.override_username = vnf.username or None
        self.session.override_password = vnf.password or None
        self.session.override_ssh_key = vnf.ssh_key or None
        self._set_status(f"Conectando ao VNF {vnf.name}\u2026", NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect(f"VNF \u2714  {vnf.name}  {{sid}}", "Erro ao conectar ao VNF")

    def _spawn(self, fn, *args) -> None:
        self._executor.submit(fn, *args)

    def _run(self, func) -> None:
        if not self.session.is_connected:
            messagebox.showwarning("Aviso", "Conecte ao roteador primeiro.")
            return
        self._spawn(func)

    def _write(self, widget: scrolledtext.ScrolledText, text: str) -> None:
        self.root.after(0, lambda: (
            widget.configure(state="normal"),
            widget.delete("1.0", "end"),
            widget.insert("end", text),
            widget.configure(state="disabled")))

    def _loading(self, widget: scrolledtext.ScrolledText, msg: str) -> None:
        self.root.after(0, lambda: (
            widget.configure(state="normal"),
            widget.delete("1.0", "end"),
            widget.insert("end", f"\u23f3  {msg}\n"),
            widget.configure(state="disabled")))

    # ══════════════════════════════════════════════════════════════════
    #  FETCH METHODS
    # ══════════════════════════════════════════════════════════════════
    def _fetch_config(self) -> None:
        self._loading(self.out_config, "Carregando configuracao atual\u2026")
        self._write(self.out_config, self.session.run_cli_rpc("display current-configuration"))

    def _fetch_route(self) -> None:
        label_to_key = {v: k for k, v in ROUTE_FILTER_LABELS.items()}
        fkey = label_to_key.get(self.route_filter_var.get(), "routing")
        cmd  = CLI_FILTERS.get(fkey, "display ip routing-table")
        self._loading(self.out_route, f"Executando: {cmd}\u2026")
        self._write(self.out_route, self.session.run_cli_rpc(cmd or ""))

    def _fetch_arp(self) -> None:
        self._loading(self.out_arp, "Executando: display arp\u2026")
        self._write(self.out_arp, self.session.run_cli_rpc("display arp"))

    def _fetch_info(self) -> None:
        self._loading(self.out_info, "Coletando informacoes do sistema\u2026")
        buf = io.StringIO()
        commands = [
            ("Versao / Sistema", "display version"),
            ("Dispositivo", "display device"),
            ("Licenca", "display license"),
            ("CPU", "display cpu-usage"),
            ("Memoria", "display memory-usage"),
            ("Interfaces", "display interface brief"),
            ("LLDP", "display lldp neighbor brief"),
        ]
        for title, cmd in commands:
            buf.write(f"{'=' * 70}\n\u25b6  {title}\n{'-' * 70}\n")
            buf.write(self.session.run_cli_rpc(cmd or ""))
            buf.write("\n\n")
        self._write(self.out_info, buf.getvalue())

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR
    # ══════════════════════════════════════════════════════════════════
    def _on_tpl_select(self, _event=None) -> None:
        sel = self._tpl_listbox.curselection()
        if not sel:
            return
        name = self._tpl_listbox.get(sel[0])
        cmd  = self._tpl_cmd_map.get(name, name) or ""
        self._cmd_editor.delete("1.0", "end")
        self._cmd_editor.insert("end", cmd)

    def _get_editor_cmd(self) -> str:
        return self._cmd_editor.get("1.0", "end").strip()

    def _exec_cmd(self) -> None:
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd, "\u2718  Editor vazio \u2014 digite um comando")
            return
        if self._sysview_var.get():
            self._loading(self.out_cmd,
                          "system-view \u2192 " + cmd.splitlines()[0] + " \u2192 quit\u2026")
            self.session.run_cli_timing("system-view")
            result = self.session.run_cli_timing(cmd)
            self.session.run_cli_timing("quit")
        else:
            self._loading(self.out_cmd, f"Executando: {cmd}\u2026")
            result = self.session.run_cli_rpc(cmd or "")
        self._write(self.out_cmd, result)

    def _exec_config(self) -> None:
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd,
                         "\u2718  Editor vazio \u2014 digite os comandos de configuracao")
            return
        self._loading(self.out_cmd, "Aplicando configuracao\u2026")
        ok, msg = self.session.edit_config(cmd)
        self._write(self.out_cmd, msg)

    # ══════════════════════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════════════════════
    def _do_backup(self) -> None:
        fmt = self.backup_fmt.get()
        self._loading(self.out_backup, "Coletando configuracao para backup\u2026")
        conteudo = self.session.run_cli_rpc("display current-configuration")
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext  = "txt"
        host = self.session._host
        nome = f"backup_{host}_{ts}.{ext}"
        pasta = self.backup_path.get().strip() or os.path.expanduser("~")
        path  = os.path.join(pasta, nome)
        try:
            os.makedirs(pasta, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                header = (
                    f"# Backup CLI\n"
                    f"# Host   : {host}\n"
                    f"# User   : {self.session._user}\n"
                    f"# Data   : {ts}\n\n"
                )
                fh.write(header + conteudo)
            linhas = conteudo.count("\n") + 1
            resumo = (
                f"\u2714  Backup concluido!\n{'-' * 60}\n"
                f"  Arquivo  : {path}\n"
                f"  Formato  : {fmt}\n"
                f"  Data     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"  Linhas   : {linhas}\n"
                f"  Tamanho  : {os.path.getsize(path):,} bytes\n"
                f"{'-' * 60}\n\nPrevia (40 linhas):\n\n"
                + "\n".join(conteudo.splitlines()[:40])
            )
            self._write(self.out_backup, resumo)
            self.root.after(0, lambda: self._set_status(f"Backup: {nome}", NEON_CYAN))
            audit.log_operation("backup", user=self.session._user,
                                host=host, status="ok", file=path)
            log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
        except OSError as ex:
            log.error("Backup falhou: %s", ex)
            self._write(self.out_backup, f"\u2718  Erro ao salvar:\n  {ex}")

    def _choose_backup_dir(self) -> None:
        d = filedialog.askdirectory(title="Escolha o diretorio",
                                    initialdir=self.backup_path.get())
        if d:
            self.backup_path.set(d)

    # ══════════════════════════════════════════════════════════════════
    #  TOPOLOGIA / VNFs
    # ══════════════════════════════════════════════════════════════════
    def _init_topology_backend(self) -> None:
        use_mock = not NCE_HOST
        self._nce_ctrl = NorthboundController(
            host=NCE_HOST, port=NCE_PORT,
            username=NCE_USER, password=NCE_PASS,
            verify_ssl=NCE_VERIFY_SSL,
            use_mock=use_mock,
        )
        log.info("Topology backend: mock=%s", use_mock)
        log.debug("Topology backend: mock=%s host=%s", use_mock, NCE_HOST or "(local)")

    def _refresh_vnfs(self) -> None:
        vnfs = load_vnf_inventory()
        self.root.after(0, lambda: self._update_vnfs_ui(vnfs))
        self.root.after(0, lambda: self._nce_status_lbl.configure(
            text=("Inventario: {} dispositivos  \u2022  {}"
                       .format(len(vnfs), datetime.datetime.now().strftime('%H:%M:%S')))
        ) if hasattr(self, "_nce_status_lbl") else None)

    def _update_vnfs_ui(self, vnfs: list[VNF]) -> None:
        self._vnfs = vnfs
        if self._topo_canvas:
            self._topo_canvas.set_admin(self._admin_authenticated)
            self._topo_canvas.update_vnfs(vnfs)

    # ── Admin ─────────────────────────────────────────────────────────
    def _show_admin_login(self) -> None:
        if self._admin_authenticated:
            self._admin_authenticated = False
            if self._topo_canvas:
                self._topo_canvas.set_admin(False)
            self._admin_btn.configure(text="\U0001f512  Admin")
            self._update_vnfs_ui(self._vnfs)
            return

        now = datetime.datetime.now().timestamp()
        if now < self._admin_locked_until:
            remaining = int(self._admin_locked_until - now)
            messagebox.showwarning(
                "Admin Bloqueado",
                f"Tentativas excedidas. Aguarde {remaining}s e tente novamente.")
            return

        admin_pw = _secrets.get("ADMIN_PASSWORD", "")
        if not admin_pw:
            self._admin_authenticated = True
            if self._topo_canvas:
                self._topo_canvas.set_admin(True)
            self._admin_btn.configure(text="\U0001f513  Admin")
            self._update_vnfs_ui(self._vnfs)
            log.info("Admin: autenticado (sem senha definida)")
            return

        win = tk.Toplevel(self.root)
        win.title("Autenticacao Admin")
        win.geometry("360x180")
        win.configure(bg=BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Senha Mestra", bg=BG_CARD, fg=NEON_CYAN,
                 font=FONT_XLARGE_B).pack(pady=(16, 8))

        pw_var = tk.StringVar()
        entry = tk.Entry(win, textvariable=pw_var, show="*",
                         bg=BG_INPUT, fg=NEON_CYAN, insertbackground=NEON_CYAN,
                         font=FONT_XLARGE, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=BORDER_NRM)
        entry.pack(padx=24, fill="x", pady=(0, 12))
        entry.focus_set()

        def _verify():
            nonlocal now
            if pw_var.get() == admin_pw:
                self._admin_authenticated = True
                self._admin_attempts = 0
                if self._topo_canvas:
                    self._topo_canvas.set_admin(True)
                self._admin_btn.configure(text="\U0001f513  Admin")
                self._update_vnfs_ui(self._vnfs)
                win.destroy()
                log.info("Admin: autenticado com sucesso")
            else:
                self._admin_attempts += 1
                remaining = self.ADMIN_MAX_ATTEMPTS - self._admin_attempts
                if remaining <= 0:
                    self._admin_locked_until = \
                        datetime.datetime.now().timestamp() + self.ADMIN_LOCKOUT_SECS
                    self._admin_attempts = 0
                    win.destroy()
                    messagebox.showerror(
                        "Admin Bloqueado",
                        f"Senha incorreta. Acesso bloqueado por "
                        f"{self.ADMIN_LOCKOUT_SECS}s.")
                    log.warning("Admin: lockout por %ds", self.ADMIN_LOCKOUT_SECS)
                else:
                    messagebox.showerror(
                        "Admin",
                        f"Senha incorreta. {remaining} tentativa(s) restante(s).")
                    pw_var.set("")
                    entry.focus_set()

        action_button(win, "Autenticar", _verify, NEON_CYAN).pack(pady=8)
        entry.bind("<Return>", lambda _: _verify())
        win.bind("<Escape>", lambda _: win.destroy())

    # ── Device Dialog ────────────────────────────────────────────────
    def _show_device_dialog(self, vnf: VNF | None = None) -> None:
        editing = vnf is not None
        vnf = vnf or VNF(id="", name="", host="")

        win = tk.Toplevel(self.root)
        win.title("Editar Dispositivo" if editing else "Cadastrar Dispositivo")
        win.geometry("500x480")
        win.configure(bg=BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        fields = [
            ("host", "IP / Host", vnf.host),
            ("port", "Porta SSH", str(vnf.port)),
            ("username", "Usuario SSH", vnf.username),
            ("password", "Senha SSH", vnf.password, True),
            ("ssh_key", "Chave SSH (path)", vnf.ssh_key),
            ("location", "Localizacao", vnf.location),
        ]

        row_frame = tk.Frame(win, bg=BG_CARD)
        row_frame.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(row_frame, text="Nome:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        name_var = tk.StringVar(value=vnf.name)
        tk.Entry(row_frame, textvariable=name_var, bg=BG_INPUT,
                 fg=NEON_CYAN, font=FONT_MEDIUM, relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=BORDER_NRM).pack(
                     side="left", fill="x", expand=True, ipady=4)

        row_frame2 = tk.Frame(win, bg=BG_CARD)
        row_frame2.pack(fill="x", padx=20, pady=(4, 12))
        tk.Label(row_frame2, text="Tipo:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        type_var = tk.StringVar(value=vnf.type)
        type_cb = ttk.Combobox(row_frame2, textvariable=type_var,
                               values=list(VNF_TYPES.keys()),
                               state="readonly", width=18, font=FONT_BODY)
        type_cb.pack(side="left", fill="x", expand=True)

        vars_dict: dict[str, tk.StringVar] = {"name": name_var, "type": type_var}
        secret_vars: dict[str, tk.StringVar] = {}

        for fname, flabel, *rest in fields:
            is_secret = len(rest) > 1 and rest[1] is True
            default = rest[0]
            fr = tk.Frame(win, bg=BG_CARD)
            fr.pack(fill="x", padx=20, pady=3)
            tk.Label(fr, text=f"{flabel}:", bg=BG_CARD, fg=FG_DIM,
                     font=FONT_BODY).pack(side="left", padx=(0, 8))
            var = tk.StringVar(value=default)
            show_char = "*" if is_secret else ""
            entry = tk.Entry(fr, textvariable=var, show=show_char,
                             bg=BG_INPUT, fg=NEON_CYAN, font=FONT_MEDIUM,
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=BORDER_NRM)
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            vars_dict[fname] = var

            if is_secret:
                secret_vars[fname] = var
                def _toggle(e=None, ev=var, en=entry):
                    en.configure(show="" if en.cget("show") == "*" else "*")
                btn = tk.Label(fr, text="\U0001f441", bg=BG_CARD, fg=NEON_PURP,
                               font=FONT_XLARGE, cursor="hand2")
                btn.pack(side="left", padx=(4, 0))
                btn.bind("<Button-1>", _toggle)

        def _save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Validacao", "Nome e obrigatorio.")
                return
            host = vars_dict["host"].get().strip()
            if not host:
                messagebox.showwarning("Validacao", "IP/Host e obrigatorio.")
                return

            try:
                port_val = int(vars_dict["port"].get().strip() or "22")
            except ValueError:
                port_val = 22

            vnfs = load_vnf_inventory()
            if editing:
                new_vnf = VNF(
                    id=vnf.id, name=name,
                    host=host, port=port_val,
                    type=type_var.get(),
                    username=vars_dict["username"].get().strip(),
                    password=vars_dict["password"].get().strip(),
                    ssh_key=vars_dict["ssh_key"].get().strip(),
                    location=vars_dict["location"].get().strip(),
                )
                for i, v in enumerate(vnfs):
                    if v.id == vnf.id:
                        vnfs[i] = new_vnf
                        break
                else:
                    vnfs.append(new_vnf)
            else:
                new_id = f"vnf-{len(vnfs) + 1:03d}-{name.lower().replace(' ', '-')}"
                new_vnf = VNF(
                    id=new_id, name=name,
                    host=host, port=port_val,
                    type=type_var.get(),
                    username=vars_dict["username"].get().strip(),
                    password=vars_dict["password"].get().strip(),
                    ssh_key=vars_dict["ssh_key"].get().strip(),
                    location=vars_dict["location"].get().strip(),
                )
                vnfs.append(new_vnf)

            save_vnf_inventory(vnfs)
            win.destroy()
            self._spawn(self._refresh_vnfs)

        bar = tk.Frame(win, bg=BG_CARD)
        bar.pack(fill="x", padx=20, pady=(16, 12))
        action_button(bar, "\U0001f4be  Salvar", _save, NEON_CYAN).pack(side="left", padx=(0, 8))
        action_button(bar, "\u2716  Cancelar", win.destroy, NEON_PURP).pack(side="left")

    def _delete_device(self, vnf: VNF) -> None:
        if not messagebox.askyesno("Excluir",
                                    f"Confirmar exclusao de {vnf.name} ({vnf.host})?"):
            return
        vnfs = load_vnf_inventory()
        vnfs = [v for v in vnfs if v.id != vnf.id]
        save_vnf_inventory(vnfs)
        if self._target_vnf and self._target_vnf.id == vnf.id:
            self._clear_vnf_target()
        self._spawn(self._refresh_vnfs)

    def _on_vnf_selected(self, vnf: VNF) -> None:
        self._target_vnf = vnf
        info = f"{vnf.name} ({vnf.host})"
        if self._admin_authenticated:
            info += f":{vnf.port}"
        if self._admin_authenticated and vnf.username:
            info += f"  user:{vnf.username}"
        if hasattr(self, "_vnf_info_lbl"):
            self._vnf_info_lbl.configure(
                text=f"  Selecionado: {info}", fg=NEON_CYAN)
        self._vnf_target_lbl.configure(text=info)
        log.info("VNF selecionado: %s", info)
        self._refresh_service_list()

    def _clear_vnf_target(self) -> None:
        self._target_vnf = None
        self.session.override_host = None
        self.session.override_port = None
        self.session.override_username = None
        self.session.override_password = None
        self.session.override_ssh_key = None
        if self._topo_canvas:
            self._topo_canvas.deselect()
        self._vnf_target_lbl.configure(text="(roteador padrao)")
        if hasattr(self, "_vnf_info_lbl"):
            self._vnf_info_lbl.configure(
                text="  Nenhum VNF selecionado", fg=FG_DIM)
        if self.session.is_connected:
            self.session.disconnect()
            self._set_status("Desconectado", NEON_PURP)
            self._set_conn_btn()
        self._refresh_service_list()

    def _on_close(self) -> None:
        self.session.disconnect()
        self.root.destroy()
