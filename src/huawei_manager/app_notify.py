from __future__ import annotations


class NotifyMixin:
    def _cleanup_executors(self) -> None:
        for pool in (self._io_executor, self._cpu_executor):
            if pool is not None:
                pool.shutdown(wait=True, timeout=5)

    def _on_close(self) -> None:
        self._watcher.shutdown()
        self._sb.disconnect()
        self._cleanup_executors()

    def closeEvent(self, event) -> None:
        self._on_close()
        super().closeEvent(event)
