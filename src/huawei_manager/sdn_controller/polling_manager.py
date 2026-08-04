"""PollingManager — polling adaptativo por VNF (headless, sem Qt).

Orquestra SSHSessionFactory + StabilityTracker + IntervalDecider.
Fonte de devices online = snapshot do inventário (D6), nunca ControllerCore.
Executa em worker thread (via _spawn_io); guard de mock fica na UI thread.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from huawei_manager.constants import (
    POLL_DEFAULT_INTERVAL,
    POLL_HISTORY_SIZE,
    POLL_MAX_DEVICES,
    POLL_MAX_INTERVAL,
    POLL_MAX_WORKERS,
    POLL_MIN_INTERVAL,
    POLL_SERVICES,
    POLL_STABLE_MULTIPLIER,
)
from huawei_manager.sdn_controller.session_factory import SSHSessionFactory
from huawei_manager.services.catalog import get_service_by_id
from huawei_manager.services.vnf_service import VnfService
from huawei_manager.services_data import ServiceDef
from huawei_manager.utils import clean_output
from huawei_manager.vnf_models import VNF

log = logging.getLogger("huawei.polling")

_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]")
_COUNTER_WORDS = ("total", "average", "peers", "sessions", "rules",
                  "zones", "entries", "stations")
# Prefixos de erro-como-string do wrapper de sessão (D13) + erros reais de
# device Huawei/CLI (ex.: "% Unrecognized command", "Invalid input").
_ERROR_PREFIXES = ("ERRO:", "Sem conex", "Error:", "Unknown command",
                   "Incomplete command", "Ambiguous", "Unrecognized",
                   "Invalid input")


def _normalize_output(text: str) -> str:
    """Normaliza output p/ comparação de estabilidade.

    Remove ANSI/controle, linhas vazias, contadores, percentuais e
    timestamps — campos que mudam a cada tick sem mudança estrutural.
    """
    lines: list[str] = []
    for line in clean_output(text).splitlines():
        s = line.strip()
        if not s:
            continue
        if "%" in s or _ISO_TS.search(s):
            continue
        if s.lower().startswith(_COUNTER_WORDS):
            continue
        lines.append(s)
    return "\n".join(lines)


def _is_error_string(text: str) -> bool:
    """True se alguma linha do output é erro-como-string (D13).

    Roda sobre o output CRU (antes de _normalize_output): erros reais de
    device começam com '%' e o normalizer os descartaria como contadores.
    Linhas começando com '%' são erro Huawei (ex.: "% Unrecognized").
    """
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("%"):
            return True
        if s.lower().startswith(tuple(p.lower() for p in _ERROR_PREFIXES)):
            return True
    return False


class StabilityTracker:
    """Estabilidade por device: últimos N hashes do output normalizado.

    Todos os N hashes iguais → ESTÁVEL. Thread-safe.
    """

    def __init__(self, history_size: int = POLL_HISTORY_SIZE) -> None:
        self._history_size = max(1, history_size)
        self._history: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def record(self, device_id: str, result_sha: str) -> bool:
        """Registra hash e retorna True se o histórico está estável."""
        with self._lock:
            hist = self._history.setdefault(device_id, [])
            hist.append(result_sha)
            if len(hist) > self._history_size:
                del hist[0]
            return self._is_stable_locked(hist)

    def is_stable(self, device_id: str) -> bool:
        with self._lock:
            return self._is_stable_locked(self._history.get(device_id, []))

    def reset(self, device_id: str | None = None) -> None:
        with self._lock:
            if device_id is None:
                self._history.clear()
            else:
                self._history.pop(device_id, None)

    def get_all_states(self) -> dict[str, bool]:
        with self._lock:
            return {
                d: self._is_stable_locked(h)
                for d, h in self._history.items()
            }

    def _is_stable_locked(self, hist: list[str]) -> bool:
        # Janela cheia E todos iguais → estável (TODO 2)
        return len(hist) == self._history_size and len(set(hist)) == 1


class IntervalDecider:
    """Decide intervalo por device: instável→min, estável→×multiplier, offline→max."""

    def __init__(
        self,
        min_interval: float = POLL_MIN_INTERVAL,
        max_interval: float = POLL_MAX_INTERVAL,
        multiplier: float = POLL_STABLE_MULTIPLIER,
    ) -> None:
        self._min = min_interval
        self._max = max_interval
        self._mult = multiplier
        self._current: dict[str, float] = {}
        self._lock = threading.Lock()

    def next_interval(
        self, device_id: str, is_stable: bool, is_offline: bool = False
    ) -> float:
        with self._lock:
            if is_offline:
                self._current[device_id] = self._max
                return self._max
            if not is_stable:
                self._current[device_id] = self._min
                return self._min
            cur = self._current.get(device_id, self._min)
            nxt = min(self._max, cur * self._mult)
            self._current[device_id] = nxt
            return nxt

    def get_current_interval(self, device_id: str) -> float:
        with self._lock:
            return self._current.get(device_id, self._min)

    def reset(self, device_id: str | None = None) -> None:
        with self._lock:
            if device_id is None:
                self._current.clear()
            else:
                self._current.pop(device_id, None)


class PollingManager:
    """Polling adaptativo por device com consumo real do intervalo.

    tick() roda em worker thread e nunca lança. Guard de mock/enabled
    fica na UI thread; aqui apenas o snapshot do inventário decide.
    """

    def __init__(
        self,
        factory: SSHSessionFactory,
        vnf_service: VnfService,
        enabled: bool = True,
        poll_services: list[str] | None = None,
        max_devices: int = POLL_MAX_DEVICES,
        max_workers: int = POLL_MAX_WORKERS,
    ) -> None:
        self._factory = factory
        self._vnf_service = vnf_service
        self._enabled = enabled
        self._poll_services = list(poll_services) if poll_services else list(POLL_SERVICES)
        self._max_devices = max_devices
        self._max_workers = max_workers
        self._tracker = StabilityTracker()
        self._decider = IntervalDecider()
        self._next_due: dict[str, float] = {}
        self._next_due_lock = threading.Lock()
        self._tick_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def tick(self) -> None:
        """Roda um ciclo de polling. Nunca lança; ticks sobrepostos são ignorados."""
        if not self._enabled:
            return
        if not self._tick_lock.acquire(blocking=False):
            log.warning("tick sobreposto ignorado")
            return
        try:
            self._tick_impl()
        except Exception:
            log.exception("adaptive polling tick falhou")
        finally:
            self._tick_lock.release()

    def _tick_impl(self) -> None:
        try:
            now = time.time()
            vnfs = self._vnf_service.load_inventory()
            online = [v for v in vnfs if v.status == "online"][: self._max_devices]
            with self._next_due_lock:
                next_due = dict(self._next_due)
            due = [v for v in online if now >= next_due.get(v.id, 0)]
            if due:
                with ThreadPoolExecutor(
                    max_workers=min(self._max_workers, len(due))
                ) as pool:
                    futures = [pool.submit(self._poll_device, v) for v in due]
                    for fut in futures:
                        exc = fut.exception()
                        if exc is not None:
                            log.error("device poll future falhou: %s", exc)
        finally:
            self._factory.purge_expired()

    def _poll_device(self, vnf: VNF) -> None:
        try:
            svcs = self._matching_services(vnf)
            if not svcs:
                return
            ssb = self._factory.get(vnf)
            if ssb is None:
                # Falha de conexão/validação — backoff p/ não martelar
                self._set_next_due(vnf.id, POLL_DEFAULT_INTERVAL)
                return
            cmds = [c for s in svcs for c in (s.cli_commands or [])]
            out = ssb.send_service_commands(cmds)
            if _is_error_string(out):
                log.warning("device %s erro-como-string — instável", vnf.id)
                self._decider.next_interval(vnf.id, False)
                self._set_next_due(vnf.id, POLL_MIN_INTERVAL)
                return
            norm = _normalize_output(out)
            sha = hashlib.sha256(norm.encode("utf-8")).hexdigest()
            stable = self._tracker.record(vnf.id, sha)
            interval = self._decider.next_interval(vnf.id, stable)
            self._set_next_due(vnf.id, interval)
        except Exception:
            log.exception("device %s skip", vnf.id)
            self._factory.release(vnf.id)
            self._set_next_due(vnf.id, POLL_DEFAULT_INTERVAL)

    def _set_next_due(self, device_id: str, interval: float) -> None:
        # Anchora no tempo DE CONCLUSÃO, não no início do tick: device lento
        # (poll > intervalo) nunca é re-agendado no passado nem martelado.
        with self._next_due_lock:
            self._next_due[device_id] = time.time() + interval

    def _matching_services(self, vnf: VNF) -> list[ServiceDef]:
        vtype = vnf.type.upper()
        return [
            s for s in (get_service_by_id(i) for i in self._poll_services)
            if s is not None and vtype in s.vnf_types
        ]

    def next_due_min(self) -> float | None:
        with self._next_due_lock:
            values = list(self._next_due.values())
        return min(values) if values else None

    def get_status(self) -> dict[str, Any]:
        with self._next_due_lock:
            devices = dict(self._next_due)
        intervals = {
            d: self._decider.get_current_interval(d)
            for d in devices
        }
        return {
            "enabled": self._enabled,
            "devices": len(devices),
            "next_due_min": self.next_due_min(),
            "active_sessions": self._factory.active_sessions,
            "stable": self._tracker.get_all_states(),
            "intervals": intervals,
        }

    def force_poll(self, device_id: str, service_id: str | None = None) -> None:
        """Torna um device elegível imediatamente no próximo tick."""
        del service_id
        with self._next_due_lock:
            self._next_due.pop(device_id, None)
