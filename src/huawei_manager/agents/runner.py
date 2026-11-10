"""Executor unificado de agentes — roda todos em paralelo.

Cada scan tem timeout individual e exceção isolada —
um scan lento ou com erro não bloqueia os outros.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult
from huawei_manager.agents.scans import cross_ref, dead_code, deps, security, structure, style

log = logging.getLogger("huawei.agents.runner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

SCAN_TIMEOUT_S = 15


def _safe(fn: Callable[[], AgentResult], name: str) -> AgentResult:
    """Executa um scan com timeout e captura qualquer exceção."""
    try:
        return fn()
    except TimeoutError:
        return AgentResult(
            name=name, status="error",
            summary=f"Timeout (> {SCAN_TIMEOUT_S}s)",
            items=[AgentItem(severity="error", file="(timeout)",
                             message=f"Scan '{name}' excedeu {SCAN_TIMEOUT_S}s",
                             suggestion="Verifique se há muitos arquivos ou loops infinitos")],
        )
    except Exception as exc:
        log.exception("Agente %s falhou", name)
        return AgentResult(
            name=name, status="error",
            summary=f"Exceção: {exc}",
            items=[AgentItem(severity="error", file="(exception)",
                             message=f"Scan '{name}' falhou: {exc}",
                             suggestion="Verifique o log para traceback completo")],
        )


def run_all() -> list[AgentResult]:
    agents: list[tuple[Callable[[], AgentResult], str]] = [
        (lambda: dead_code.scan(PROJECT_ROOT), "dead_code"),
        (lambda: structure.scan(PROJECT_ROOT), "structure"),
        (lambda: security.scan(PROJECT_ROOT), "security"),
        (lambda: deps.scan(PROJECT_ROOT), "deps"),
        (lambda: style.scan(PROJECT_ROOT), "style"),
        (lambda: cross_ref.scan(PROJECT_ROOT), "cross_ref"),
    ]
    results: list[AgentResult] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_safe, fn, name): name for fn, name in agents}
        for f in as_completed(futures, timeout=30):
            name = futures[f]
            try:
                results.append(f.result(timeout=1))
            except Exception:
                results.append(AgentResult(
                    name=name, status="error",
                    summary="Falha ao coletar resultado",
                    items=[],
                ))
    return results
