"""AppCoreProtocol — type‑safe contract for mixin inheritance.

Defines the shared interface that AppCore provides to its 11 mixins
(7 handlers + 3 pages + 1 threading). Using ``self: AppCoreProtocol``
on each mixin method eliminates ~150 pyright ``reportAttributeAccessIssue``
warnings for cross‑mixin attribute access.

Attributes that are purely local to one mixin (e.g. ``_dash_conn_status``,
``_cmd_editor``) are intentionally **not** covered — they generate ~150
remaining warnings, which is accepted (Momus review, Round 3 plan).
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from huawei_manager.sdn_controller.authz import SessionTracker
from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.southbound import SouthboundProtocol
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.services.vnf_service import VnfService
from huawei_manager.vnf_models import VNF

if TYPE_CHECKING:
    from huawei_manager.widgets.auth_overlay import AuthOverlay


@runtime_checkable
class AppCoreProtocol(Protocol):
    """Shared attributes & methods that AppCore provides to all mixins.

    Usage in a mixin::

        def some_method(self: AppCoreProtocol, arg: str) -> None:
            self._sb.send_command(arg)   # now type‑safe
    """

    # ── Southbound / SSH ──────────────────────────────────────────────
    _sb: SouthboundProtocol
    session: object | None          # NetmikoSession — avoid hard import
    _target_vnf: VNF | None

    # ── Events & Auth ─────────────────────────────────────────────────
    _event_queue: IEventBus
    _session_tracker: SessionTracker
    _access_level: str
    _mock_mode: bool

    # ── Threading ─────────────────────────────────────────────────────
    _ui_queue: deque[Callable[[], object]]
    _io_executor: ThreadPoolExecutor
    _cpu_executor: ThreadPoolExecutor

    # ── VNF / Topology ────────────────────────────────────────────────
    _vnfs: list[VNF]
    _vnfs_lock: threading.Lock
    _topo_canvas: object | None     # TopologyCanvas — avoids Qt import
    _watcher: object | None         # Watcher — avoids agent import
    _vnf_service: VnfService | None  # Domain service (set by AppCore)

    # ── Validator & Dry‑run ───────────────────────────────────────────
    _cmd_validator: CommandValidator | None
    _dry_run: DryRunEngine | None

    # ── Auth state ────────────────────────────────────────────────────
    _auth_overlay: AuthOverlay | None
    _admin_attempts: int
    _admin_locked_until: float
    _sysview_var: bool
    backup_path: str

    # ── UI content area (used by AuthOverlay) ─────────────────────────
    content: object | None          # QWidget — avoids Qt import

    # ── Methods shared across mixins ──────────────────────────────────
    def _dispatch(self, fn: Callable[[], object]) -> None: ...
    def _spawn_io(self, fn: Callable[..., object], *args: object) -> None: ...
    def _spawn_cpu(self, fn: Callable[..., object], *args: object) -> None: ...
    def _write(self, widget: object, text: str) -> None: ...
    def _loading(self, widget: object, msg: str) -> None: ...
    def _set_status(self, text: str, color: str) -> None: ...
    def _set_conn_btn(self, text: str = "", disabled: bool = False) -> None: ...
    def _rebuild_page(self, page: str) -> None: ...
    def _get_selected_vnf(self) -> VNF | None: ...
