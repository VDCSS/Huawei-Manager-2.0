from __future__ import annotations

import logging

from PySide6.QtGui import QCloseEvent

_app_log = logging.getLogger("huawei.app")


class NotifyMixin:
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
