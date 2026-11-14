"""Detecção compartilhada de erros de sintaxe/execução da VRP.

O caminho NAPALM e o caminho Netmiko precisam da mesma definição do que é
uma linha rejeitada pelo device. Manter uma cópia só evita divergência
silenciosa (ex.: Netmiko reportar sucesso enquanto o NAPALM recusa).

Além da detecção, este módulo **atribui** cada erro ao comando que o
originou. A VRP ecoa o comando rejeitado junto do prompt (``[~NE40E]
traffic classifier C_BLOQUEIO``); sem essa atribuição o operador recebe
uma lista de mensagens idênticas e não sabe *qual* comando foi recusado.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

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

#: Eco da VRP: prompt (``<NE40E>`` / ``[~NE40E]`` / ``[*NE40E-acl-3000]``)
#: seguido do comando digitado.
_ECHO_RE = re.compile(r"^\s*[\[<][^\]>]*[\]>]\s*(?P<cmd>\S.*?)\s*$")

#: Dicas para features ausentes no device. O par (regex do comando, texto)
#: é consultado quando o comando é recusado — transformam um erro técnico
#: seco em uma ação concreta para o operador.
VRP_FEATURE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^(traffic\s+(classifier|behavior|policy)|traffic-policy|if-match"
            r"|qos\s+policy)\b",
            re.IGNORECASE,
        ),
        "Este device não implementa a cadeia de QoS/política de tráfego "
        "(classifier/behavior/policy). A feature QoS não está disponível "
        "nesse modelo/imagem — aplique em um device com QoS habilitado "
        "(em imagens EVE-NG do NE40E o comando é recusado com "
        "'Unrecognized command').",
    ),
    (
        re.compile(r"^traffic-filter\b", re.IGNORECASE),
        "Este device não implementa 'traffic-filter' (feature de filtragem "
        "por ACL ausente). Use a cadeia 'traffic policy' em um device com "
        "QoS habilitado.",
    ),
)


@dataclass(frozen=True)
class VRPCommandError:
    """Erro de VRP associado (quando possível) ao comando rejeitado."""

    command: str
    message: str


def detect_vrp_errors(output: str) -> list[str]:
    """Retorna as linhas de erro detectadas na saída de comandos VRP."""
    found: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if any(low.startswith(prefix) for prefix in VRP_ERROR_PREFIXES):
            found.append(stripped)
    return found


def _normalize(text: str) -> str:
    return " ".join(text.split())


def attribute_vrp_errors(
    output: str, commands: Sequence[str]
) -> list[VRPCommandError]:
    """Atribui cada erro da saída ao comando que o originou.

    A VRP ecoa o comando recusado após o prompt; a linha de erro vem logo
    abaixo. Percorrendo a saída e guardando o último eco conhecido, cada
    erro fica vinculado ao comando correspondente. Erros sem eco
    reconhecível são devolvidos com ``command=""`` (atribuição indisponível).
    """
    wanted = {_normalize(cmd) for cmd in commands}
    attributed: list[VRPCommandError] = []
    current = ""
    for line in output.splitlines():
        match = _ECHO_RE.match(line)
        if match:
            candidate = match.group("cmd")
            if _normalize(candidate) in wanted:
                current = candidate.strip()
            else:
                current = ""
            continue
        stripped = line.strip()
        low = stripped.lower()
        if any(low.startswith(prefix) for prefix in VRP_ERROR_PREFIXES):
            attributed.append(VRPCommandError(command=current, message=stripped))
    return attributed


def hint_for_command(command: str) -> str:
    """Dica acionável para um comando recusado (feature ausente)."""
    if not command:
        return ""
    for pattern, hint in VRP_FEATURE_HINTS:
        if pattern.match(command.strip()):
            return hint
    return ""


def format_vrp_errors(errors: Sequence[VRPCommandError]) -> str:
    """Monta a mensagem de recusa da VRP, comando a comando.

    O mesmo erro repetido (ex.: o device recusa 5 linhas) aparece uma vez
    por comando, e as dicas de feature ausente são anexadas ao final.
    """
    if not errors:
        return "Configuração recusada pela VRP."
    lines = ["Configuração recusada pela VRP:"]
    seen: set[tuple[str, str]] = set()
    for err in errors:
        key = (err.command, err.message)
        if key in seen:
            continue
        seen.add(key)
        if err.command:
            lines.append(f"  • `{err.command}` → {err.message}")
        else:
            lines.append(f"  • {err.message}")
    hints = {
        hint_for_command(err.command)
        for err in errors
        if err.command and hint_for_command(err.command)
    }
    for hint in sorted(hints):
        lines.append(f"💡 {hint}")
    return "\n".join(lines)


def describe_vrp_failure(
    output: str, commands: Sequence[str]
) -> str:
    """Mensagem de recusa da VRP a partir da saída crua do device.

    Atribui os erros aos comandos e anexa as dicas de feature ausente.
    """
    errors = attribute_vrp_errors(output, commands)
    if not errors:
        errors = [
            VRPCommandError(command="", message=msg)
            for msg in detect_vrp_errors(output)
        ]
    return format_vrp_errors(errors)
