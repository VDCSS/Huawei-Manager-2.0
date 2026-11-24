"""Agente: verifica constantes definidas em constants.py × usadas no projeto.

Apenas constants.py é a fonte canónica de constantes — o scan cruza
cada constante ALL_CAPS com as referências reais em todos os src/,
incluindo acessos via alias (`import ... as C` → C.FONT_H1).
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.cross_ref")

SKIP = {"True", "False", "None"}

# Módulo canónico de constantes
CONST_MODULE = "huawei_manager.constants"


def _collect_const_assignments(tree: ast.AST) -> set[str]:
    """Devolve nomes ALL_CAPS definidos via Assign no módulo."""
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    result.add(t.id)
    return result


def _collect_const_aliases(root: Path) -> set[str]:
    aliases: set[str] = set()
    dirs = [root / "src", root / "tests"]
    for d in dirs:
        if not d.is_dir():
            continue
        for fpath in d.rglob("*.py"):
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == CONST_MODULE:
                            aliases.add(alias.asname or CONST_MODULE)
                elif isinstance(node, ast.ImportFrom):
                    if node.module == CONST_MODULE:
                        pass
    return aliases


def _collect_all_caps_uses(root: Path, const_aliases: set[str]) -> set[str]:
    used: set[str] = set()
    dirs = [root / "src", root / "tests"]
    for d in dirs:
        if not d.is_dir():
            continue
        for fpath in d.rglob("*.py"):
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id.isupper():
                    used.add(node.id)
                if isinstance(node, ast.Attribute) and node.attr.isupper():
                    if isinstance(node.value, ast.Name) and node.value.id in const_aliases:
                        used.add(node.attr)
    return used


def scan(root: Path) -> AgentResult:
    """Cruza definições de constants.py com usos no projeto."""
    const_file = root / "src" / "huawei_manager" / "constants.py"
    if not const_file.is_file():
        return AgentResult(name="cross_ref", status="error",
                           summary="constants.py não encontrado", items=[])

    defined: set[str] = _collect_const_assignments(
        ast.parse(const_file.read_text(encoding="utf-8"))
    )
    const_aliases: set[str] = _collect_const_aliases(root)
    used: set[str] = _collect_all_caps_uses(root, const_aliases)
    unused = defined - used - SKIP

    items = [
        AgentItem(
            severity="info",
            file="constants.py",
            message=f"Constante '{name}' definida mas não referenciada",
            suggestion="Remova a constante ou adicione uso",
        )
        for name in sorted(unused)
    ]

    status: str = "ok"
    if items:
        status = "info" if len(items) < 3 else "warning"
    n = len(items)
    summary = f"{n} constante(s) de constants.py não referenciada(s)" if n else "Cross-refs OK"
    return AgentResult(name="cross_ref", status=status, summary=summary, items=items)
