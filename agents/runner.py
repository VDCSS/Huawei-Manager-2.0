"""Executor unificado de agentes — roda todos em paralelo."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agents import AgentResult
from agents.scans import cross_ref, dead_code, deps, security, structure, style

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_all() -> list[AgentResult]:
    agents: list[Callable[[], AgentResult]] = [
        lambda: dead_code.scan(PROJECT_ROOT),
        lambda: structure.scan(PROJECT_ROOT),
        lambda: security.scan(PROJECT_ROOT),
        lambda: deps.scan(PROJECT_ROOT),
        lambda: style.scan(PROJECT_ROOT),
        lambda: cross_ref.scan(PROJECT_ROOT),
    ]
    results: list[AgentResult] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(fn) for fn in agents]
        for f in as_completed(fut):
            results.append(f.result())
    return results
