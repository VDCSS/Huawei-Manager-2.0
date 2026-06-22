#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import datetime
import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox

import huawei_manager.constants as C
from agents.watcher import Watcher
from huawei_manager._config import PROJECT_ROOT, _secrets, audit
from huawei_manager.constants import (
    FONT_BODY,
    FONT_H1,
    FONT_H2_B,
    FONT_HERO_B,
    FONT_MEDIUM_B,
    FONT_SMALL,
    FONT_XSMALL,
    set_theme,
)
from huawei_manager.handlers import EventHandlers
from huawei_manager.pages import PageBuilder
from huawei_manager.session import NetmikoSession
from huawei_manager.topology import VNF, TopologyCanvas
from huawei_manager.widgets import action_button, neon_button


class AppCore:
    """Mixin principal — inicializa janela, layout, navegação e helpers de threading."""

    def __init__(self, root: tk.Tk) -> None:
        """Inicializa a janela Tkinter, sessão SSH, fila de UI, watcher e constrói o layout."""
        self.root = root
        self.root.title("HUAWEI MANAGER")
        self.root.geometry("1220x740")
        self.root.configure(bg=C.BG_BASE)
        self.root.resizable(True, True)
        try:
            icon_path = PROJECT_ROOT / "share" / "icons" / "huawei-manager.png"
            if icon_path.exists():
                img = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, img)
        except Exception:
            pass

        self.session = NetmikoSession(_secrets, audit)
        self._active_btn: tk.Frame | None = None
        self._access_level: str = "user"
        self._mock_mode: bool = False
        self._vnfs_busy: bool = False
        self._theme: str = "dark"

        self._admin_attempts = 0
        self._admin_locked_until: float = 0

        self._target_vnf: VNF | None = None
        self._vnfs: list[VNF] = []
        self._topo_canvas: TopologyCanvas | None = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hw")
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._watcher = Watcher(self.root, self._on_watcher_update)
        self._watcher_results: list | None = None

        self._current_page: str | None = None
        self._PAGE_KEYS = ["home", "topology", "config", "route", "arp",
                           "info", "cmd", "backup", "manutencao", "services"]

        self._poll_queue()
        self._build_layout()
        self._setup_bindings()
        self._show_page("home")
        self._tick_clock()
        self._tick_dashboard()
        self._tick_vnfs()
        self._init_topology_backend()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ───────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        """Constrói sidebar, header, content area e footer da janela principal."""
        self.sidebar = tk.Frame(self.root, bg=C.BG_SIDEBAR, width=228)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        right = tk.Frame(self.root, bg=C.BG_BASE)
        right.pack(side="left", fill="both", expand=True)

        self._build_header(right)
        tk.Frame(right, bg=C.BORDER_NRM, height=1).pack(fill="x")

        self.content = tk.Frame(right, bg=C.BG_BASE)
        self.content.pack(fill="both", expand=True, padx=18, pady=18)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        self._build_sidebar()
        self._build_footer()

        self.pages: dict[str, tk.Frame] = {}
        self._page_builders = {
            "home":     self._build_home_page,
            "config":   self._build_config_page,
            "route":    self._build_route_page,
            "arp":      self._build_arp_page,
            "info":     self._build_info_page,
            "cmd":      self._build_cmd_page,
            "backup":   self._build_backup_page,
            "topology":    self._build_topology_page,
            "services":    self._build_services_page,
            "manutencao":  self._build_manutencao_page,
        }

    # ── Header ───────────────────────────────────────────────────────
    def _build_header(self, parent) -> None:
        """Constrói o cabeçalho com logo, indicador de status e botão de tema."""
        hdr = tk.Frame(parent, bg=C.BG_BASE, height=56)
        hdr.pack(fill="x", padx=18, pady=(10, 6))
        hdr.pack_propagate(False)

        tk.Label(hdr, text="HUAWEI",  bg=C.BG_BASE, fg=C.NEON_CYAN,
                 font=FONT_HERO_B).pack(side="left")
        tk.Label(hdr, text=" MANAGER", bg=C.BG_BASE, fg=C.FG_MAIN,
                 font=FONT_HERO_B).pack(side="left")


        badge = tk.Frame(hdr, bg=C.BG_BASE)
        badge.pack(side="right")

        self.status_dot = tk.Label(badge, text="\u25cf", bg=C.BG_BASE, fg=C.NEON_PURP,
                                   font=FONT_H1)
        self.status_dot.pack(side="left", padx=(0, 4))
        self.status_lbl = tk.Label(badge, text="Desconectado", bg=C.BG_BASE, fg=C.FG_DIM,
                                   font=FONT_BODY)
        self.status_lbl.pack(side="left", padx=(0, 12))
        self.conn_btn = action_button(badge, "  CONECTAR  ",
                                       self._toggle_connect, C.NEON_CYAN)
        self.conn_btn.pack(side="left")
        self.theme_btn = action_button(badge, "\u263c", self._toggle_theme, C.NEON_PURP)
        self.theme_btn.pack(side="left", padx=(6, 0))

    # ── Sidebar ──────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        """Constrói a barra lateral com botões de navegação e label do VNF alvo."""
        logo = tk.Frame(self.sidebar, bg=C.BG_SIDEBAR)
        logo.pack(fill="x", pady=(18, 8))
        tk.Label(logo, text="[ MODULOS ]", bg=C.BG_SIDEBAR,
                 fg=C.FG_DIM, font=FONT_SMALL).pack(padx=16, anchor="w")
        tk.Frame(self.sidebar, bg=C.BORDER_NRM, height=1).pack(fill="x", padx=16, pady=6)

        self._nav_buttons: dict[str, tk.Frame] = {}
        items = (
            ("home",     "\U0001f3e0", "Dashboard",            C.NEON_CYAN),
            ("topology", "\U0001f5fa", "Topologia / VNFs",     C.NEON_AMBER),
            ("config",   "\U0001f4cb", "Config Atual",       C.NEON_CYAN),
            ("route",    "\U0001f310", "Roteamento",          C.NEON_CYAN),
            ("arp",      "\U0001f4e1", "Tabela ARP",           C.NEON_CYAN),
            ("info",     "\U0001f4bb", "Info do Sistema",      C.NEON_MAG),
            ("cmd",      "\u2328",  "Editor de Comandos",       C.NEON_MAG),
            ("backup",   "\U0001f4be", "Backup",               C.NEON_PURP),
            ("services",    "\u26a1",  "Servicos",       C.NEON_AMBER),
            ("manutencao",  "\U0001f6e0", "Manutencao",   C.NEON_MAG),
        )
        for key, icon, label, color in items:
            btn = neon_button(self.sidebar, label,
                              lambda k=key: self._show_page(k),
                              color=color, icon=icon)
            btn.pack(fill="x", pady=1)
            self._nav_buttons[key] = btn

        tk.Frame(self.sidebar, bg=C.BORDER_NRM, height=1).pack(
            fill="x", padx=16, pady=(16, 4))
        tk.Label(self.sidebar, text="ALVO VNF", bg=C.BG_SIDEBAR,
                 fg=C.FG_DIM, font=FONT_BODY).pack(padx=16, anchor="w")
        self._vnf_target_lbl = tk.Label(
            self.sidebar, text="(roteador padrao)", bg=C.BG_SIDEBAR,
            fg=C.NEON_AMBER, font=FONT_MEDIUM_B, wraplength=180)
        self._vnf_target_lbl.pack(padx=16, anchor="w")

    # ── Footer ───────────────────────────────────────────────────────
    def _build_footer(self) -> None:
        """Constrói o rodapé com créditos e relógio."""
        foot = tk.Frame(self.root, bg=C.BG_SIDEBAR, height=22)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot,
                 text="Huawei Manager  \u2022  v2.0.0",
                 bg=C.BG_SIDEBAR, fg=C.FG_DIM, font=FONT_XSMALL).pack(side="left", padx=12)
        self.clock_lbl = tk.Label(foot, bg=C.BG_SIDEBAR, fg=C.NEON_PURP,
                                  font=FONT_XSMALL)
        self.clock_lbl.pack(side="right", padx=12)

    # ── Helpers de pagina ─────────────────────────────────────────────
    def _make_page(self, key: str) -> tk.Frame:
        """Cria um novo frame de página dentro do content grid."""
        f = tk.Frame(self.content, bg=C.BG_CARD,
                     highlightthickness=1, highlightbackground=C.BORDER_NRM)
        f.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(f, bg=C.BG_CARD)
        inner.pack(fill="both", expand=True, padx=18, pady=18)
        self.pages[key] = inner
        return inner

    def _page_title(self, parent, text, color, subtitle="") -> None:
        """Cria um título estilizado com barra colorida e subtítulo opcional."""
        row = tk.Frame(parent, bg=C.BG_CARD)
        row.pack(fill="x", pady=(0, 14))
        tk.Frame(row, bg=color, width=4).pack(side="left", fill="y", padx=(0, 10))
        col = tk.Frame(row, bg=C.BG_CARD)
        col.pack(side="left")
        tk.Label(col, text=text.upper(), bg=C.BG_CARD, fg=color,
                 font=FONT_H2_B).pack(anchor="w")
        if subtitle:
            tk.Label(col, text=subtitle, bg=C.BG_CARD, fg=C.FG_DIM,
                     font=FONT_SMALL).pack(anchor="w")

    # ── Navegacao ────────────────────────────────────────────────────
    def _show_page(self, key: str) -> None:
        """Alterna para a página identificada por *key*, reconstruindo se necessário."""
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
        self._current_page = key

    def _rebuild_page(self, key: str) -> None:
        """Destrói e recria a página *key* do cache, mantendo a navegação atual."""
        if key in self.pages:
            self.pages[key].master.destroy()
            del self.pages[key]
        if self._current_page == key:
            self._show_page(key)

    def _tick_clock(self) -> None:
        """Atualiza o relógio no rodapé a cada 1 segundo."""
        self.clock_lbl.configure(
            text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _tick_dashboard(self) -> None:
        """Atualiza o dashboard a cada 5 segundos se a página inicial estiver ativa."""
        if self._current_page == "home":
            self._refresh_dashboard()
        self.root.after(5000, self._tick_dashboard)

    def _tick_vnfs(self) -> None:
        """Atualiza o status das VNFs a cada 30 segundos nas páginas de topologia/home."""
        if self._current_page in ("home", "topology"):
            self._spawn(self._refresh_vnfs)
        self.root.after(30000, self._tick_vnfs)

    def _set_status(self, text: str, color: str) -> None:
        """Atualiza o indicador de status (bolinha + texto) no header."""
        self.status_dot.configure(fg=color)
        self.status_lbl.configure(text=text)

    def _set_conn_btn(self, text: str = "  CONECTAR  ", disabled: bool = False) -> None:
        """Altera o texto/estado do botão de conexão de forma thread-safe."""
        state = "disabled" if disabled else "normal"
        self._dispatch(lambda: self.conn_btn.configure(text=text, state=state))

    # ── Tema ──────────────────────────────────────────────────────────
    def _toggle_theme(self) -> None:
        """Alterna entre tema claro e escuro e reconstrói a interface."""
        self._theme = "light" if self._theme == "dark" else "dark"
        set_theme(self._theme)
        self._rebuild_ui()
        icon = "\u263c" if self._theme == "dark" else "\u263e"
        self.theme_btn.configure(text=icon)

    def _rebuild_ui(self) -> None:
        """Destrói toda a UI e reconstrói do zero, preservando a página atual."""
        current_page = self._current_page
        self._active_btn = None          # botão antigo foi destruído
        self._topo_canvas = None          # canvas antigo foi destruído
        for child in list(self.root.winfo_children()):
            child.destroy()
        self._build_layout()
        self._rebuild_page(current_page or "home")

    # ── Atalhos de teclado ─────────────────────────────────────────────
    def _setup_bindings(self) -> None:
        """Registra todos os atalhos de teclado (Enter, Ctrl+*, F5, Escape)."""
        self.root.bind("<Return>", self._on_enter)
        self.root.bind("<Control-Shift-Return>", self._on_ctrl_shift_enter)
        self.root.bind("<Control-d>", self._on_ctrl_d)
        self.root.bind("<Control-l>", self._on_ctrl_l)
        self.root.bind("<Control-q>", self._on_ctrl_q)
        self.root.bind("<Control-Shift-A>", self._on_ctrl_shift_a)
        self.root.bind("<F5>", self._on_f5)
        self.root.bind("<Control-Tab>", self._on_ctrl_tab)
        self.root.bind("<Control-Shift-Tab>", self._on_ctrl_shift_tab)
        self.root.bind("<Escape>", self._on_escape)
        for i, key in enumerate(self._PAGE_KEYS[:9], 1):
            self.root.bind(f"<Control-Key-{i}>", lambda e, k=key: self._show_page(k))

    def _on_enter(self, event=None) -> None:
        """Executa a ação principal da página atual (Enter)."""
        focus = self.root.focus_get()
        if isinstance(focus, tk.Text):
            return
        page = self._current_page
        if page == "config":
            self._run(self._fetch_config)
        elif page == "route":
            self._run(self._fetch_route)
        elif page == "arp":
            self._run(self._fetch_arp)
        elif page == "info":
            self._run(self._fetch_info)
        elif page == "cmd":
            cmd = self._get_editor_cmd()
            if cmd:
                self._run(self._exec_cmd)
        elif page == "backup":
            self._run(self._do_backup)

    def _on_ctrl_shift_enter(self, event=None) -> None:
        """Envia comando como configuracao (Ctrl+Shift+Enter) na pagina Cmd."""
        if self._current_page == "cmd":
            self._run(self._exec_config)

    def _on_ctrl_d(self, event=None) -> None:
        """Alterna conexao SSH (Ctrl+D)."""
        self._toggle_connect()

    def _on_ctrl_l(self, event=None) -> None:
        """Limpa o widget de output da página atual (Ctrl+L)."""
        page = self._current_page
        if page == "config" and hasattr(self, "out_config"):
            self._write(self.out_config, "")
        elif page == "route" and hasattr(self, "out_route"):
            self._write(self.out_route, "")
        elif page == "arp" and hasattr(self, "out_arp"):
            self._write(self.out_arp, "")
        elif page == "info" and hasattr(self, "out_info"):
            self._write(self.out_info, "")
        elif page == "cmd" and hasattr(self, "out_cmd"):
            self._write(self.out_cmd, "")
        elif page == "backup" and hasattr(self, "out_backup"):
            self._write(self.out_backup, "")
        elif page == "services" and hasattr(self, "_svc_output"):
            self._write(self._svc_output, "")

    def _on_ctrl_q(self, event=None) -> None:
        """Fecha a aplicacao (Ctrl+Q)."""
        self._on_close()

    def _on_ctrl_shift_a(self, event=None) -> None:
        """Abre/fecha o dialogo de autenticacao (Ctrl+Shift+A)."""
        self._show_auth_dialog()

    def _on_f5(self, event=None) -> None:
        """Atualiza a página atual (F5): VNFs, serviços ou executa ação padrão."""
        page = self._current_page
        if page == "topology":
            self._spawn(self._refresh_vnfs)
        elif page == "services":
            self._refresh_service_list()
        else:
            self._on_enter()

    def _on_ctrl_tab(self, event=None) -> None:
        """Navega para a próxima página (Ctrl+Tab)."""
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx + 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_ctrl_shift_tab(self, event=None) -> None:
        """Navega para a página anterior (Ctrl+Shift+Tab)."""
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx - 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_escape(self, event=None) -> None:
        """Fecha diálogo aberto ou limpa output da página (Escape)."""
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                child.destroy()
                return
        self._on_ctrl_l()

    # ── Helpers de threading ──────────────────────────────────────────
    def _dispatch(self, fn) -> None:
        """Enfileira uma chamada para execução thread-safe na main thread."""
        self._ui_queue.put(fn)

    def _poll_queue(self) -> None:
        """Polling periódico da fila de UI para execução thread-safe (50ms)."""
        while True:
            try:
                fn = self._ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
        self.root.after(50, self._poll_queue)

    def _spawn(self, fn, *args) -> None:
        """Executa *fn(*args)* em thread paralela via ThreadPoolExecutor."""
        self._executor.submit(fn, *args)

    def _run(self, func) -> None:
        """Verifica conexão e dispara *func* em background."""
        if not self.session.is_connected:
            messagebox.showwarning("Aviso", "Conecte ao roteador primeiro.")
            return
        self._spawn(func)

    def _write(self, widget, text: str) -> None:
        """Substitui o conteúdo de um widget Text de forma thread-safe."""
        self._dispatch(lambda: (
            widget.configure(state="normal"),
            widget.delete("1.0", "end"),
            widget.insert("end", text),
            widget.configure(state="disabled")))

    def _loading(self, widget, msg: str) -> None:
        """Exibe mensagem de carregamento no widget Text de forma thread-safe."""
        self._dispatch(lambda: (
            widget.configure(state="normal"),
            widget.delete("1.0", "end"),
            widget.insert("end", f"\u23f3  {msg}\n"),
            widget.configure(state="disabled")))

    def _on_watcher_update(self, results) -> None:
        """Callback recebido do Watcher; armazena resultados e recria página de manutenção."""
        self._watcher_results = results
        if self._current_page == "manutencao":
            self._rebuild_page("manutencao")

    # ── Cleanup ───────────────────────────────────────────────────────
    def _on_close(self) -> None:
        """Finaliza watcher, desconecta sessão e encerra o executor ao fechar."""
        self._watcher.stop()
        self.session.disconnect()
        self._executor.shutdown(wait=False)
        self.root.destroy()


class HuaweiRouterApp(AppCore, PageBuilder, EventHandlers):
    """Classe final que combina os mixins AppCore, PageBuilder e EventHandlers via herança múltipla."""
