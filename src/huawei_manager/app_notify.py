from __future__ import annotations


class NotifyMixin:
    def _cleanup_executors(self) -> None:
        for pool in (self._io_executor, self._cpu_executor):
            if pool is not None:
                pool.shutdown(wait=False)

    def _on_close(self) -> None:
        if getattr(self, "_adaptive_timer", None) is not None:
            self._adaptive_timer.stop()
        if getattr(self, "_session_factory", None) is not None:
            self._session_factory.dispose()
        self._watcher.shutdown()
        self._sb.disconnect()
        self._cleanup_executors()

    def closeEvent(self, event) -> None:
        self._on_close()
        super().closeEvent(event)
