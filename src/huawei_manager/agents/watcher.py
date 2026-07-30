"""Watcher contínuo — monitora o projeto a cada N segundos enquanto ativo."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer

from huawei_manager.agents import AgentResult
from huawei_manager.agents.runner import run_all

log = logging.getLogger("huawei.agents")


class Watcher:
    """Watcher baseado em QTimer que varre o projeto periodicamente.

    Varreduras rodam em thread separada para não bloquear a UI.
    """

    def __init__(self, parent: QObject, on_update: Callable[[list[AgentResult]], None]) -> None:
        self._on_update = on_update
        self._active = False
        self._cache: list[AgentResult] | None = None
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._tick)
        self._interval_ms = 60_000
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="watcher")
        self._scanning = False

    def start(self, interval_s: int = 60) -> None:
        if self._active:
            return
        self._active = True
        self._interval_ms = interval_s * 1000
        log.info("Watcher iniciado (intervalo=%ds)", interval_s)
        self._tick()
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        self._active = False
        self._scanning = False
        if self._timer.isActive():
            self._timer.stop()
        log.info("Watcher parado")

    @property
    def is_active(self) -> bool:
        return self._active

    def shutdown(self) -> None:
        """Para o timer e finaliza o pool de threads."""
        self.stop()
        self._executor.shutdown(wait=True)

    def _tick(self) -> None:
        if not self._active or self._scanning:
            return
        self._scanning = True
        try:
            self._executor.submit(self._run_scan)
        except RuntimeError:
            # Executor shut down — reseta flag
            self._scanning = False
            log.warning("Watcher: executor rejeitou scan (shutdown?)")

    def _run_scan(self) -> None:
        try:
            results = run_all()
            if results != self._cache:
                self._cache = results
                self._on_update(results)
        except Exception as exc:
            log.warning("Watcher: erro no scan — %s", exc)
        finally:
            self._scanning = False
