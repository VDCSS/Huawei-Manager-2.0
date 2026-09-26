from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

if TYPE_CHECKING:
    from concurrent.futures import ThreadPoolExecutor

    from huawei_manager.agents.watcher import Watcher
    from huawei_manager.sdn_controller.session_factory import SSHSessionFactory
    from huawei_manager.sdn_controller.southbound import SouthboundProtocol

_app_log = logging.getLogger("huawei.app")


class NotifyMixin(QMainWindow if TYPE_CHECKING else object):
    if TYPE_CHECKING:
        # Membros do AppCore usados aqui (self é implícito: closeEvent precisa
        # de super(), que não funciona com self de protocolo).
        _io_executor: ThreadPoolExecutor
        _cpu_executor: ThreadPoolExecutor
        _session_factory: SSHSessionFactory
        _watcher: Watcher
        _sb: SouthboundProtocol
        _shutdown: bool

    def _cleanup_executors(self) -> None:
        for pool in (self._io_executor, self._cpu_executor):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

    def _on_close(self) -> None:
        self._shutdown = True                      # 1ª LINHA (R13)
        for attr in ("_adaptive_timer", "_poll_timer", "_device_timer",
                     "_dash_timer", "_session_timer", "_clock_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                t.stop()
        if getattr(self, "_session_factory", None) is not None:
            self._session_factory.dispose()
        self._watcher.shutdown(wait=False)
        self._sb.disconnect()
        self._cleanup_executors()

    def closeEvent(self, event: QCloseEvent, /) -> None:
        try:
            self._on_close()
        except Exception:
            _app_log.exception("closeEvent: _on_close falhou — continuando fechamento")
        super().closeEvent(event)
