"""Agente: encontra funções, imports e variáveis não utilizados.

Usa análise global (todos os ficheiros src/) em vez de por-ficheiro,
eliminando falsos positivos de métodos partilhados entre mixins.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.dead_code")

# Nomes que NUNCA devem ser reportados como mortos
EXCEPTIONS: set[str] = {
    # dunder methods
    "__init__", "__enter__", "__exit__", "__aenter__", "__aexit__",
    "__str__", "__repr__", "__len__", "__iter__", "__next__",
    "__contains__", "__getitem__", "__setitem__", "__delitem__",
    "__call__", "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
    "__hash__", "__bool__", "__del__", "__new__", "__subclasshook__",
    # pytest/test hooks
    "setup_method", "teardown_method", "setup_class", "teardown_class",
    "setup", "teardown", "main", "run",
    # Public API da package — usado externamente, não em src/
    "__version__",
    # Estado interno de módulo — só atribuído, não lido diretamente
    "_active_theme",
    # Utilitários usados apenas por testes
    "_normalize_status", "_validate_credentials",
}


def _get_py_files(root: Path) -> list[Path]:
    src = root / "src"
    return list(src.rglob("*.py")) if src.is_dir() else []


def _collect_definitions(tree: ast.AST) -> set[str]:
    """Coleta todos os nomes definidos (funções, classes, imports, assignments)."""
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
    return defined


def _collect_uses(tree: ast.AST) -> set[str]:
    """Coleta todos os nomes referenciados (incluindo self.metodo via Attribute)."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            used.add(node.attr)
    return used


def scan(root: Path) -> AgentResult:
    """Varre todos os ficheiros src/ e reporta definições globalmente não utilizadas."""
    all_defs: set[str] = set()
    all_uses: set[str] = set()
    file_count = 0

    for fpath in _get_py_files(root):
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        file_count += 1
        all_defs.update(_collect_definitions(tree))
        all_uses.update(_collect_uses(tree))

    # Reporta nomes internos (com _) globalmente não referenciados
    unused: set[str] = set()
    for name in sorted(all_defs - all_uses):
        if name.startswith("_") and name not in EXCEPTIONS:
            unused.add(name)

    items = [
        AgentItem(
            severity="warning",
            file="(global)",
            message=f"'{name}' definido mas nunca referenciado",
            suggestion="Remova a definição ou adicione um uso/teste",
        )
        for name in sorted(unused)
    ]

    n = len(items)
    status = "ok" if not items else "warning"
    summary = (
        f"{n} item(ns) não utilizado(s) (em {file_count} ficheiros)"
        if n
        else "Nenhum código morto"
    )
    return AgentResult(name="dead_code", status=status, summary=summary, items=items)
