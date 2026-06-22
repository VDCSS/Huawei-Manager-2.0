"""Agente: varre credenciais hardcoded, permissões e exposição de secrets.

Nota: ficheiros .env são ignorados (ambiente lab com credenciais dummy).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.security")

SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Requer aspas no valor — evita matches em variáveis
    (re.compile(r'(?i)(password|passwd|secret|token|apikey)\s*[=:]\s*["\'][^"\']{4,}["\']'),
     "Credencial em texto claro"),
    (re.compile(r'(?i)-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----'), "Chave privada incorporada"),
    (re.compile(r'(?i)(aws_access_key_id|aws_secret_access_key)\s*[=:]\s*\S+'), "Credencial AWS"),
]

IGNORE_DIRS: set[str] = {
    ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "logs", ".git", "agents", "share", "tests",
}

IGNORE_FILES: set[str] = {
    ".env",           # ambiente lab — credenciais dummy propositais
    ".env.example",   # template — sem valores reais
    "secrets.enc.yaml",  # SOPS-encriptado — conteúdo não é texto plano
}


def _walk(root: Path) -> list[Path]:
    result: list[Path] = []
    for p in root.rglob("*.py"):
        if not any(part in p.parts for part in IGNORE_DIRS):
            result.append(p)
    # Apenas ficheiros não ignorados explicitamente
    for p in root.iterdir():
        if p.is_file() and p.name not in IGNORE_FILES and p.suffix in {".env", ".txt", ".yaml", ".yml", ".cfg"}:
            result.append(p)
    return result


def scan(root: Path) -> AgentResult:
    """Varre o projeto por credenciais hardcoded e permissões inseguras."""
    items: list[AgentItem] = []
    for fpath in _walk(root):
        if not fpath.is_file():
            continue
        if fpath.name in IGNORE_FILES:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, desc in SENSITIVE_PATTERNS:
            for m in pattern.finditer(content):
                line_num = content[:m.start()].count("\n") + 1
                rel = fpath.relative_to(root)
                items.append(AgentItem(
                    severity="error", file=f"{rel}:{line_num}",
                    message=desc,
                    suggestion="Use secrets backend em vez de string literal",
                ))

    # Permissões de ficheiros de teste
    try:
        test_dir = root / "tests"
        if test_dir.is_dir():
            for f in test_dir.rglob("*.py"):
                perms = f.stat().st_mode & 0o777
                if perms & 0o002:
                    items.append(AgentItem(
                        severity="warning", file=str(f.relative_to(root)),
                        message="Ficheiro world-writable",
                        suggestion=f"Rode: chmod o-w {f}",
                    ))
    except Exception:
        pass

    status: str = "ok"
    if items:
        status = "error" if any(i.severity == "error" for i in items) else "warning"
    n = len(items)
    summary = f"{n} problema(s) de segurança" if n else "Nenhum problema de segurança"
    return AgentResult(name="security", status=status, summary=summary, items=items)
