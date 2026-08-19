#!/usr/bin/env python3
from __future__ import annotations

import atexit
import datetime
import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._app import apply_theme
from huawei_manager._config import PROJECT_ROOT, _s, _secrets, audit
from huawei_manager.agents.watcher import Watcher
from huawei_manager.app_notify import NotifyMixin
from huawei_manager.app_shortcuts import ShortcutsMixin
from huawei_manager.app_state import AppStateMixin
from huawei_manager.app_threading import ThreadingMixin
from huawei_manager.constants import set_theme
from huawei_manager.db import get_connection, init_database
from huawei_manager.device_models import Device
from huawei_manager.device_repository import DeviceRepository
from huawei_manager.handlers import EventHandlers
from huawei_manager.migration import migrate_json_inventory
from huawei_manager.pages import PageBuilder
from huawei_manager.sdn_controller.authz import SessionTracker
from huawei_manager.sdn_controller.core import ControllerCore
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import EventQueue
from huawei_manager.sdn_controller.polling_manager import PollingManager
from huawei_manager.sdn_controller.session_factory import SSHSessionFactory
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.services.device_service import DeviceService
from huawei_manager.session import NetmikoSession
from huawei_manager.widgets.neon_button import ActionButton, NeonButton, action_button, neon_button

log = logging.getLogger("huawei_manager")


class AppCore(QMainWindow, ThreadingMixin, NotifyMixin):
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
        self._event_queue = EventQueue(maxsize=1000)
        self._sb = SSHSouthbound(_secrets, audit, session=self.session)
        self._cmd_validator = CommandValidator()
        self._dry_run = DryRunEngine()
        self._controller = ControllerCore(
            event_queue=self._event_queue,
            dump_path=str(Path.home() / ".huawei_manager" / "sdn_state.json"),
        )
        db_conn = get_connection()
        init_database(db_conn)

        # Auto-generate VNF_ENCRYPT_KEY on first boot (fail-closed: if put fails, log and continue)
        try:
            from huawei_manager.device_crypto import ensure_encrypt_key
            ensure_encrypt_key()
        except Exception as exc:
            log.warning("VNF_ENCRYPT_KEY nao disponivel — segredos Device falharao no save (fail-closed): %s", exc)

        # Auto-migrate JSON inventory to SQLite on first run
        json_path = str(Path(__file__).resolve().parent / "data" / "vnf_inventory.json")
        if Path(json_path).exists():
            repo_check = DeviceRepository(db_conn)
            if not repo_check.list_devices():
                log.info("SQLite inventory empty — migrating from JSON...")
                migrate_json_inventory(json_path, db_conn)

        self._device_service = DeviceService(
            inventory_path=json_path,
            resolve_env=_s,
            repository=DeviceRepository(db_conn),
        )

        self._polling_enabled = os.environ.get(C.POLL_ENABLED_ENV, "0") == "1"
        if self._polling_enabled and not _s("VNF_ENCRYPT_KEY"):
            log.critical(
                "HW_ADAPTIVE_POLLING=1 mas VNF_ENCRYPT_KEY ausente — polling desabilitado"
            )
            self._polling_enabled = False
        self._session_factory = SSHSessionFactory(_secrets, audit)
        self._polling_mgr = PollingManager(
            factory=self._session_factory,
            device_service=self._device_service,
            enabled=self._polling_enabled,
        )
        self._adaptive_timer = QTimer(self)
        self._adaptive_timer.timeout.connect(self._tick_adaptive_polling)
        self._adaptive_timer.start(C.POLL_TICK_FLOOR_MS)

        self._drv = RouterDriver(southbound=self._sb, event_queue=self._event_queue)
        self._session_tracker = SessionTracker(timeout_secs=300)
        self._active_btn: NeonButton | None = None
        self._access_level: str = "user"
        self._mock_mode: bool = False
        self._theme: str = "dark"
        self._theme_toggling: bool = False

        self._admin_attempts = 0
        self._admin_locked_until: float = 0

        self._target_device: Device | None = None
        self._devices: list[Device] = []
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

        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._tick_devices)
        self._device_timer.start(30000)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_queue)
        self._poll_timer.start(50)

        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._check_session_timeout)
        self._session_timer.start(30000)  # check every 30s

        self._build_layout()
        self._setup_bindings()
        self._show_page("home")

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
        self._device_info_lbl: QLabel | None = None
        self._device_status_lbl: QLabel | None = None
        self._auth_overlay: QWidget | None = None
        self._last_manut_results: list = []
        self._manut_filter: str = "all"
        self._devices_lock = threading.Lock()
        self._devices_gen: int = 0
        self._devices: list[Device] = []
        self._mock_mode: bool = False
        self._dry_run: DryRunEngine | None = None
        self._cmd_validator: CommandValidator | None = None
        self._cancel_event: threading.Event | None = None
        self.backup_path: str = ""
        self._svc_mode_var: str = os.environ.get("HW_SVC_MODE", "mock")
        if self._svc_mode_var not in ("mock", "cli"):
            log.warning("HW_SVC_MODE invalido (%r) — usando mock", self._svc_mode_var)
            self._svc_mode_var = "mock"
        self._svc_param_entries: dict[str, QLineEdit] = {}
        self._shutdown: bool = False

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
            f"background: {C.BG_CARD}; border-radius: 4px;")
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
                ("topology", "\U0001f5fa", "Topologia / Devices", C.NEON_AMBER),
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
                              f"font: {C.FONT_CAPTION}px 'Inter';")
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

        device_section = QWidget(sb)
        device_section.setStyleSheet(f"background: {C.BG_SIDEBAR};")
        device_layout = QVBoxLayout(device_section)
        device_layout.setContentsMargins(16, 4, 16, 0)
        device_layout.setSpacing(2)

        lbl_alvo = QLabel("ALVO DEVICE", device_section)
        lbl_alvo.setStyleSheet(f"color: {C.FG_DIM}; background: {C.BG_SIDEBAR}; "
                               f"font: 11px 'Inter';")
        device_layout.addWidget(lbl_alvo)

        self._device_target_lbl = QLabel("(roteador padrao)", device_section)
        self._device_target_lbl.setStyleSheet(
            f"color: {C.NEON_AMBER}; background: {C.BG_SIDEBAR}; "
            f"font: bold 12px 'Inter';")
        self._device_target_lbl.setWordWrap(True)
        device_layout.addWidget(self._device_target_lbl)
        sb_layout.addWidget(device_section)

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
                          f"font: {C.FONT_CAPTION}px 'Inter';")
        foot_layout.addWidget(lbl)

        foot_layout.addStretch()

        self.clock_lbl = QLabel(foot)
        self.clock_lbl.setStyleSheet(f"color: {C.NEON_PURP}; background: {C.BG_SIDEBAR}; "
                                     f"font: {C.FONT_CAPTION}px 'Inter';")
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

    def _tick_adaptive_polling(self) -> None:
        if self._polling_enabled and not self._mock_mode:
            try:
                self._spawn_io(self._polling_mgr.tick)
            except Exception:
                log.exception("adaptive polling tick falhou ao despachar")
        try:
            nxt = self._polling_mgr.next_due_min()
            if nxt is None:
                delay_ms = C.POLL_MIN_INTERVAL * 1000
            else:
                delay_ms = max(
                    C.POLL_TICK_FLOOR_MS,
                    int((nxt - time.time()) * 1000),
                )
            self._adaptive_timer.start(delay_ms)
        except Exception:
            # B-1: re-arm nunca deve morrer com o timer — polling continua.
            log.exception("adaptive polling re-arm falhou")
            self._adaptive_timer.start(C.POLL_TICK_FLOOR_MS)

    # ── Tema ──────────────────────────────────────────────────────────
    def _toggle_theme(self) -> None:
        if self._theme_toggling:
            return
        # Salvar estado de conexão antes do rebuild
        status_lbl = getattr(self, "status_lbl", None)
        status_dot = getattr(self, "status_dot", None)
        conn_btn = getattr(self, "conn_btn", None)
        conn_text = status_lbl.text() if status_lbl else "Desconectado"
        conn_color = status_dot.styleSheet() if status_dot else f"color: {C.NEON_CYAN};"
        conn_btn_text = conn_btn.text() if conn_btn else "  CONECTAR  "
        conn_disabled = conn_btn.isEnabled() is False if conn_btn else False
        active_page = self._current_page

        self._theme_toggling = True
        self._theme = "light" if self._theme == "dark" else "dark"
        set_theme(self._theme)
        apply_theme(self._theme)
        # Feedback visual durante rebuild
        if status_lbl:
            status_lbl.setText("Reconstruindo tema…")
        QApplication.processEvents()
        self._rebuild_ui()

        # Restaurar estado de conexão (defensivo para mocks em testes)
        set_status = getattr(self, "_set_status", None)
        set_conn_btn = getattr(self, "_set_conn_btn", None)
        color = conn_color.replace("color: ", "").split(";")[0] if "color:" in conn_color else C.NEON_CYAN
        if set_status:
            set_status(conn_text, color)
        if set_conn_btn:
            set_conn_btn(text=conn_btn_text, disabled=conn_disabled)
        if active_page and active_page in self.pages:
            self._show_page(active_page)
            # Reativar botão da aba
            btn = self._nav_buttons.get(active_page)
            if btn:
                btn._activate()
                self._active_btn = btn
        theme_btn = getattr(self, "theme_btn", None)
        if theme_btn:
            theme_btn.setText("\u263c" if self._theme == "dark" else "\u263e")
            theme_btn.setEnabled(False)
        QTimer.singleShot(1500, self._unlock_theme)

    def _unlock_theme(self) -> None:
        self._theme_toggling = False
        if self.theme_btn is not None:
            self.theme_btn.setEnabled(True)

    def _rebuild_ui(self) -> None:
        # 1. Parar todos os timers antes de destruir widgets
        self._dash_timer.stop()
        self._device_timer.stop()
        self._poll_timer.stop()
        self._session_timer.stop()
        self._clock_timer.stop()
        if getattr(self, "_adaptive_timer", None) is not None:
            self._adaptive_timer.stop()
        self._watcher.stop()

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
        self._device_timer.start()
        self._poll_timer.start()
        self._session_timer.start()
        self._clock_timer.start()
        if getattr(self, "_adaptive_timer", None) is not None:
            self._adaptive_timer.start()
        if self._watcher.is_active:
            self._watcher.start()

class HuaweiRouterApp(AppStateMixin, ShortcutsMixin, AppCore, PageBuilder, EventHandlers):
    """Classe final que combina os mixins AppCore, PageBuilder e EventHandlers."""
