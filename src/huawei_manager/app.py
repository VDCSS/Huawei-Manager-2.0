#!/usr/bin/env python3
from __future__ import annotations

import atexit
import datetime
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:

    from huawei_manager._protocols import AppCoreProtocol
    from huawei_manager.agents import AgentResult
    from huawei_manager.sdn_controller.bus import IEventBus
    from huawei_manager.sdn_controller.event_queue import Event
    from huawei_manager.sdn_controller.southbound import SouthboundProtocol
    from huawei_manager.tabs._contract import TabDef
    from huawei_manager.tabs.arp import ArpTab
    from huawei_manager.tabs.backup import BackupTab
    from huawei_manager.tabs.cmd import CmdTab
    from huawei_manager.tabs.config import ConfigTab
    from huawei_manager.tabs.home import HomeTab
    from huawei_manager.tabs.info import InfoTab
    from huawei_manager.tabs.route import RouteTab
    from huawei_manager.tabs.services import ServicesTab
    from huawei_manager.tabs.topology import TopologyTab
    from huawei_manager.topology import TopologyCanvas
    from huawei_manager.widgets.command_palette import Command, CommandRegistry

import huawei_manager.constants as C
from huawei_manager import _config
from huawei_manager._app import apply_theme
from huawei_manager._config import PROJECT_ROOT, _s
from huawei_manager.agents.watcher import Watcher
from huawei_manager.app_notify import NotifyMixin
from huawei_manager.app_shortcuts import ShortcutsMixin
from huawei_manager.app_state import AppStateMixin
from huawei_manager.app_threading import ThreadingMixin
from huawei_manager.command import ConfigCommand
from huawei_manager.constants import set_theme
from huawei_manager.db import get_connection, init_database
from huawei_manager.device_models import Device
from huawei_manager.device_repository import DeviceRepository
from huawei_manager.handlers import EventHandlers
from huawei_manager.migration import migrate_json_inventory
from huawei_manager.sdn_controller.authz import SessionTracker
from huawei_manager.sdn_controller.core import ControllerCore
from huawei_manager.sdn_controller.drivers.factory import driver_for
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import EventQueue
from huawei_manager.sdn_controller.listeners import start_alert_listeners
from huawei_manager.sdn_controller.polling_manager import PollingManager
from huawei_manager.sdn_controller.session_factory import SSHSessionFactory
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.services.device_service import DeviceService
from huawei_manager.services.ui_bridge import UiBridge
from huawei_manager.session import NetmikoSession
from huawei_manager.tabs import build_registry, tab_by_key
from huawei_manager.tabs._contract import TabContext
from huawei_manager.widgets.confirm_drawer import ConfirmDrawer
from huawei_manager.widgets.icons import icon as svg_icon
from huawei_manager.widgets.icons import icon_pixmap
from huawei_manager.widgets.neon_button import ActionButton, NeonButton, action_button, neon_button

log = logging.getLogger("huawei_manager")


def _preferences() -> QSettings:
    """QSettings da aplicação com formato INI explícito.

    O formato nativo no Windows é o registro; usar INI mantém a persistência
    previsível entre plataformas e permite isolar os testes via
    ``QSettings.setPath``.
    """
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "HuaweiManager",
        "Preferences",
    )


class AppCore(NotifyMixin, QMainWindow, ThreadingMixin):
    """Mixin principal Qt — inicializa janela, layout, navegação e helpers de threading."""

    if TYPE_CHECKING:
        # ── Membros do AppCoreProtocol que vivem em mixins/builder ──────
        # (declarações estáticas; as implementações reais ficam em
        # AppStateMixin / ShortcutsMixin / EventHandlers e
        # só existem na composição final HuaweiRouterApp.)
        ADMIN_MAX_ATTEMPTS: int
        ADMIN_LOCKOUT_SECS: int
        # ── Métodos implementados fora do AppCore (espelho do protocolo) ─
        def _on_sdn_event(self: AppCoreProtocol, ev: Event | None) -> None: ...
        def _set_status(self: AppCoreProtocol, text: str, color: str) -> None: ...
        def _set_conn_btn(
            self: AppCoreProtocol, text: str = "", disabled: bool = False
        ) -> None: ...
        def _tick_dashboard(self: AppCoreProtocol) -> None: ...
        def _tick_devices(self: AppCoreProtocol) -> None: ...
        def _check_session_timeout(self: AppCoreProtocol) -> None: ...
        def _on_watcher_update(
            self: AppCoreProtocol, results: Sequence[AgentResult]
        ) -> None: ...
        def _rebuild_manutencao_if_active(self: AppCoreProtocol) -> None: ...
        def _setup_bindings(self: AppCoreProtocol) -> None: ...
        def _on_enter(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_shift_enter(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_d(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_l(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_q(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_shift_a(self: AppCoreProtocol) -> None: ...
        def _on_f5(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_tab(self: AppCoreProtocol) -> None: ...
        def _on_ctrl_shift_tab(self: AppCoreProtocol) -> None: ...
        def _on_escape(self: AppCoreProtocol) -> None: ...
        def _show_auth_dialog(self: AppCoreProtocol) -> None: ...
        def _rebuild_for_access_change(self: AppCoreProtocol) -> None: ...
        def _require_access(self: AppCoreProtocol, level: str = "admin") -> bool: ...
        def _get_selected_device(self: AppCoreProtocol) -> Device | None: ...
        def _ensure_device_ready(
            self: AppCoreProtocol, action: str
        ) -> Device | None: ...
        def _prompt_no_devices(self: AppCoreProtocol, action: str) -> None: ...
        def _toggle_connect(self: AppCoreProtocol) -> None: ...
        def _do_connect(
            self: AppCoreProtocol, on_success_fmt: str, on_error_msg: str
        ) -> None: ...
        def _connect_with_device(self: AppCoreProtocol, device: Device) -> None: ...
        def _refresh_devices(self: AppCoreProtocol) -> None: ...
        def _update_devices_ui(
            self: AppCoreProtocol, devices: list[Device]
        ) -> None: ...
        def _show_device_dialog(
            self: AppCoreProtocol, device: Device | None = None
        ) -> None: ...
        def _delete_device(self: AppCoreProtocol, device: Device) -> None: ...
        def _on_device_selected(self: AppCoreProtocol, device: Device) -> None: ...
        def _clear_device_target(self: AppCoreProtocol) -> None: ...

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

        settings = _preferences()
        saved_theme = settings.value("theme", "dark")
        if saved_theme not in ("dark", "light", "huawei"):
            saved_theme = "dark"
        self._theme: str = str(saved_theme)
        set_theme(self._theme)
        apply_theme(self._theme)

        # Globais de _config lidos em tempo de uso (não fixados no import):
        # um `from _config import _secrets` capturaria None se app.py fosse
        # importado antes do init(), quebrando o boot por ordem de import.
        secrets = _config._secrets
        audit_log = _config.audit
        if secrets is None:
            raise RuntimeError("_config.init() must be called first")
        if audit_log is None:
            raise RuntimeError("_config.init() must be called first")
        self.session = NetmikoSession(secrets, audit_log)
        self._event_queue: IEventBus = EventQueue(maxsize=1000)
        # Gap 2: fontes push (traps SNMP / syslog), opt-in por ambiente.
        # Cada listener é isolado — bind negado vira warning, não crash.
        # Precisa nascer DEPOIS do barramento (start_alert_listeners usa
        # _event_queue); _init_common_attrs roda antes deste ponto.
        self._alert_listeners = start_alert_listeners(self._event_queue)
        self._cmd_validator = CommandValidator()
        self._sb: SouthboundProtocol = SSHSouthbound(
            secrets, audit_log, session=self.session, validator=self._cmd_validator
        )
        self._dry_run = DryRunEngine()
        # Última mutação de configuração (Editor/Serviços) com snapshot
        # pré-mudança — alimenta o rollback da paleta de comandos.
        self._last_config_command: ConfigCommand | None = None
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
            log.warning(
                "VNF_ENCRYPT_KEY nao disponivel — segredos Device falharao "
                "no save (fail-closed): %s",
                exc,
            )

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
        self._session_factory = SSHSessionFactory(secrets, audit_log)
        self._polling_mgr = PollingManager(
            factory=self._session_factory,
            device_service=self._device_service,
            enabled=self._polling_enabled,
        )
        self._adaptive_timer = QTimer(self)
        self._adaptive_timer.timeout.connect(self._tick_adaptive_polling)
        self._adaptive_timer.start(C.POLL_TICK_FLOOR_MS)

        # Factory (Gap 1): driver resolvido pelo tipo do dispositivo; no
        # boot não há device selecionado, então vale o perfil padrão (VRP).
        self._drv = driver_for(None, self._sb, self._event_queue)
        self._session_tracker = SessionTracker(timeout_secs=300)
        self._active_btn: NeonButton | None = None
        self._access_level: str = "user"
        self._mock_mode: bool = False
        # ``_theme`` já foi lido de QSettings no início do __init__ (linhas
        # ~161-167). Não redefinir aqui: isso descartava a preferência salva
        # e deixava o QSS aplicado dessincronizado do botão de tema.
        self._theme_toggling: bool = False

        self._admin_attempts = 0
        self._admin_locked_until: float = 0

        self._target_device: Device | None = None
        self._devices: list[Device] = []
        io_w = int(os.environ.get("HW_IO_WORKERS", "6"))
        cpu_w = int(os.environ.get("HW_CPU_WORKERS", "2"))
        self._io_executor = ThreadPoolExecutor(max_workers=io_w, thread_name_prefix="hw-io")
        self._cpu_executor = ThreadPoolExecutor(max_workers=cpu_w, thread_name_prefix="hw-cpu")
        atexit.register(self._cleanup_executors)
        self._ui_queue: deque[Callable[[], object]] = deque(maxlen=1000)
        self._watcher = Watcher(self, self._on_watcher_update)
        self._watcher_results: Sequence[AgentResult] | None = None

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
        # Command Palette (Ctrl+K) - lazy init
        self._command_palette = None
        self._setup_bindings()
        self._show_page("home")

    def _init_common_attrs(self) -> None:
        """Garante que todos os atributos dos mixins existem antes do uso."""
        self._logo_pixmap: QPixmap | None = None
        self.theme_btn: ActionButton | None = None
        self._page_container: QStackedWidget | None = None
        self._auth_overlay: QWidget | None = None
        self._drawer: ConfirmDrawer | None = None
        self._devices_lock = threading.Lock()
        self._devices_gen: int = 0
        self._devices: list[Device] = []
        self._mock_mode: bool = False
        self._dry_run: DryRunEngine | None = None
        self._cmd_validator: CommandValidator | None = None
        self._svc_mode_var: str = os.environ.get("HW_SVC_MODE", "mock")
        if self._svc_mode_var not in ("mock", "cli"):
            log.warning("HW_SVC_MODE invalido (%r) — usando mock", self._svc_mode_var)
            self._svc_mode_var = "mock"
        self._shutdown: bool = False
        self._event_drop_count: int = 0
        # Logger de auditoria do app (era inacessível aos mixins; o caminho
        # NAPALM e o audit de comandos negados dependem dele).
        # Lido em tempo de uso: _init_common_attrs roda antes do __init__
        # montar os serviços, e o audit nasce no _config.init().
        self.audit_logger = _config.audit
        # Ponte I/O→GUI: workers pedem confirmação via ask_from_worker()
        # (QMessageBox nunca fora da thread GUI — ver services/ui_bridge.py).
        self._ui_bridge: UiBridge | None = UiBridge(self)

    # ── Layout ───────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(268)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        main_layout.addWidget(self.sidebar)

        right = QWidget()
        right.setObjectName("rightPane")
        right.setStyleSheet(f"#rightPane {{ background: {C.BG_BASE}; }}")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        main_layout.addWidget(right, stretch=1)

        self._build_header(right)

        self.content: QWidget | None = QWidget(right)
        self.content.setObjectName("contentPane")
        self.content.setStyleSheet(f"#contentPane {{ background: {C.BG_BASE}; }}")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        right_layout.addWidget(self.content, stretch=1)

        self._page_container = QStackedWidget(self.content)
        self._page_container.setObjectName("pageContainer")
        self._page_container.setStyleSheet(
            f"#pageContainer {{ background: {C.BG_BASE}; border: none; }}")
        self.content_layout.addWidget(self._page_container, stretch=1)

        # Registry único de abas (plano plano-abas-independentes): sidebar e
        # RBAC derivam de tabs/_TAB_META; as 10 abas são módulos reais.
        self._tabs: list[TabDef] = build_registry()
        self._tab_context = TabContext(
            sb=self._sb,
            audit=self.audit_logger,
            event_bus=self._event_queue,
            role=lambda: self._access_level,
            device=self._get_selected_device,
            dispatch=self._dispatch,
            require_access=self._require_access,
            spawn_io=self._spawn_io,
            spawn_cpu=self._spawn_cpu,
            watcher=self._watcher,
            is_mock=lambda: self._mock_mode,
            toggle_mock=self._toggle_mock_mode,
            show_auth_dialog=self._show_auth_dialog,
            watcher_results=lambda: self._watcher_results,
            set_watcher_results=self._set_watcher_results,
            session=self.session,
            run=self._run,
            set_status=self._set_status,
            touch_session=self._session_tracker.touch,
            cmd_validator=self._cmd_validator,
            dry_run=self._dry_run,
            get_last_config_command=lambda: self._last_config_command,
            set_last_config_command=lambda cmd: setattr(
                self, "_last_config_command", cmd),
            drv=lambda: self._drv,
            devices=lambda: self._devices,
            show_page=self._show_page,
            svc_mode=lambda: self._svc_mode_var,
            ui_bridge=lambda: self._ui_bridge,
            ensure_device_ready=self._ensure_device_ready,
            refresh_devices=self._refresh_devices,
            show_device_dialog=self._show_device_dialog,
            delete_device=self._delete_device,
            on_device_selected=self._on_device_selected,
            clear_device_target=self._clear_device_target,
        )

        self._build_sidebar()
        self._build_footer(right_layout)
        self._drawer = ConfirmDrawer(self)

        self.pages: dict[str, QWidget] = {}
        self._page_builders: dict[str, Callable[[], None]] = {
            td.key: (lambda key=td.key: self._build_tab(key)) for td in self._tabs
        }

    # ── Header ───────────────────────────────────────────────────────
    def _build_header(self, parent: QWidget) -> None:
        hdr = QWidget(parent)
        hdr.setObjectName("topbar")
        hdr.setFixedHeight(C.TOPBAR_HEIGHT)
        hdr.setStyleSheet(
            f"#topbar {{ background: {C.BG_BASE}; border-bottom: 1px solid {C.BORDER_NRM}; }}")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 0, 20, 0)
        hdr_layout.setSpacing(18)

        # ── Marca / wordmark — caixa 38 px + texto display 17 px ──────
        wordmark = QWidget(hdr)
        wordmark.setStyleSheet("background: transparent;")
        wm_layout = QHBoxLayout(wordmark)
        wm_layout.setContentsMargins(0, 0, 0, 0)
        wm_layout.setSpacing(10)

        logo_box = QLabel(wordmark)
        logo_box.setFixedSize(38, 38)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet(
            f"background: {C.rgba(C.NEON_CYAN, 0.09)};"
            f" border: 1px solid {C.rgba(C.NEON_CYAN, 0.34)};"
            f" border-radius: 5px;")
        self._logo_pixmap = icon_pixmap("i-logo", C.NEON_CYAN, 24)
        logo_box.setPixmap(self._logo_pixmap)
        wm_layout.addWidget(logo_box)

        brand = QLabel(wordmark)
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setText(
            f"<span style='color:{C.NEON_CYAN}'>HUAWEI</span> "
            f"<span style='color:{C.FG_MAIN}'>MANAGER</span>"
        )
        brand.setStyleSheet(
            f"background: transparent; font: 700 17px '{C.FONT_UI_TITLE_FAMILY}';")
        wm_layout.addWidget(brand)
        hdr_layout.addWidget(wordmark)

        divider = QFrame(hdr)
        divider.setFixedSize(1, 20)
        divider.setStyleSheet(f"background: {C.BORDER_NRM}; border: none;")
        hdr_layout.addWidget(divider)

        # ── Breadcrumb “Aplicativo › página” ──────────────────────────
        crumb = QWidget(hdr)
        crumb.setStyleSheet("background: transparent;")
        crumb_layout = QHBoxLayout(crumb)
        crumb_layout.setContentsMargins(0, 0, 0, 0)
        crumb_layout.setSpacing(6)

        crumb_app = QLabel("Aplicativo", crumb)
        crumb_app.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent;"
            f" font: 12.5px '{C.FONT_UI_FAMILY}';")
        crumb_layout.addWidget(crumb_app)

        crumb_sep = QLabel(crumb)
        crumb_sep.setPixmap(icon_pixmap("i-chevron-right", C.FG_FAINT, 14))
        crumb_layout.addWidget(crumb_sep)

        self.page_context_lbl = QLabel("Visão geral", crumb)
        self.page_context_lbl.setStyleSheet(
            f"color: {C.FG_CODE}; background: transparent;"
            f" font: 500 12.5px '{C.FONT_UI_FAMILY}';")
        crumb_layout.addWidget(self.page_context_lbl)
        hdr_layout.addWidget(crumb)
        hdr_layout.addStretch()

        # ── Grupo direito (busca, conexão, tema, avatar, janela) ──────
        right = QWidget(hdr)
        right.setStyleSheet("background: transparent;")
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        # Busca global — mesma ação do Ctrl+K (Command Palette).
        search_box = QFrame(right)
        search_box.setObjectName("searchBox")
        search_box.setFixedSize(290, 38)
        search_box.setCursor(Qt.CursorShape.PointingHandCursor)
        search_box.setStyleSheet(
            f"#searchBox {{ background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM};"
            f" border-radius: 6px; }}"
            f"#searchBox:hover {{ border-color: {C.rgba(C.NEON_CYAN, 0.34)}; }}")
        search_box.mousePressEvent = lambda _e: self._toggle_command_palette()
        sb_layout = QHBoxLayout(search_box)
        sb_layout.setContentsMargins(11, 0, 8, 0)
        sb_layout.setSpacing(8)

        search_icon = QLabel(search_box)
        search_icon.setPixmap(icon_pixmap("i-search", C.FG_FAINT, 16))
        sb_layout.addWidget(search_icon)

        search_ph = QLabel("Buscar serviço…", search_box)
        search_ph.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 13px '{C.FONT_UI_FAMILY}';")
        sb_layout.addWidget(search_ph, stretch=1)

        kbd = QLabel("Ctrl K", search_box)
        kbd.setStyleSheet(
            f"color: {C.FG_FAINT}; background: {C.BG_SURFACE_3};"
            f" border: 1px solid {C.BORDER_NRM}; border-radius: 2px;"
            f" padding: 2px 6px; font: 10px '{C.FONT_MONO_FAMILY}';")
        sb_layout.addWidget(kbd)
        right_layout.addWidget(search_box)

        # Estado da conexão — dot 6 px + label 12.5 px
        conn = QWidget(right)
        conn.setStyleSheet("background: transparent;")
        conn_layout = QHBoxLayout(conn)
        conn_layout.setContentsMargins(0, 0, 0, 0)
        conn_layout.setSpacing(6)

        self.status_dot = QLabel(conn)
        self.status_dot.setFixedSize(6, 6)
        self.status_dot.setStyleSheet(
            f"color: {C.NEON_RED}; background: {C.NEON_RED};"
            f" border-radius: 3px;")
        conn_layout.addWidget(self.status_dot)

        self.status_lbl = QLabel("Desconectado", conn)
        self.status_lbl.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent;"
            f" font: 12.5px '{C.FONT_UI_FAMILY}';")
        conn_layout.addWidget(self.status_lbl)
        right_layout.addWidget(conn)

        self.conn_btn = action_button(
            right, "  CONECTAR  ", self._toggle_connect, C.NEON_CYAN,
            variant="outline")
        self.conn_btn.setIcon(svg_icon("i-power", C.NEON_CYAN, 16))
        self.conn_btn.setIconSize(QSize(16, 16))
        right_layout.addWidget(self.conn_btn)

        self.theme_btn = action_button(
            right, "", self._toggle_theme, C.NEON_PURP, variant="ghost")
        self.theme_btn.setIconSize(QSize(16, 16))
        self._update_theme_btn_label()
        right_layout.addWidget(self.theme_btn)

        avatar = QLabel("HM", right)
        avatar.setObjectName("avatar")
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"#avatar {{ background: {C.rgba(C.NEON_CYAN, 0.09)}; color: {C.NEON_CYAN};"
            f" font: 700 12px '{C.FONT_MONO_FAMILY}';"
            f" border: 1px solid {C.rgba(C.NEON_CYAN, 0.34)}; border-radius: 16px; }}")
        right_layout.addWidget(avatar)

        # ── Controles de janela (icon-btn 34 px + SVG) ────────────────
        win_controls = QWidget(right)
        win_controls.setObjectName("windowControls")
        win_controls.setStyleSheet("background: transparent;")
        win_layout = QHBoxLayout(win_controls)
        win_layout.setContentsMargins(0, 0, 0, 0)
        win_layout.setSpacing(4)

        self.btn_min = QPushButton(win_controls)
        self.btn_min.setObjectName("winMinimizeBtn")
        self.btn_min.setFixedSize(34, 34)
        self.btn_min.setIcon(svg_icon("i-minus", C.FG_DIM, 18))
        self.btn_min.setIconSize(QSize(18, 18))
        self.btn_min.setToolTip("Minimizar janela")
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.clicked.connect(self.showMinimized)
        win_layout.addWidget(self.btn_min)

        self.btn_max = QPushButton(win_controls)
        self.btn_max.setObjectName("winMaximizeBtn")
        self.btn_max.setFixedSize(34, 34)
        self.btn_max.setIcon(svg_icon("i-square", C.FG_DIM, 18))
        self.btn_max.setIconSize(QSize(18, 18))
        self.btn_max.setToolTip("Maximizar / Restaurar janela")
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.clicked.connect(self._toggle_maximize)
        win_layout.addWidget(self.btn_max)

        self.btn_close = QPushButton(win_controls)
        self.btn_close.setObjectName("winCloseBtn")
        self.btn_close.setFixedSize(34, 34)
        self.btn_close.setIcon(svg_icon("i-x", C.FG_DIM, 18))
        self.btn_close.setIconSize(QSize(18, 18))
        self.btn_close.setToolTip("Fechar aplicativo")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        win_layout.addWidget(self.btn_close)

        right_layout.addWidget(win_controls)
        hdr_layout.addWidget(right)

        # ── Garantir que hdr seja adicionado ao layout do parent ──
        pl = parent.layout()
        if pl is not None:
            pl.addWidget(hdr)

    # ── Sidebar ──────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        sb = self.sidebar
        sb_layout = cast(QVBoxLayout, sb.layout())
        sb_layout.setSpacing(0)

        head = QWidget(sb)
        head.setObjectName("sidebarHead")
        head.setFixedHeight(68)
        head.setStyleSheet(
            f"#sidebarHead {{ background: {C.BG_SIDEBAR};"
            f" border-bottom: 1px solid {C.BORDER_SOFT}; }}")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(16, 0, 12, 0)
        head_layout.setSpacing(10)

        logo = QLabel(head)
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"background: {C.rgba(C.NEON_CYAN, 0.09)};"
            f" border: 1px solid {C.rgba(C.NEON_CYAN, 0.34)};"
            f" border-radius: 5px;")
        logo.setPixmap(icon_pixmap("i-logo", C.NEON_CYAN, 23))
        head_layout.addWidget(logo)

        copy = QWidget(head)
        copy.setStyleSheet("background: transparent;")
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(0)
        name = QLabel("HUAWEI MANAGER", copy)
        name.setStyleSheet(
            f"color: {C.NEON_CYAN}; background: transparent;"
            f" font: 600 13px '{C.FONT_UI_FAMILY}';")
        copy_layout.addWidget(name)
        version = QLabel("v2.0.0  ·  desktop", copy)
        version.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 10.5px '{C.FONT_MONO_FAMILY}';")
        copy_layout.addWidget(version)
        head_layout.addWidget(copy)
        head_layout.addStretch()
        sb_layout.addWidget(head)

        self._nav_buttons: dict[str, NeonButton] = {}

        # Nav rolável (MVP .sidebar__scroll: padding 6 0 12).
        nav_scroll = QScrollArea(sb)
        nav_scroll.setObjectName("sidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nav_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")
        nav_scroll.viewport().setStyleSheet("background: transparent;")

        nav_host = QWidget(nav_scroll)
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 6, 0, 12)
        nav_layout.setSpacing(0)

        # Sidebar gerada do registry (Fase 0): grupos e itens vêm de self._tabs
        # na ordem declarada em tabs/_TAB_META — fonte única.
        groups: dict[str, list[TabDef]] = {}
        for td in self._tabs:
            groups.setdefault(td.group, []).append(td)

        for cat_label, items in groups.items():
            cat_w = QWidget(nav_host)
            cat_w.setStyleSheet("background: transparent;")
            cat_layout = QVBoxLayout(cat_w)
            cat_layout.setContentsMargins(0, 0, 0, 0)
            cat_layout.setSpacing(1)

            lbl = QLabel(cat_label.upper(), cat_w)
            lbl.setObjectName("navGroupLabel")
            lbl.setStyleSheet(
                f"color: {C.FG_FAINT}; background: transparent;"
                f" font: 600 10.5px '{C.FONT_UI_FAMILY}';"
                f" padding: 12px 16px 7px 16px;")
            cat_layout.addWidget(lbl)

            for td in items:
                btn = neon_button(cat_w, td.label,
                                  lambda _chk, k=td.key: self._show_page(k),
                                  color=td.color, icon=td.icon)
                if td.key == "home":
                    btn.set_badge("live")
                self._nav_buttons[td.key] = btn
                cat_layout.addWidget(btn)
            nav_layout.addWidget(cat_w)

        nav_layout.addStretch()
        nav_scroll.setWidget(nav_host)
        sb_layout.addWidget(nav_scroll, stretch=1)

        # ── Rodapé: target-card + user-card (MVP .sidebar__foot) ──────
        foot = QWidget(sb)
        foot.setObjectName("sidebarFoot")
        foot.setStyleSheet(
            f"#sidebarFoot {{ background: {C.BG_SIDEBAR};"
            f" border-top: 1px solid {C.BORDER_SOFT}; }}")
        foot_layout = QVBoxLayout(foot)
        foot_layout.setContentsMargins(12, 12, 12, 12)
        foot_layout.setSpacing(8)

        device_section = QFrame(foot)
        device_section.setObjectName("targetCard")
        device_section.setStyleSheet(
            f"#targetCard {{ background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM};"
            f" border-radius: 6px; }}")
        device_layout = QHBoxLayout(device_section)
        device_layout.setContentsMargins(11, 10, 11, 10)
        device_layout.setSpacing(10)

        target_dot = QLabel(device_section)
        target_dot.setFixedSize(6, 6)
        target_dot.setStyleSheet(
            f"background: {C.NEON_GREEN}; border-radius: 3px;")
        device_layout.addWidget(target_dot)

        target_copy = QWidget(device_section)
        target_copy.setStyleSheet("background: transparent;")
        target_copy_layout = QVBoxLayout(target_copy)
        target_copy_layout.setContentsMargins(0, 0, 0, 0)
        target_copy_layout.setSpacing(1)

        lbl_alvo = QLabel("ALVO DO DEVICE", target_copy)
        lbl_alvo.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 600 9.5px '{C.FONT_UI_FAMILY}';")
        target_copy_layout.addWidget(lbl_alvo)

        self._device_target_lbl = QLabel("(nenhum device)", target_copy)
        self._device_target_lbl.setStyleSheet(
            f"color: {C.NEON_AMBER}; background: transparent;"
            f" font: 600 12px '{C.FONT_MONO_FAMILY}';")
        self._device_target_lbl.setWordWrap(True)
        target_copy_layout.addWidget(self._device_target_lbl)
        device_layout.addWidget(target_copy, stretch=1)

        target_icon = QLabel(device_section)
        target_icon.setPixmap(icon_pixmap("i-refresh", C.FG_FAINT, 15))
        device_layout.addWidget(target_icon)

        foot_layout.addWidget(device_section)

        user_card = QWidget(foot)
        user_card.setObjectName("userCard")
        user_card.setStyleSheet(
            f"#userCard {{ background: transparent;"
            f" border-top: 1px solid {C.BORDER_SOFT}; }}")
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(8, 9, 8, 9)
        user_layout.setSpacing(8)

        user_avatar = QLabel("HM", user_card)
        user_avatar.setFixedSize(32, 32)
        user_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_avatar.setStyleSheet(
            f"background: {C.rgba(C.NEON_PURP, 0.10)}; color: {C.NEON_PURP};"
            f" border: 1px solid {C.rgba(C.NEON_PURP, 0.30)}; border-radius: 16px;"
            f" font: 700 12px '{C.FONT_MONO_FAMILY}';")
        user_layout.addWidget(user_avatar)

        user_copy = QWidget(user_card)
        user_copy.setStyleSheet("background: transparent;")
        user_copy_layout = QVBoxLayout(user_copy)
        user_copy_layout.setContentsMargins(0, 0, 0, 0)
        user_copy_layout.setSpacing(0)
        user_name = QLabel("Sessão local", user_copy)
        user_name.setStyleSheet(
            f"color: {C.FG_CODE}; background: transparent;"
            f" font: 600 12.5px '{C.FONT_UI_FAMILY}';")
        user_copy_layout.addWidget(user_name)
        user_role = QLabel("perfil RBAC", user_copy)
        user_role.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 10.5px '{C.FONT_UI_FAMILY}';")
        user_copy_layout.addWidget(user_role)
        user_layout.addWidget(user_copy, stretch=1)

        online_dot = QLabel(user_card)
        online_dot.setFixedSize(5, 5)
        online_dot.setStyleSheet(
            f"background: {C.NEON_GREEN}; border-radius: 2px;")
        user_layout.addWidget(online_dot)

        foot_layout.addWidget(user_card)
        sb_layout.addWidget(foot)

    # ── Footer ───────────────────────────────────────────────────────
    def _build_footer(self, parent_layout: QBoxLayout) -> None:
        foot = QWidget()
        foot.setObjectName("statusbar")
        foot.setFixedHeight(C.STATUSBAR_HEIGHT)
        foot.setStyleSheet(
            f"#statusbar {{ background: {C.BG_STATUS}; border-top: 1px solid {C.BORDER_NRM}; }}")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(14, 0, 14, 0)
        foot_layout.setSpacing(16)

        left = QWidget(foot)
        left.setStyleSheet("background: transparent;")
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(7)

        brand_icon = QLabel(left)
        brand_icon.setPixmap(icon_pixmap("i-logo", C.NEON_CYAN, 16))
        left_layout.addWidget(brand_icon)

        lbl = QLabel("Huawei Manager", left)
        lbl.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent;"
            f" font: 11.5px '{C.FONT_UI_FAMILY}';")
        left_layout.addWidget(lbl)

        sep1 = QFrame(left)
        sep1.setFixedSize(1, 9)
        sep1.setStyleSheet(f"background: {C.BORDER_NRM}; border: none;")
        left_layout.addWidget(sep1)

        ver = QLabel("v2.0.0", left)
        ver.setStyleSheet(
            f"color: {C.FG_FAINT}; background: transparent;"
            f" font: 11px '{C.FONT_MONO_FAMILY}';")
        left_layout.addWidget(ver)
        foot_layout.addWidget(left)

        foot_layout.addStretch()

        secure = QWidget(foot)
        secure.setStyleSheet("background: transparent;")
        secure_layout = QHBoxLayout(secure)
        secure_layout.setContentsMargins(0, 0, 0, 0)
        secure_layout.setSpacing(3)

        lock = QLabel(secure)
        lock.setPixmap(icon_pixmap("i-lock", C.NEON_GREEN, 13))
        secure_layout.addWidget(lock)

        secure_lbl = QLabel("Conexão segura", secure)
        secure_lbl.setStyleSheet(
            f"color: {C.NEON_GREEN}; background: transparent;"
            f" font: 11px '{C.FONT_UI_FAMILY}';")
        secure_layout.addWidget(secure_lbl)
        foot_layout.addWidget(secure)

        sep2 = QFrame(foot)
        sep2.setFixedSize(1, 9)
        sep2.setStyleSheet(f"background: {C.BORDER_NRM}; border: none;")
        foot_layout.addWidget(sep2)

        self.clock_lbl = QLabel(foot)
        self.clock_lbl.setStyleSheet(
            f"color: {C.FG_DIM}; background: transparent;"
            f" font: 11px '{C.FONT_MONO_FAMILY}';")
        foot_layout.addWidget(self.clock_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        parent_layout.addWidget(foot)

    def _build_tab(self, key: str) -> None:
        """Constrói a aba pelo registry e registra a QWidget no shell."""
        td = tab_by_key(self._tabs, key)
        if td is None:
            return
        page = td.module.build(self._tab_context)
        if page is not None:
            self.pages[key] = page
            if self._page_container is not None:
                self._page_container.addWidget(page)

    def _toggle_mock_mode(self) -> bool:
        """Alterna o modo probe global (Real/Mock) — injetado no TabContext."""
        self._mock_mode = not self._mock_mode
        return self._mock_mode

    def _set_watcher_results(self, results: Sequence[AgentResult]) -> None:
        """Snapshot imutável (R18) dos resultados dos agentes."""
        self._watcher_results = tuple(results)

    # ── Fachadas da aba Editor de Comandos (F2-cmd) ─────────────────
    def _cmd_tab(self) -> CmdTab | None:
        """Módulo real da aba cmd (instância única do registry) + contexto.

        ``attach`` é idempotente: injeta o TabContext mesmo sem a UI
        ter sido construída (rollback via paleta, ex.).
        """
        from huawei_manager.tabs.cmd import CmdTab

        td = tab_by_key(self._tabs, "cmd")
        if td is None or not isinstance(td.module, CmdTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _get_editor_cmd(self) -> str:
        tab = self._cmd_tab()
        return "" if tab is None else tab.get_editor_cmd()

    def _run_cmd_safe(self, cmd: str = "") -> None:
        tab = self._cmd_tab()
        if tab is not None:
            tab.run_cmd_safe(cmd)

    def _run_config_safe(self, cmd: str = "") -> None:
        tab = self._cmd_tab()
        if tab is not None:
            tab.run_config_safe(cmd)

    def _rollback_last_config(self) -> None:
        tab = self._cmd_tab()
        if tab is not None:
            tab.rollback_last_config()

    def _cmd_out(self) -> QTextEdit | None:
        """Widget de saída da aba cmd (Ctrl+L limpa a saída)."""
        tab = self._cmd_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Backup (F2-backup) ──────────────────────────
    def _backup_tab(self) -> BackupTab | None:
        """Módulo real da aba backup (instância única do registry) + contexto."""
        from huawei_manager.tabs.backup import BackupTab

        td = tab_by_key(self._tabs, "backup")
        if td is None or not isinstance(td.module, BackupTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _do_backup(self, fmt: str = "") -> None:
        tab = self._backup_tab()
        if tab is not None:
            tab.run_backup(fmt)

    def _backup_out(self) -> QTextEdit | None:
        """Widget de saída da aba backup (Ctrl+L limpa a saída)."""
        tab = self._backup_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Configuração Atual (F2-config) ─────────────
    def _config_tab(self) -> ConfigTab | None:
        """Módulo real da aba config (instância única do registry) + contexto."""
        from huawei_manager.tabs.config import ConfigTab

        td = tab_by_key(self._tabs, "config")
        if td is None or not isinstance(td.module, ConfigTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _fetch_config(self) -> None:
        tab = self._config_tab()
        if tab is not None:
            tab.fetch_config()

    def _config_out(self) -> QTextEdit | None:
        """Widget de saída da aba config (Ctrl+L limpa a saída)."""
        tab = self._config_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Roteamento (F2-route) ───────────────────────
    def _route_tab(self) -> RouteTab | None:
        """Módulo real da aba route (instância única do registry) + contexto."""
        from huawei_manager.tabs.route import RouteTab

        td = tab_by_key(self._tabs, "route")
        if td is None or not isinstance(td.module, RouteTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _fetch_route(self) -> None:
        tab = self._route_tab()
        if tab is not None:
            tab.fetch_route()

    def _route_out(self) -> QTextEdit | None:
        """Widget de saída da aba route (Ctrl+L limpa a saída)."""
        tab = self._route_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Tabela ARP (F2-arp) ─────────────────────────
    def _arp_tab(self) -> ArpTab | None:
        """Módulo real da aba arp (instância única do registry) + contexto."""
        from huawei_manager.tabs.arp import ArpTab

        td = tab_by_key(self._tabs, "arp")
        if td is None or not isinstance(td.module, ArpTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _fetch_arp(self) -> None:
        tab = self._arp_tab()
        if tab is not None:
            tab.fetch_arp()

    def _arp_out(self) -> QTextEdit | None:
        """Widget de saída da aba arp (Ctrl+L limpa a saída)."""
        tab = self._arp_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Info do Sistema (F2-info) ───────────────────
    def _info_tab(self) -> InfoTab | None:
        """Módulo real da aba info (instância única do registry) + contexto."""
        from huawei_manager.tabs.info import InfoTab

        td = tab_by_key(self._tabs, "info")
        if td is None or not isinstance(td.module, InfoTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _fetch_info(self) -> None:
        tab = self._info_tab()
        if tab is not None:
            tab.fetch_info()

    def _info_out(self) -> QTextEdit | None:
        """Widget de saída da aba info (Ctrl+L limpa a saída)."""
        tab = self._info_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Dashboard (F2-home) ──────────────────────────
    def _home_tab(self) -> HomeTab | None:
        """Módulo real da aba home (instância única do registry) + contexto."""
        from huawei_manager.tabs.home import HomeTab

        td = tab_by_key(self._tabs, "home")
        if td is None or not isinstance(td.module, HomeTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _refresh_dashboard(self) -> None:
        tab = self._home_tab()
        if tab is not None:
            tab.refresh()

    # ── Fachadas da aba Serviços (F2-services) ───────────────────────
    def _services_tab(self) -> ServicesTab | None:
        """Módulo real da aba services (instância única do registry) + contexto."""
        from huawei_manager.tabs.services import ServicesTab

        td = tab_by_key(self._tabs, "services")
        if td is None or not isinstance(td.module, ServicesTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _refresh_service_list(self) -> None:
        tab = self._services_tab()
        if tab is not None:
            tab.refresh_service_list()

    def _svc_out(self) -> QTextEdit | None:
        """Widget de saída da aba services (Ctrl+L limpa a saída)."""
        tab = self._services_tab()
        return None if tab is None else tab.out_widget()

    # ── Fachadas da aba Topologia (F2-topology) ───────────────────────
    def _topology_tab(self) -> TopologyTab | None:
        """Módulo real da aba topology (instância única do registry) + contexto."""
        from huawei_manager.tabs.topology import TopologyTab

        td = tab_by_key(self._tabs, "topology")
        if td is None or not isinstance(td.module, TopologyTab):
            return None
        tab = td.module
        tab.attach(self._tab_context)
        return tab

    def _topo_canvas_widget(self) -> TopologyCanvas | None:
        tab = self._topology_tab()
        return None if tab is None else tab.state.topo_canvas

    def _device_info_widget(self) -> QLabel | None:
        tab = self._topology_tab()
        return None if tab is None else tab.state.device_info_lbl

    def _device_status_widget(self) -> QLabel | None:
        tab = self._topology_tab()
        return None if tab is None else tab.state.device_status_lbl

    # ── Navegacao ────────────────────────────────────────────────────
    def _show_page(self, key: str) -> None:
        if self._active_btn:
            self._active_btn._deactivate()
        if key not in self.pages:
            fn = self._page_builders.get(key)
            if fn:
                fn()
        target = self.pages.get(key)
        if target is not None and self._page_container is not None:
            self._page_container.setCurrentWidget(target)
        btn = self._nav_buttons.get(key)
        if btn:
            btn._activate()
            self._active_btn = btn
        self._current_page = key

        context_lbl = getattr(self, "page_context_lbl", None)
        if context_lbl is not None:
            td = tab_by_key(self._tabs, key)
            context_lbl.setText(td.label if td is not None else key)

    def _rebuild_page(self, key: str) -> None:
        td = tab_by_key(self._tabs, key)
        if td is not None:
            td.module.dispose()
        if key in self.pages:
            old = self.pages.pop(key)
            if self._page_container is not None:
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
        themes = ["dark", "light", "huawei"]
        idx = themes.index(self._theme) if self._theme in themes else 0
        self._theme = themes[(idx + 1) % len(themes)]

        try:
            settings = _preferences()
            settings.setValue("theme", self._theme)
        except Exception:
            pass

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
        if "color:" in conn_color:
            color = conn_color.replace("color: ", "").split(";")[0]
        else:
            color = C.NEON_CYAN
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
        self._update_theme_btn_label()
        theme_btn = getattr(self, "theme_btn", None)
        if theme_btn:
            theme_btn.setEnabled(False)
        QTimer.singleShot(1500, self._unlock_theme)

    def _update_theme_btn_label(self) -> None:
        theme_btn = getattr(self, "theme_btn", None)
        if theme_btn is None:
            return
        labels = {
            "dark": ("Escuro", "Alternar tema (atual: Escuro)", "i-moon"),
            "light": ("Claro", "Alternar tema (atual: Claro)", "i-sun"),
            "huawei": ("Huawei", "Alternar tema (atual: Huawei Theme)", "i-zap"),
        }
        text, tip, icon_id = labels.get(
            self._theme, ("Escuro", "Alternar tema", "i-moon"))
        theme_btn.setText(text)
        theme_btn.setToolTip(tip)
        theme_btn.setIcon(svg_icon(icon_id, C.NEON_PURP, 16))

    def _toggle_maximize(self) -> None:
        """Alterna a janela entre maximizada e tamanho padrão."""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def show_drawer(
        self,
        title: str = "Descartar configuração?",
        message: str = "",
        on_confirm: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        confirm_text: str = "Confirmar",
        cancel_text: str = "Cancelar",
        eyebrow: str = "CONFIRMAÇÃO",
        is_danger: bool = True,
    ) -> None:
        """Exibe o drawer lateral deslizante sobre a janela principal."""
        drawer = getattr(self, "_drawer", None)
        if drawer is not None:
            drawer.open_drawer(
                title=title,
                message=message,
                on_confirm=on_confirm,
                on_cancel=on_cancel,
                confirm_text=confirm_text,
                cancel_text=cancel_text,
                eyebrow=eyebrow,
                is_danger=is_danger,
            )

    def resizeEvent(self, event) -> None:
        """Garante que overlays e o drawer redimensionem com a janela."""
        super().resizeEvent(event)
        drawer = getattr(self, "_drawer", None)
        if drawer is not None:
            drawer.sync_geometry()

    def _unlock_theme(self) -> None:
        self._theme_toggling = False
        if self.theme_btn is not None:
            self.theme_btn.setEnabled(True)

    def _toggle_command_palette(self) -> None:
        """Mostra/esconde a Command Palette (Ctrl+K)."""
        if self._command_palette is None:
            from huawei_manager.widgets.command_palette import (
                CommandPalette,
                CommandRegistry,
                create_default_commands,
            )
            # Mesma lista viva: o registry muta in-place e a paleta vê as
            # mudanças no próximo filtro (abas registrando ações — Fase 0).
            cmds = create_default_commands(self)
            self._command_registry = CommandRegistry(cmds)
            self._command_palette = CommandPalette(self, cmds)
        if self._command_palette.isVisible():
            self._command_palette.hide()
        else:
            self._command_palette.show()

    def register_command(self, cmd: Command) -> None:
        """Registra um comando na palette — API para abas (Fase 0)."""
        if getattr(self, "_command_registry", None) is None:
            self._toggle_command_palette()
        registry = cast(
            "CommandRegistry | None", getattr(self, "_command_registry", None))
        if registry is not None:
            registry.register(cmd)

    def unregister_command(self, cmd_id: str) -> None:
        """Remove comando da palette pelo id — cleanup no dispose da aba."""
        registry = cast(
            "CommandRegistry | None", getattr(self, "_command_registry", None))
        if registry is not None:
            registry.unregister(cmd_id)

    def _rebuild_ui(self) -> None:
        # 1. Parar todos os timers antes de destruir widgets
        self._dash_timer.stop()
        self._device_timer.stop()
        self._poll_timer.stop()
        self._session_timer.stop()
        self._clock_timer.stop()
        if getattr(self, "_adaptive_timer", None) is not None:
            self._adaptive_timer.stop()
        # Salvar estado do watcher ANTES de parar: stop() zera is_active,
        # entao a checagem na reinicializacao (passo 5) usaria o estado errado.
        watcher_was_active = self._watcher.is_active
        self._watcher.stop()

        # 2. Salvar estado
        current_page = self._current_page
        self._active_btn = None
        self.pages.clear()
        # Widgets recriados em _build_layout/_rebuild_page: zerar refs para
        # nao apontar para objetos C++ deletados (RuntimeError/AttributeError).
        self._auth_overlay = None
        self._ui_queue.clear()

        # 3. Destruir UI antiga
        old = self.centralWidget()
        if old:
            old.setParent(None)
            old.deleteLater()
        # O ConfirmDrawer é filho da janela (não do centralWidget), portanto
        # não é destruído junto com a UI antiga. Descartar explicitamente
        # evita acumular um drawer invisível a cada troca de tema.
        old_drawer = getattr(self, "_drawer", None)
        if old_drawer is not None:
            old_drawer.hide()
            old_drawer.setParent(None)
            old_drawer.deleteLater()
            self._drawer = None
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
        if watcher_was_active:
            self._watcher.start()

class HuaweiRouterApp(AppStateMixin, ShortcutsMixin, AppCore, EventHandlers):
    """Classe final que combina os mixins AppCore e EventHandlers."""
