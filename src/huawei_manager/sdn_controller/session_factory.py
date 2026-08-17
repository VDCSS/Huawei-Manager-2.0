"""SSHSessionFactory — pool de sessões SSH per-device (polling adaptativo).

Segurança (D14/D15): credenciais estritas por Device. Host/username são
obrigatórios e password OU ssh_key também; sem nenhum fallback para as
credenciais globais (ROUTER_*) — um Device mal configurado NUNCA conecta
no roteador default. Falha de validação ou conexão → get() retorna None.

Toda auditoria gerada pelas sessões deste pool é marcada com
origin='auto-poll' via _OriginAuditWrapper.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from huawei_manager.audit_log import AuditEntry, AuditLogger, _TimedCtx
from huawei_manager.constants import POLL_ORIGIN
from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.session import NetmikoSession
from huawei_manager.vault import SecretsBackend

log = logging.getLogger("huawei.session_factory")

# TTL default > POLL_MAX_INTERVAL (300s) para nunca purgar sessão
# de um device estável entre dois polls consecutivos.
_DEFAULT_TTL = 600.0


class _OriginAuditWrapper(AuditLogger):
    """AuditLogger que injeta ``origin='auto-poll'`` em toda entrada.

    NetmikoSession usa ``audit.timed(...)`` e ``audit.log_operation(...)``
    internamente; o wrapper repassa com o extra fixo e grava no logger
    interno para manter a mesma cadeia de hashes/HMAC.
    """

    def __init__(self, inner: AuditLogger) -> None:
        self._inner = inner

    def _write(self, entry: AuditEntry) -> None:
        self._inner._write(entry)

    def log_operation(
        self,
        op: str,
        user: str,
        host: str,
        datastore: str | None = None,
        status: str = "ok",
        duration_ms: float = 0.0,
        session_id: str | None = None,
        category: str = "general",
        **extra: Any,
    ) -> None:
        extra.setdefault("origin", POLL_ORIGIN)
        self._inner.log_operation(
            op, user=user, host=host, datastore=datastore,
            status=status, duration_ms=duration_ms,
            session_id=session_id, category=category, **extra,
        )

    @contextmanager
    def timed(
        self,
        op: str,
        user: str,
        host: str,
        datastore: str | None = None,
        session_id: str | None = None,
        category: str = "general",
        **extra: Any,
    ) -> Generator[_TimedCtx, None, None]:
        extra.setdefault("origin", POLL_ORIGIN)
        with self._inner.timed(
            op, user=user, host=host, datastore=datastore,
            session_id=session_id, category=category, **extra,
        ) as ctx:
            yield ctx


@dataclass
class _PoolEntry:
    ssb: SSHSouthbound
    last_used: float


class SSHSessionFactory:
    """Pool thread-safe de SSHSouthbound por ``device.id`` com TTL de idle.

    get() cria e conecta lazy (retry via SSHSouthbound); falha → None
    (fail-closed). release()/purge_expired()/dispose() fecham sessões.
    """

    def __init__(
        self,
        backend: SecretsBackend,
        audit_logger: AuditLogger,
        session_builder: Callable[..., SSHSouthbound] | None = None,
        ttl_seconds: float = _DEFAULT_TTL,
        timeout: int = 30,
        max_retries: int = 2,
    ) -> None:
        self._backend = backend
        self._audit = _OriginAuditWrapper(audit_logger)
        self._session_builder = session_builder or self._default_builder
        self._ttl = ttl_seconds
        self._timeout = timeout
        self._max_retries = max_retries
        self._pool: dict[str, _PoolEntry] = {}
        self._lock = threading.Lock()

    @property
    def active_sessions(self) -> int:
        """Número de sessões vivas no pool (para status/UI)."""
        with self._lock:
            return len(self._pool)

    def get(self, device: Device) -> SSHSouthbound | None:
        """Retorna sessão para o Device, criando+conectando se necessário.

        Valida credenciais estritas antes de criar. Se o Device estiver
        mal configurado ou a conexão falhar, retorna None sem lançar.
        """
        with self._lock:
            existing = self._pool.get(device.id)
            if existing is not None:
                existing.last_used = time.time()
                return existing.ssb
        if not self._validate_device(device):
            return None
        ssb = self._create(device)
        if ssb is None:
            return None
        with self._lock:
            again = self._pool.get(device.id)
            if again is not None:
                again.last_used = time.time()
            else:
                self._pool[device.id] = _PoolEntry(ssb, time.time())
        # Disconnect fora do lock: I/O de rede não bloqueia outros threads.
        if again is not None:
            self._close_ssb(ssb)
            return again.ssb
        return ssb

    def release(self, device_id: str) -> None:
        """Remove device_id do pool e fecha a sessão, se houver."""
        with self._lock:
            entry = self._pool.pop(device_id, None)
        if entry is not None:
            self._close_ssb(entry.ssb)

    def purge_expired(self) -> None:
        """Fecha sessões ociosas há mais de ``ttl_seconds``."""
        now = time.time()
        expired = [
            dev_id
            for dev_id, entry in list(self._pool.items())
            if now - entry.last_used > self._ttl
        ]
        for dev_id in expired:
            self.release(dev_id)

    def dispose(self) -> None:
        """Fecha todas as sessões e esvazia o pool."""
        with self._lock:
            entries = list(self._pool.values())
            self._pool.clear()
        for entry in entries:
            self._close_ssb(entry.ssb)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _validate_device(device: Device) -> bool:
        """Credenciais estritas: host+username e password ou ssh_key."""
        if not device.host or not device.host.strip():
            log.warning("poll skip %s: host vazio", device.id)
            return False
        if not device.username:
            log.warning("poll skip %s: username vazio", device.id)
            return False
        if not device.password and not device.ssh_key:
            log.warning(
                "poll skip %s: sem password nem ssh_key (fail-closed)",
                device.id,
            )
            return False
        return True

    def _create(self, device: Device) -> SSHSouthbound | None:
        overrides = {
            "override_host": device.host,
            "override_port": device.port if device.port else 22,
            "override_username": device.username,
            "override_password": device.password or None,
            "override_ssh_key": device.ssh_key or None,
        }
        ssb = self._session_builder(self._backend, self._audit, **overrides)
        try:
            ssb.connect()
        except Exception as exc:
            # Nunca logar credenciais; apenas tipo + id do device.
            log.warning("poll connect falhou %s (%s)", device.id, type(exc).__name__)
            self._close_ssb(ssb)
            return None
        return ssb

    def _default_builder(
        self,
        backend: SecretsBackend,
        audit: AuditLogger,
        **overrides: Any,
    ) -> SSHSouthbound:
        session = NetmikoSession(backend, audit, **overrides)
        return SSHSouthbound(
            backend, audit,
            timeout=self._timeout, max_retries=self._max_retries,
            session=session,
        )

    @staticmethod
    def _close_ssb(ssb: SSHSouthbound) -> None:
        try:
            ssb.disconnect()
        except Exception:
            log.debug("disconnect falhou", exc_info=True)
