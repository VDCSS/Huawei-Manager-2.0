#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
from __future__ import annotations

import atexit
import datetime
import logging
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._app import apply_theme
from huawei_manager._config import PROJECT_ROOT, _secrets, audit
from huawei_manager.agents.watcher import Watcher
from huawei_manager.constants import set_theme
from huawei_manager.handlers import EventHandlers
from huawei_manager.pages import PageBuilder
from huawei_manager.sdn_controller.authz import SessionTracker
from huawei_manager.sdn_controller.core import ControllerCore
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import EventQueue
from huawei_manager.sdn_controller.northbound import NorthboundAPI
from huawei_manager.sdn_controller.snmp_handler import SnmpTrapHandler
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.session import NetmikoSession
from huawei_manager.vnf_models import VNF
from huawei_manager.widgets import ActionButton, NeonButton, action_button, neon_button

log = logging.getLogger("huawei_manager")
_app_log = logging.getLogger("huawei.app")


class AppCore(QMainWindow):
    """Mixin principal Qt — inicializa janela, layout, navegação e helpers de threading."""

    def __init__(self) -> None:
        super().__init__()
        self._init_common_attrs()
        self.setWindowTitle("HUAWEI MANAGER")
        self.resize(1220, 740)
        self.setMinimumSize(800, 500)

        try:
            icon_path = PROJECT_ROOT / "share" / "icons" / "huawei-manager.png"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass

        apply_theme("dark")

        assert _secrets is not None, "_config.init() must be called first"
        assert audit is not None, "_config.init() must be called first"
        self.session = NetmikoSession(_secrets, audit)
        self._event_queue = EventQueue()
        self._sb = SSHSouthbound(_secrets, audit, session=self.session)
        self._cmd_validator = CommandValidator()
        self._dry_run = DryRunEngine()
        self._controller = ControllerCore(event_queue=self._event_queue)
        self._northbound = NorthboundAPI(
            controller=self._controller,
            event_queue=self._event_queue,
            audit_logger=audit,
            sb=self._sb,
        )
        self._snmp_handler = SnmpTrapHandler()
        self._drv = RouterDriver(southbound=self._sb, event_queue=self._event_queue)
        self._session_tracker = SessionTracker(timeout_secs=300)
        self._active_btn: NeonButton | None = None
        self._access_level: str = "user"
        self._mock_mode: bool = True
        self._vnfs_busy: bool = False
        self._theme: str = "dark"
        self._theme_toggling: bool = False

        self._admin_attempts = 0
        self._admin_locked_until: float = 0

        self._target_vnf: VNF | None = None
        self._vnfs: list[VNF] = []
        self._topo_canvas: object = None
        io_w = int(os.environ.get("HW_IO_WORKERS", "6"))
        cpu_w = int(os.environ.get("HW_CPU_WORKERS", "2"))
        self._io_executor = ThreadPoolExecutor(max_workers=io_w, thread_name_prefix="hw-io")
        self._cpu_executor = ThreadPoolExecutor(max_workers=cpu_w, thread_name_prefix="hw-cpu")
        atexit.register(self._cleanup_executors)
        self._ui_queue: deque = deque(maxlen=1000)
        self._watcher = Watcher(self, self._on_watcher_update)
        self._watcher_results: list | None = None

        self._current_page: str | None = None
        self._PAGE_KEYS = [
            "home", "topology", "config", "route", "arp",
            "info", "cmd", "backup", "manutencao", "services",
        ]

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self._dash_timer = QTimer(self)
        self._dash_timer.timeout.connect(self._tick_dashboard)
        self._dash_timer.start(5000)

        self._vnf_timer = QTimer(self)
        self._vnf_timer.timeout.connect(self._tick_vnfs)
        self._vnf_timer.start(30000)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_queue)
        self._poll_timer.start(50)

        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._check_session_timeout)
        self._session_timer.start(30000)  # check every 30s

        self._build_layout()
        self._setup_bindings()
        self._show_page("home")
        self._init_topology_backend()

    def _init_common_attrs(self) -> None:
        """Garante que todos os atributos dos mixins existem antes do uso."""
        self._logo_pixmap: QPixmap | None = None
        self.theme_btn: ActionButton | None = None
        self.out_config: QTextEdit | None = None
        self.out_route: QTextEdit | None = None
        self.out_arp: QTextEdit | None = None
        self.out_info: QTextEdit | None = None
        self.out_cmd: QTextEdit | None = None
        self.out_backup: QTextEdit | None = None
        self._svc_output: QTextEdit | None = None
        self._page_container: QStackedWidget | None = None
        self._vnf_info_lbl: QLabel | None = None
        self._vnf_status_lbl: QLabel | None = None
        self._auth_overlay: QWidget | None = None
        self._last_manut_results: list = []
        self._manut_filter: str = "all"
        self._vnfs_lock = threading.Lock()

    # ── Layout ───────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(228)
        self.sidebar.setStyleSheet(f"background: {C.BG_SIDEBAR};")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        main_layout.addWidget(self.sidebar)

        right = QWidget()
        right.setStyleSheet(f"background: {C.BG_BASE};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        main_layout.addWidget(right, stretch=1)

        self._build_header(right)

        sep = QFrame(right)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {C.BORDER_NRM}; max-height: 1px; border: none;")
        right_layout.addWidget(sep)

        self.content = QWidget(right)
        self.content.setStyleSheet(f"background: {C.BG_BASE};")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(18, 18, 18, 18)
        self.content_layout.setSpacing(0)
        right_layout.addWidget(self.content, stretch=1)

        self._page_container = QStackedWidget(self.content)
        self._page_container.setStyleSheet(
            f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        self.content_layout.addWidget(self._page_container, stretch=1)

        self._build_sidebar()
        self._build_footer(right_layout)

        self.pages: dict[str, QWidget] = {}
        self._page_builders = {
            "home":       self._build_home_page,
            "config":     self._build_config_page,
            "route":      self._build_route_page,
            "arp":        self._build_arp_page,
            "info":       self._build_info_page,
            "cmd":        self._build_cmd_page,
            "backup":     self._build_backup_page,
            "topology":   self._build_topology_page,
            "services":   self._build_services_page,
            "manutencao": self._build_manutencao_page,
        }

    # ── Header ───────────────────────────────────────────────────────
    def _build_header(self, parent: QWidget) -> None:
        hdr = QWidget(parent)
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background: {C.BG_BASE};")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(18, 10, 18, 6)
        hdr_layout.setSpacing(0)

        try:
            logo_path = PROJECT_ROOT / "share" / "icons" / "huawei-manager.png"
            if logo_path.exists():
                pixmap = QPixmap(str(logo_path))
                self._logo_pixmap = pixmap
                scaled = pixmap.scaled(63, 61, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                logo_lbl = QLabel(hdr)
                logo_lbl.setPixmap(scaled)
                logo_lbl.setStyleSheet(f"background: {C.BG_BASE};")
                hdr_layout.addWidget(logo_lbl)
                hdr_layout.addSpacing(10)
        except Exception:
            pass

        lbl_huawei = QLabel("HUAWEI", hdr)
        lbl_huawei.setStyleSheet(f"color: {C.NEON_CYAN}; background: {C.BG_BASE}; "
                                 f"font: bold 18px 'Inter';")
        hdr_layout.addWidget(lbl_huawei)

        lbl_manager = QLabel(" MANAGER", hdr)
        lbl_manager.setStyleSheet(f"color: {C.FG_MAIN}; background: {C.BG_BASE}; "
                                  f"font: bold 18px 'Inter';")
        hdr_layout.addWidget(lbl_manager)

        hdr_layout.addStretch()

        badge = QWidget(hdr)
        badge.setStyleSheet(f"background: {C.BG_BASE};")
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(0)

        self.status_dot = QLabel("\u25cf", badge)
        self.status_dot.setStyleSheet(f"color: {C.NEON_PURP}; background: {C.BG_BASE}; "
                                      f"font: 16px 'Inter';")
        badge_layout.addWidget(self.status_dot)
        badge_layout.addSpacing(4)

        self.status_lbl = QLabel("Desconectado", badge)
        self.status_lbl.setStyleSheet(f"color: {C.FG_DIM}; background: {C.BG_BASE}; "
                                      f"font: 11px 'Inter';")
        badge_layout.addWidget(self.status_lbl)
        badge_layout.addSpacing(12)

        self.conn_btn = action_button(badge, "  CONECTAR  ",
                                      self._toggle_connect, C.NEON_CYAN)
        badge_layout.addWidget(self.conn_btn)

        self.theme_btn = action_button(badge, "\u263c", self._toggle_theme, C.NEON_PURP)
        badge_layout.addSpacing(6)
        badge_layout.addWidget(self.theme_btn)

        hdr_layout.addWidget(badge)

        # ── Garantir que hdr seja adicionado ao layout do parent ──
        pl = parent.layout()
        if pl is not None:
            pl.addWidget(hdr)

    # ── Sidebar ──────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        sb = self.sidebar
        sb_layout = sb.layout()
        sb_layout.setSpacing(0)

        logo = QWidget(sb)
        logo.setStyleSheet(f"background: {C.BG_SIDEBAR};")
        logo_layout = QVBoxLayout(logo)
        logo_layout.setContentsMargins(0, 14, 0, 4)

        try:
            if self._logo_pixmap is not None:
                sm = self._logo_pixmap.scaled(
                    32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                logo_lbl = QLabel(logo)
                logo_lbl.setPixmap(sm)
                logo_lbl.setStyleSheet(f"background: {C.BG_SIDEBAR};")
                logo_layout.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
                logo_layout.addSpacing(6)
        except Exception:
            pass
        sb_layout.addWidget(logo)

        self._nav_buttons: dict[str, NeonButton] = {}

        groups = (
            ("DASHBOARD", (
                ("home", "\U0001f3e0", "Dashboard", C.NEON_CYAN),
            )),
            ("DISPOSITIVOS", (
                ("topology", "\U0001f5fa", "Topologia / VNFs", C.NEON_AMBER),
                ("config",   "\U0001f4cb", "Config Atual", C.NEON_CYAN),
                ("route",    "\U0001f310", "Roteamento", C.NEON_CYAN),
                ("arp",      "\U0001f4e1", "Tabela ARP", C.NEON_CYAN),
                ("info",     "\U0001f4bb", "Info do Sistema", C.NEON_MAG),
            )),
            ("FERRAMENTAS", (
                ("cmd",      "\u2328",     "Editor de Comandos", C.NEON_MAG),
                ("backup",   "\U0001f4be", "Backup", C.NEON_PURP),
                ("services", "\u26a1",     "Servicos", C.NEON_AMBER),
            )),
            ("ADMINISTRACAO", (
                ("manutencao", "\U0001f6e0", "Manutencao", C.NEON_MAG),
            )),
        )

        for cat_label, items in groups:
            cat_w = QWidget(sb)
            cat_w.setStyleSheet(f"background: {C.BG_SIDEBAR};")
            cat_layout = QVBoxLayout(cat_w)
            cat_layout.setContentsMargins(16, 6, 16, 0)
            cat_layout.setSpacing(0)

            lbl = QLabel(cat_label, cat_w)
            lbl.setStyleSheet(f"color: {C.FG_DIM}; background: {C.BG_SIDEBAR}; "
                              f"font: 9px 'Inter';")
            cat_layout.addWidget(lbl)

            for key, icon_char, label, color in items:
                btn = neon_button(cat_w, label,
                                  lambda _chk, k=key: self._show_page(k),
                                  color=color, icon=icon_char)
                self._nav_buttons[key] = btn
                cat_layout.addWidget(btn)
            sb_layout.addWidget(cat_w)

        sep_line = QFrame(sb)
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet(f"background: {C.BORDER_NRM}; max-height: 1px; "
                               f"border: none;")
        sb_layout.addSpacing(8)
        sb_layout.addWidget(sep_line)
        sb_layout.addSpacing(8)

        vnf_section = QWidget(sb)
        vnf_section.setStyleSheet(f"background: {C.BG_SIDEBAR};")
        vnf_layout = QVBoxLayout(vnf_section)
        vnf_layout.setContentsMargins(16, 4, 16, 0)
        vnf_layout.setSpacing(2)

        lbl_alvo = QLabel("ALVO VNF", vnf_section)
        lbl_alvo.setStyleSheet(f"color: {C.FG_DIM}; background: {C.BG_SIDEBAR}; "
                               f"font: 11px 'Inter';")
        vnf_layout.addWidget(lbl_alvo)

        self._vnf_target_lbl = QLabel("(roteador padrao)", vnf_section)
        self._vnf_target_lbl.setStyleSheet(
            f"color: {C.NEON_AMBER}; background: {C.BG_SIDEBAR}; "
            f"font: bold 12px 'Inter';")
        self._vnf_target_lbl.setWordWrap(True)
        vnf_layout.addWidget(self._vnf_target_lbl)
        sb_layout.addWidget(vnf_section)

        sb_layout.addStretch()

    # ── Footer ───────────────────────────────────────────────────────
    def _build_footer(self, parent_layout: QBoxLayout) -> None:
        foot = QWidget()
        foot.setFixedHeight(22)
        foot.setStyleSheet(f"background: {C.BG_SIDEBAR};")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(12, 0, 12, 0)
        foot_layout.setSpacing(0)

        lbl = QLabel("Huawei Manager  \u2022  v2.0.0", foot)
        lbl.setStyleSheet(f"color: {C.FG_DIM}; background: {C.BG_SIDEBAR}; "
                          f"font: 9px 'Inter';")
        foot_layout.addWidget(lbl)

        foot_layout.addStretch()

        self.clock_lbl = QLabel(foot)
        self.clock_lbl.setStyleSheet(f"color: {C.NEON_PURP}; background: {C.BG_SIDEBAR}; "
                                     f"font: 9px 'Inter';")
        foot_layout.addWidget(self.clock_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        parent_layout.addWidget(foot)

    # ── Helpers de pagina ─────────────────────────────────────────────
    def _make_page(self, key: str) -> QWidget:
        p = super()._make_page(key)
        self.pages[key] = p
        return p

    # ── Navegacao ────────────────────────────────────────────────────
    def _show_page(self, key: str) -> None:
        if self._active_btn:
            self._active_btn._deactivate()
        if key not in self.pages:
            fn = self._page_builders.get(key)
            if fn:
                fn()
        target = self.pages.get(key)
        if target:
            self._page_container.setCurrentWidget(target)
        btn = self._nav_buttons.get(key)
        if btn:
            btn._activate()
            self._active_btn = btn
        self._current_page = key

    def _rebuild_page(self, key: str) -> None:
        if key in self.pages:
            old = self.pages.pop(key)
            self._page_container.removeWidget(old)
            old.deleteLater()
        if self._current_page == key:
            self._show_page(key)

    def _tick_clock(self) -> None:
        self.clock_lbl.setText(
            datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def _tick_dashboard(self) -> None:
        if self._current_page == "home":
            self._refresh_dashboard()

    def _tick_vnfs(self) -> None:
        if self._current_page in ("home", "topology"):
            self._spawn_io(self._refresh_vnfs)

    def _check_session_timeout(self) -> None:
        """Verifica timeout da sessao e faz downgrade se inativo."""
        if self._access_level == "user":
            return
        new_role = self._session_tracker.current_role
        if new_role.value != self._access_level:
            self._access_level = new_role.value
            self._mock_mode = False
            self._watcher.stop()
            self._rebuild_page("topology")
            log.info("Acesso: timeout de sessao — resetado para user")

    def _set_status(self, text: str, color: str) -> None:
        self.status_dot.setStyleSheet(
            f"color: {color}; background: {C.BG_BASE}; font: 16px 'Inter';")
        self.status_lbl.setText(text)

    def _set_conn_btn(self, text: str = "  CONECTAR  ", disabled: bool = False) -> None:
        btn = self.conn_btn
        self._dispatch(lambda: (
            btn.setText(text),
            btn.setEnabled(not disabled),
        ))

    # ── Tema ──────────────────────────────────────────────────────────
    def _toggle_theme(self) -> None:
        if self._theme_toggling:
            return
        self._theme_toggling = True
        self._theme = "light" if self._theme == "dark" else "dark"
        set_theme(self._theme)
        apply_theme(self._theme)
        self._rebuild_ui()
        icon = "\u263c" if self._theme == "dark" else "\u263e"
        self.theme_btn.setText(icon)
        self.theme_btn.setEnabled(False)
        QTimer.singleShot(1500, self._unlock_theme)

    def _unlock_theme(self) -> None:
        self._theme_toggling = False
        if self.theme_btn is not None:
            self.theme_btn.setEnabled(True)

    def _rebuild_ui(self) -> None:
        # 1. Parar todos os timers antes de destruir widgets
        self._dash_timer.stop()
        self._vnf_timer.stop()
        self._poll_timer.stop()

        # 2. Salvar estado
        current_page = self._current_page
        self._active_btn = None
        self._topo_canvas = None
        self.pages.clear()

        # 3. Destruir UI antiga
        old = self.centralWidget()
        if old:
            old.setParent(None)
            old.deleteLater()
        self.content = None
        self._page_container = None
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        # 4. Reconstruir
        self._build_layout()
        self._rebuild_page(current_page or "home")

        # 5. Reiniciar timers
        self._dash_timer.start()
        self._vnf_timer.start()
        self._poll_timer.start()

    # ── Atalhos de teclado ─────────────────────────────────────────────
    def _setup_bindings(self) -> None:
        QShortcut(QKeySequence("Return"), self).activated.connect(self._on_enter)
        QShortcut(QKeySequence("Ctrl+Shift+Return"), self).activated.connect(
            self._on_ctrl_shift_enter)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._on_ctrl_d)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._on_ctrl_l)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self._on_ctrl_q)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self).activated.connect(
            self._on_ctrl_shift_a)
        QShortcut(QKeySequence("F5"), self).activated.connect(self._on_f5)
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(self._on_ctrl_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(
            self._on_ctrl_shift_tab)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)
        for i, key in enumerate(self._PAGE_KEYS[:9], 1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self).activated.connect(
                lambda _chk, k=key: self._show_page(k))

    def _on_enter(self) -> None:
        focus = self.focusWidget()
        if isinstance(focus, QTextEdit):
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

    def _on_ctrl_shift_enter(self) -> None:
        if self._current_page == "cmd":
            self._run(self._exec_config)

    def _on_ctrl_d(self) -> None:
        self._toggle_connect()

    def _on_ctrl_l(self) -> None:
        page = self._current_page
        if page == "config" and self.out_config is not None:
            self._write(self.out_config, "")
        elif page == "route" and self.out_route is not None:
            self._write(self.out_route, "")
        elif page == "arp" and self.out_arp is not None:
            self._write(self.out_arp, "")
        elif page == "info" and self.out_info is not None:
            self._write(self.out_info, "")
        elif page == "cmd" and self.out_cmd is not None:
            self._write(self.out_cmd, "")
        elif page == "backup" and self.out_backup is not None:
            self._write(self.out_backup, "")
        elif page == "services" and self._svc_output is not None:
            self._write(self._svc_output, "")

    def _on_ctrl_q(self) -> None:
        self._on_close()

    def _on_ctrl_shift_a(self) -> None:
        self._show_auth_dialog()

    def _on_f5(self) -> None:
        page = self._current_page
        if page == "topology":
            self._spawn_io(self._refresh_vnfs)
        elif page == "services":
            self._refresh_service_list()
        else:
            self._on_enter()

    def _on_ctrl_tab(self) -> None:
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx + 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_ctrl_shift_tab(self) -> None:
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx - 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_escape(self) -> None:
        self._on_ctrl_l()

    # ── Helpers de threading ──────────────────────────────────────────
    def _dispatch(self, fn) -> None:
        maxlen = self._ui_queue.maxlen
        if maxlen is not None and len(self._ui_queue) >= maxlen:
            _app_log.warning("UI queue overflow (%d), descartando callback", len(self._ui_queue))
            return
        self._ui_queue.append(fn)

    def _poll_queue(self) -> None:
        for _ in range(500):
            try:
                fn = self._ui_queue.popleft()
            except IndexError:
                break
            try:
                fn()
            except Exception:
                _app_log.exception("_poll_queue: callback %r falhou", fn)
        # Drenar event_queue (PriorityQueue cresce sem consumidor)
        drained = 0
        while drained < 100:
            ev = self._event_queue.get(block=False)
            if ev is None:
                break
            drained += 1
        if drained > 0:
            _app_log.debug("Drained %d SDN events from queue", drained)

    def _spawn_io(self, fn, *args) -> None:
        future = self._io_executor.submit(fn, *args)
        future.add_done_callback(lambda f: f.exception() and
            _app_log.error("Task %s falhou: %s", fn.__name__, f.exception()))

    def _spawn_cpu(self, fn, *args) -> None:
        future = self._cpu_executor.submit(fn, *args)
        future.add_done_callback(lambda f: f.exception() and
            _app_log.error("CPU task %s falhou: %s", fn.__name__, f.exception()))

    def _run(self, func) -> None:
        if not self._sb.is_alive():
            QMessageBox.warning(self, "Aviso", "Conecte ao roteador primeiro.")
            return
        self._spawn_io(func)

    def _write(self, widget, text: str) -> None:
        self._dispatch(lambda w=widget, t=text: (w.clear(), w.setPlainText(t)))

    def _loading(self, widget, msg: str) -> None:
        self._dispatch(lambda w=widget, m=msg: (w.clear(), w.setPlainText(f"\u23f3  {m}\n")))

    def _on_watcher_update(self, results) -> None:
        self._watcher_results = results
        self._dispatch(self._rebuild_manutencao_if_active)

    def _rebuild_manutencao_if_active(self) -> None:
        if self._current_page == "manutencao":
            self._rebuild_page("manutencao")

    # ── Cleanup ───────────────────────────────────────────────────────
    def _cleanup_executors(self) -> None:
        """Desliga ambos os pools com timeout de 5s cada."""
        for pool in (getattr(self, "_io_executor", None),
                     getattr(self, "_cpu_executor", None)):
            if pool is not None:
                pool.shutdown(wait=True, timeout=5)

    def _on_close(self) -> None:
        self._watcher.stop()
        self._sb.disconnect()
        self._cleanup_executors()

    def closeEvent(self, event) -> None:
        self._on_close()
        super().closeEvent(event)


class HuaweiRouterApp(AppCore, PageBuilder, EventHandlers):
    """Classe final que combina os mixins AppCore, PageBuilder e EventHandlers."""
