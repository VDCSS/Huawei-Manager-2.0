"""Verificações **pré-aplicação** contra o estado real do device.

Duas checagens evitam erro de sintaxe no device:

1. **Interface inexistente** — o campo "interface" aceita qualquer nome
   sintaticamente válido (``GigabitEthernet0/0/1``), mas o device só aceita
   interfaces que existem. Sem esta checagem a VRP responde
   ``Error: Wrong parameter found at '^' position`` e o operador fica sem
   saber qual é o nome correto.
2. **Linhas de aplicação** — o bloco pode referenciar a mesma interface
   mais de uma vez; a checagem lista as interfaces efetivamente usadas.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

#: Linha de bloco que abre o contexto de interface: ``interface <nome>``.
_INTERFACE_LINE_RE = re.compile(r"^\s*interface\s+(?P<name>\S+)\s*$")


def interfaces_in_block(lines: Iterable[str]) -> list[str]:
    """Interfaces referenciadas pelo bloco de configuração (ordem única)."""
    found: list[str] = []
    for line in lines:
        match = _INTERFACE_LINE_RE.match(line)
        if match:
            name = match.group("name")
            if name not in found:
                found.append(name)
    return found


def missing_interfaces(
    snapshot: str, interfaces: Sequence[str]
) -> list[str]:
    """Interfaces que **não** existem no ``running-config`` informado.

    A comparação ignora maiúsculas/minúsculas e espaços ao redor do nome
    (o device grava ``interface GigabitEthernet0/0/1``).
    """
    known = {
        match.group("name").lower()
        for match in (
            _INTERFACE_LINE_RE.match(line) for line in snapshot.splitlines()
        )
        if match is not None
    }
    missing: list[str] = []
    for name in interfaces:
        if name.lower() not in known:
            missing.append(name)
    return missing
