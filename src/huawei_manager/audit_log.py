#!/usr/bin/env python3
"""
audit_log.py — Log estruturado de auditoria SSH/CLI (Fase 3)
=============================================================
Grava cada operação CLI em formato JSON Lines:
  huawei_audit_structured.jsonl

Cada linha é um objeto JSON com os campos:
  timestamp   — ISO 8601 UTC
  op          — operação (get-config, get, edit-config, cli-rpc, connect, ...)
  user        — usuário autenticado no roteador
  host        — IP/hostname do dispositivo
  datastore   — running | candidate | startup | None
  status      — ok | error | timeout | auth_fail
  duration_ms — tempo de resposta em milissegundos
  session_id  — ID da sessão SSH (se disponível)
  extra       — campos adicionais livres (dict)

Uso:
    from audit_log import AuditLogger
    audit = AuditLogger()
    with audit.timed("get-config", user="admin", host="10.0.0.1",
                     datastore="running") as ctx:
        result = session.get_config(...)
    # ctx.set_status("ok") é chamado automaticamente se não houver exceção
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUDIT_FILE = "huawei_audit_structured.jsonl"
_lock = threading.Lock()
_log  = logging.getLogger("huawei.audit")


# ═══════════════════════════════════════════════════════════════════════
#  ENTRY DATACLASS
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class AuditEntry:
    """Entrada individual de auditoria — uma operacao CLI com metadados."""
    timestamp:   str
    op:          str
    user:        str
    host:        str
    datastore:   str | None
    status:      str
    duration_ms: float
    session_id:  str | None
    extra:       dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
#  CONTEXT HELPER (timing)
# ═══════════════════════════════════════════════════════════════════════
class _TimedCtx:
    """Contexto usado pelo AuditLogger.timed(). Mede duração e captura status."""

    def __init__(self, logger: AuditLogger, op: str,
                 user: str, host: str,
                 datastore: str | None,
                 session_id: str | None,
                 extra: dict) -> None:
        """Inicializa o contexto com parametros da operacao a auditar."""
        self._logger     = logger
        self._op         = op
        self._user       = user
        self._host       = host
        self._datastore  = datastore
        self._session_id = session_id
        self._extra      = extra
        self._status     = "ok"
        self._t0         = 0.0

    def set_status(self, status: str) -> None:
        """Define o status final da operacao (ok, error, timeout, ...)."""
        self._status = status

    def _start(self) -> None:
        """Marca o inicio da medicao com timestamp monotônico."""
        self._t0 = time.monotonic()

    def _finish(self) -> None:
        """Calcula duracao, monta AuditEntry e escreve no log."""
        ms = (time.monotonic() - self._t0) * 1000
        self._logger._write(AuditEntry(
            timestamp   = datetime.now(UTC).isoformat(),
            op          = self._op,
            user        = self._user,
            host        = self._host,
            datastore   = self._datastore,
            status      = self._status,
            duration_ms = round(ms, 2),
            session_id  = self._session_id,
            extra       = self._extra,
        ))


# ═══════════════════════════════════════════════════════════════════════
#  AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════
class AuditLogger:
    """Logger de auditoria thread-safe, saída em JSON Lines com HMAC."""

    def __init__(self, filename: str = AUDIT_FILE, hmac_key: str = "") -> None:
        """Inicializa o logger apontando para o arquivo JSONL e chave HMAC opcional."""
        self._path = Path(filename)
        self._hmac_key = hmac_key
        _log.info("AuditLogger → %s  hmac=%s", self._path.resolve(), "on" if hmac_key else "off")

    # ── HMAC ────────────────────────────────────────────────────────────
    def _hmac(self, data: dict) -> str:
        """Gera HMAC-SHA256 do dict ordenado, ou string vazia se sem chave."""
        if not self._hmac_key:
            return ""
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hmac_mod.new(
            self._hmac_key.encode(), raw.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _verify_hmac(entry: dict, key: str) -> bool:
        """Verifica HMAC de uma entrada (remove/add hmac internamente). Retorna True se valido."""
        if not key:
            return True
        expected = entry.pop("hmac", "")
        raw = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        computed = hmac_mod.new(
            key.encode(), raw.encode(), hashlib.sha256
        ).hexdigest()
        entry["hmac"] = expected
        return hmac_mod.compare_digest(computed, expected)

    # ── escrita thread-safe ───────────────────────────────────────────
    def _write(self, entry: AuditEntry) -> None:
        """Serializa a entrada com HMAC e anexa ao arquivo JSONL (thread-safe)."""
        d = asdict(entry)
        d["hmac"] = self._hmac(d)
        line = json.dumps(d, ensure_ascii=False)
        with _lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        _log.info("AUDIT op=%-12s user=%-8s status=%-10s dt=%.1fms",
                  entry.op, entry.user, entry.status, entry.duration_ms)
        _log.debug("AUDIT host=%s", entry.host)

    # ── API direta ────────────────────────────────────────────────────
    def log_operation(
        self, op: str, user: str, host: str,
        datastore: str | None = None,
        status: str = "ok",
        duration_ms: float = 0.0,
        session_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Registra uma operação diretamente (sem medir tempo)."""
        self._write(AuditEntry(
            timestamp   = datetime.now(UTC).isoformat(),
            op          = op,
            user        = user,
            host        = host,
            datastore   = datastore,
            status      = status,
            duration_ms = duration_ms,
            session_id  = session_id,
            extra       = extra,
        ))

    # ── context manager com timing ────────────────────────────────────
    @contextmanager
    def timed(
        self, op: str, user: str, host: str,
        datastore: str | None = None,
        session_id: str | None = None,
        **extra: Any,
    ) -> Generator[_TimedCtx, None, None]:
        """
        Context manager que mede a duração e registra automaticamente.
        Em caso de exceção, define status='error' e re-levanta.

        Exemplo:
            with audit.timed("get-config", user=USER, host=HOST,
                             datastore="running") as ctx:
                data = session.get_config()
        """
        ctx = _TimedCtx(self, op, user, host, datastore, session_id, extra)
        ctx._start()
        try:
            yield ctx
        except Exception:
            ctx.set_status("error")
            raise
        finally:
            ctx._finish()

    # ── leitura das últimas N entradas ────────────────────────────────
    def tail(self, n: int = 10) -> list[dict]:
        """Retorna as últimas n entradas como lista de dicts.
        Entradas com HMAC inválido são marcadas com _hmac_valid=False."""
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if self._hmac_key and "hmac" in data:
                    valid = self._verify_hmac(data, self._hmac_key)
                    data["_hmac_valid"] = valid
                elif self._hmac_key:
                    data["_hmac_valid"] = False
                else:
                    data["_hmac_valid"] = True
                entries.append(data)
            except json.JSONDecodeError:
                pass
            if len(entries) >= n:
                break
        return list(reversed(entries))

    def format_tail(self, n: int = 5) -> str:
        """Retorna as últimas n entradas formatadas para exibição na UI."""
        entries = self.tail(n)
        if not entries:
            return "  (nenhuma entrada de auditoria ainda)"
        lines = []
        for e in entries:
            ts  = e.get("timestamp", "")[:19].replace("T", " ")
            op  = e.get("op",     "?")[:14]
            st  = e.get("status", "?")[:8]
            dt  = e.get("duration_ms", 0)
            hmac_ok = e.get("_hmac_valid", True)
            prefix = "  " if hmac_ok else "\u26a0"
            lines.append(f"{prefix} {ts}  {op:<14}  {st:<8}  {dt:>7.1f}ms")
        return "\n".join(lines)
