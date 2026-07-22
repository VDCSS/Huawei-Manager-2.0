"""Threading mixin — dispatch, spawn, write, loading helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from huawei_manager._protocols import AppCoreProtocol

_app_log = logging.getLogger("huawei.app")

# Maximum callbacks to process per _poll_queue cycle
_POLL_BATCH = 500


class ThreadingMixin:
    """Mixin com helpers de threading assincrono para a UI."""

    # ══════════════════════════════════════════════════════════════════
    #  HELPERS DE THREADING
    # ══════════════════════════════════════════════════════════════════
    def _dispatch(self: AppCoreProtocol, fn: Callable[[], object]) -> None:
        maxlen = self._ui_queue.maxlen
        if maxlen is not None and len(self._ui_queue) >= maxlen:
            _app_log.warning("UI queue overflow (%d), descartando callback", len(self._ui_queue))
            return
        self._ui_queue.append(fn)

    def _poll_queue(self: AppCoreProtocol) -> None:
        for _ in range(_POLL_BATCH):
            try:
                fn = self._ui_queue.popleft()
            except IndexError:
                break
            try:
                fn()
            except Exception:
                _app_log.exception("_poll_queue: callback %r falhou", fn)
        drained = 0
        while True:
            ev = self._event_queue.get(block=False)
            if ev is None:
                break
            drained += 1
        if drained > 0:
            _app_log.debug("Drained %d SDN events from queue", drained)

    def _spawn_io(self: AppCoreProtocol, fn, *args) -> None:
        future = self._io_executor.submit(fn, *args)
        future.add_done_callback(lambda f: f.exception() and
            _app_log.error("Task %s falhou: %s", fn.__name__, f.exception()))

    def _spawn_cpu(self: AppCoreProtocol, fn, *args) -> None:
        future = self._cpu_executor.submit(fn, *args)
        future.add_done_callback(lambda f: f.exception() and
            _app_log.error("CPU task %s falhou: %s", fn.__name__, f.exception()))

    def _run(self: AppCoreProtocol, func) -> None:
        try:
            if self._sb is None or not self._sb.is_alive():
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(None, "Aviso", "Conecte ao roteador primeiro.")
                return
        except Exception:
            from PySide6.QtWidgets import QMessageBox

            _app_log.exception("_run: is_alive() falhou")
            QMessageBox.warning(None, "Aviso", "Conexao indisponivel. Reconecte.")
            return
        self._spawn_io(func)

    def _write(self: AppCoreProtocol, widget, text: str) -> None:
        self._dispatch(lambda w=widget, t=text: (w.clear(), w.setPlainText(t)))

    def _loading(self: AppCoreProtocol, widget, msg: str) -> None:
        self._dispatch(lambda w=widget, m=msg: (w.clear(), w.setPlainText(f"\u23f3  {m}\n")))
