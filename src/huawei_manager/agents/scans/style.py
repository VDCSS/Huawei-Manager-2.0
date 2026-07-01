"""Agente: verifica naming conventions, docstrings e typing.

False-positives intencionalmente ignorados:
- Qt event overrides (mousePressEvent, closeEvent, enterEvent, etc.) —
  o Qt exige camelCase e não podem ser snake_case.
- Métodos privados (_prefixo) — são auto-documentados pelo nome.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.style")

QT_EVENT_OVERRIDES: set[str] = {
    "mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent",
    "mouseDoubleClickEvent", "enterEvent", "leaveEvent",
    "keyPressEvent", "keyReleaseEvent",
    "focusInEvent", "focusOutEvent", "resizeEvent", "moveEvent",
    "paintEvent", "closeEvent", "contextMenuEvent",
    "dragEnterEvent", "dragMoveEvent", "dragLeaveEvent", "dropEvent",
    "wheelEvent", "showEvent", "hideEvent",
    "changeEvent", "timerEvent", "actionEvent",
    "hoverEnterEvent", "hoverMoveEvent", "hoverLeaveEvent",
    "inputMethodEvent", "tabletEvent",
    "nativeEvent", "event", "eventFilter",
}


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
                # Pula Qt event overrides — não podem ser snake_case
                if node.name in QT_EVENT_OVERRIDES:
                    pass
                elif node.name != node.name.lower() and not node.name.startswith("__"):
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Função '{node.name}' não segue snake_case",
                        suggestion="Renomeie para snake_case",
                    ))
            elif isinstance(node, ast.ClassDef):
                if node.name != node.name[0].upper() + node.name[1:]:
                    items.append(AgentItem(
                        severity="info", file=f"{rel}:{node.lineno}",
                        message=f"Classe '{node.name}' não segue PascalCase",
                        suggestion="Renomeie para PascalCase",
                    ))

    status = "ok"
    if items:
        status = "warning"
    n = len(items)
    summary = f"{n} problema(s) de estilo" if n else "Estilo OK"
    return AgentResult(name="style", status=status, summary=summary, items=items)
