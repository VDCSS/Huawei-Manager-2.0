from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentItem:
    severity: str       # "info" | "warning" | "error"
    file: str           # "handlers.py:42"
    message: str        # "Senha hardcoded"
    suggestion: str     # "Mova para .env"


@dataclass
class AgentResult:
    name: str           # "dead_code"
    status: str         # "ok" | "warning" | "error"
    summary: str        # "2 funções não utilizadas"
    items: list[AgentItem] = field(default_factory=list)
