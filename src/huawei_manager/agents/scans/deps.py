"""Agente: verifica imports × dependências declaradas no pyproject.toml."""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from huawei_manager.agents import AgentItem, AgentResult

log = logging.getLogger("huawei.agents.deps")

STDLIB_MODULES: set[str] = {
    "abc", "ast", "asyncio", "atexit", "base64", "collections", "concurrent", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "decimal", "difflib", "enum", "functools",
    "__future__",
    "glob", "hashlib", "hmac", "html", "http", "importlib", "inspect", "io",
    "itertools", "json", "linecache", "logging", "math", "multiprocessing",
    "numbers", "operator", "os", "pathlib", "pickle", "platform", "pprint",
    "queue", "random", "re", "secrets", "shutil", "signal", "socket", "sqlite3",
    "statistics", "string", "struct", "subprocess", "sys", "tempfile", "textwrap",
    "threading", "time", "tkinter", "traceback", "types", "typing",
    "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
}

# Módulos first/third-party conhecidos que NÃO precisam estar em pyproject.toml
KNOWN_OK: set[str] = {
    "netmiko", "hvac", "boto3", "dotenv", "yaml", "cryptography",
    "pytest", "ruff", "pyright",
}

# Módulos que são pacotes locais do projeto (não externos)
LOCAL_PACKAGES: set[str] = {
    "agents", "huawei_manager", "tests",
    "_factories",  # test helper module (tests/_factories.py)
}

# Package name → módulo importável (quando diferem)
PACKAGE_ALIASES: dict[str, str] = {
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
}


def _collect_imports(root: Path) -> set[str]:
    """Retorna top-level imports de todos os .py (excluindo .venv)."""
    imports: set[str] = set()
    for fpath in root.rglob("*.py"):
        if ".venv" in fpath.parts or ".pytest_cache" in fpath.parts:
            continue
        try:
            tree = ast.parse(fpath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    return imports


def _parse_pyproject_deps(root: Path) -> tuple[set[str], set[str]]:
    """Retorna (deps_obrigatórias, dev_deps) do pyproject.toml via regex."""
    runtime: set[str] = set()
    dev: set[str] = set()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return runtime, dev

    text = pyproject.read_text(encoding="utf-8")
    section: str | None = None
    lines = iter(text.splitlines())

    for line in lines:
        stripped = line.strip()

        # Deteta secção
        m = re.match(r'^\[(project|project\.optional-dependencies)\]', stripped)
        if m:
            section = m.group(1)
            continue
        if stripped.startswith("["):
            section = None
            continue

        if not section:
            continue

        # [project] usa dependencies = [...] inline
        if section == "project":
            if stripped.startswith("dependencies"):
                # Extrai todos os strings do array [...]
                array_content = stripped.split("=", 1)[1].strip()
                # Se o array continua em múltiplas linhas, acumula
                if array_content.startswith("["):
                    _buf = array_content
                    _in_array = "]" not in _buf
                    while _in_array:
                        line = next(lines, None)
                        if line is None:
                            break
                        _buf += " " + line.strip()
                        _in_array = "]" not in _buf
                    array_content = _buf
                for raw in array_content.strip("[]").split(","):
                    raw = raw.strip().strip('"').strip("'")
                    if raw:
                        pkg = re.split(r'[\[>=<!~]', raw)[0].strip()
                        if pkg:
                            runtime.add(pkg)
            continue

        # [project.optional-dependencies] usa [toML.table]header = ["val", ...]
        if "=" in stripped:
            pkg = stripped.split("=", 1)[0].strip().strip('"').strip("'")
            # Limpa extras tipo [security] e version specifiers
            pkg = re.split(r'[\[>=<!~]', pkg)[0].strip()
            if not pkg:
                continue
            if "dev" in section:
                dev.add(pkg)
            else:
                runtime.add(pkg)

    return runtime, dev


def scan(root: Path) -> AgentResult:
    """Cruza imports reais com dependências declaradas."""
    imports = _collect_imports(root)
    runtime, dev = _parse_pyproject_deps(root)

    # Mapeia package names canónicos para módulos importáveis
    declared_modules: set[str] = set()
    for pkg in runtime | dev:
        declared_modules.add(PACKAGE_ALIASES.get(pkg, pkg))

    items: list[AgentItem] = []

    # Dependências não declaradas
    missing: list[str] = []
    for mod in sorted(imports):
        if mod in STDLIB_MODULES or mod in KNOWN_OK or mod in LOCAL_PACKAGES:
            continue
        if mod not in declared_modules:
            missing.append(mod)

    if missing:
        items.append(AgentItem(
            severity="warning", file="pyproject.toml",
            message=f"Dependências não declaradas: {', '.join(missing)}",
            suggestion="Adicione ao [project.dependencies] ou [project.optional-dependencies] dev",
        ))

    # Dependências declaradas não utilizadas
    unused: list[str] = []
    for pkg, mod in sorted(PACKAGE_ALIASES.items()):
        if pkg in runtime and mod not in imports:
            unused.append(pkg)

    if unused:
        items.append(AgentItem(
            severity="info", file="pyproject.toml",
            message=f"Dependências não utilizadas: {', '.join(unused)}",
            suggestion="Remova do pyproject.toml",
        ))

    n = len(missing) + len(unused)
    status = "warning" if missing else "ok"
    summary = f"{n} inconsistência(s) de dependências" if n else "Dependências OK"
    return AgentResult(name="deps", status=status, summary=summary, items=items)
