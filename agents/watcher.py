"""Watcher contínuo — monitora o projeto a cada N segundos enquanto ativo."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable

from agents import AgentResult
from agents.runner import run_all

log = logging.getLogger("huawei.agents")


class Watcher:
    def __init__(self, root: tk.Tk, on_update: Callable[[list[AgentResult]], None]) -> None:
        self._root = root
        self._on_update = on_update
        self._active = False
        self._cache: list[AgentResult] | None = None
        self._timer: str | None = None
        self._interval_ms = 60_000

    def start(self, interval_s: int = 60) -> None:
        if self._active:
            return
        self._active = True
        self._interval_ms = interval_s * 1000
        log.info("Watcher iniciado (intervalo=%ds)", interval_s)
        self._tick()

    def stop(self) -> None:
        self._active = False
        if self._timer:
            try:
                self._root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        log.info("Watcher parado")

    @property
    def is_active(self) -> bool:
        return self._active

    def _tick(self) -> None:
        if not self._active:
            return
        try:
            results = run_all()
            if results != self._cache:
                self._cache = results
                self._on_update(results)
        except Exception as exc:
            log.warning("Watcher: erro no scan — %s", exc)
        if self._active:
            self._timer = self._root.after(self._interval_ms, self._tick)
