"""Agente: verifica naming conventions, docstrings e typing."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.style")


def _get_py_files(root: Path) -> list[Path]:
    src = root / "src"
    return list(src.rglob("*.py")) if src.is_dir() else []


def scan(root: Path) -> AgentResult:
    items: list[AgentItem] = []
    for fpath in _get_py_files(root):
        if ".venv" in fpath.parts:
            continue
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = fpath.relative_to(root)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Função '{node.name}' sem docstring",
                        suggestion="Adicione um docstring descrevendo o propósito",
                    ))
                if node.name != node.name.lower() and not node.name.startswith("__"):
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Função '{node.name}' não segue snake_case",
                        suggestion="Renomeie para snake_case",
                    ))
            elif isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Classe '{node.name}' sem docstring",
                        suggestion="Adicione um docstring",
                    ))
                if node.name != node.name[0].upper() + node.name[1:]:
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Classe '{node.name}' não segue PascalCase",
                        suggestion="Renomeie para PascalCase",
                    ))

    status = "ok"
    if items:
        status = "warning" if len(items) > 3 else "ok"
    n = len(items)
    summary = f"{n} problema(s) de estilo" if n else "Estilo OK"
    return AgentResult(name="style", status=status, summary=summary, items=items)
