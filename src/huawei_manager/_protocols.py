"""AppCoreProtocol — type-safe contract for mixin inheritance."""
from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.authz import SessionTracker
from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.southbound import SouthboundProtocol
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.services.device_service import DeviceService

if TYPE_CHECKING:
    from huawei_manager.sdn_controller.event_queue import Event
    from huawei_manager.widgets.auth_overlay import AuthOverlay


@runtime_checkable
class AppCoreProtocol(Protocol):
    _sb: SouthboundProtocol
    session: object | None
    _target_device: Device | None

    _event_queue: IEventBus
    _session_tracker: SessionTracker
    _access_level: str
    _mock_mode: bool

    _ui_queue: deque[Callable[[], object]]
    _io_executor: ThreadPoolExecutor
    _cpu_executor: ThreadPoolExecutor
    _event_drop_count: int

    _devices: list[Device]
    _devices_lock: threading.Lock
    _topo_canvas: object | None
    _watcher: object | None
    _device_service: DeviceService | None

    _cmd_validator: CommandValidator | None
    _dry_run: DryRunEngine | None

    _auth_overlay: AuthOverlay | None
    _admin_attempts: int
    _admin_locked_until: float
    _sysview_var: bool
    backup_path: str

    content: object | None

    def _dispatch(self, fn: Callable[[], object], *, sdn: bool = False) -> None: ...
    def _on_sdn_event(self, ev: Event | None) -> None: ...
    def _spawn_io(self, fn: Callable[..., object], *args: object) -> None: ...
    def _spawn_cpu(self, fn: Callable[..., object], *args: object) -> None: ...
    def _write(self, widget: object, text: str) -> None: ...
    def _loading(self, widget: object, msg: str) -> None: ...
    def _set_status(self, text: str, color: str) -> None: ...
    def _set_conn_btn(self, text: str = "", disabled: bool = False) -> None: ...
    def _rebuild_page(self, page: str) -> None: ...
    def _get_selected_device(self) -> Device | None: ...
