"""Detecção compartilhada de erros de sintaxe/execução da VRP.

O caminho NAPALM e o caminho Netmiko precisam da mesma definição do que é
uma linha rejeitada pelo device. Manter uma cópia só evita divergência
silenciosa (ex.: Netmiko reportar sucesso enquanto o NAPALM recusa).
"""
from __future__ import annotations

VRP_ERROR_PREFIXES = (
    "% unrecognized",
    "% wrong",
    "% invalid",
    "% incomplete",
    "% ambiguous",
    "% error",
    "% no such",
    "% no ",
    "% unsupported",
    "command not found",
    "error:",
)


def detect_vrp_errors(output: str) -> list[str]:
    """Retorna as linhas de erro detectadas na saída de comandos VRP."""
    found: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if any(low.startswith(prefix) for prefix in VRP_ERROR_PREFIXES):
            found.append(stripped)
    return found
