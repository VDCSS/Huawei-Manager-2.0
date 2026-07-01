"""Agente: valida estrutura de diretórios e arquivos esperados."""

from __future__ import annotations

import logging
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.structure")

REQUIRED_DIRS = [
    "src/huawei_manager",
    "tests",
    "share/icons",
    "share/shell",
    "share/shell/completion",
    "data",
    "setup",
]

REQUIRED_FILES = [
    "src/huawei_manager/__init__.py",
    "src/huawei_manager/app.py",
    "src/huawei_manager/pages.py",
    "src/huawei_manager/handlers.py",
    "src/huawei_manager/session.py",
    "src/huawei_manager/topology.py",
    "src/huawei_manager/vault.py",
    "src/huawei_manager/services.py",
    "src/huawei_manager/utils.py",
    "src/huawei_manager/audit_log.py",
    "src/huawei_manager/constants.py",
    "src/huawei_manager/widgets.py",
    "src/huawei_manager/_config.py",
    "pyproject.toml",
    "Makefile",
    "setup/setup.sh",
]


def scan(root: Path) -> AgentResult:
    items: list[AgentItem] = []
    for d in REQUIRED_DIRS:
        p = root / d
        if not p.is_dir():
            items.append(AgentItem(
                severity="error", file=d,
                message=f"Diretório obrigatório ausente: {d}",
                suggestion="Crie o diretório",
            ))
    for f in REQUIRED_FILES:
        p = root / f
        if not p.is_file():
            items.append(AgentItem(
                severity="error", file=f,
                message=f"Arquivo obrigatório ausente: {f}",
                suggestion="Verifique se o arquivo existe",
            ))
    status = "ok"
    if items:
        status = "error" if any(i.severity == "error" for i in items) else "warning"
    n = len(items)
    summary = f"{n} problema(s) de estrutura" if n else "Estrutura OK"
    return AgentResult(name="structure", status=status, summary=summary, items=items)
