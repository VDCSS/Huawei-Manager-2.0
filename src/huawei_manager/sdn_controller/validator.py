"""Command Validator — Allow-list and deny-list para comandos CLI.

Valida comandos contra listas de permitidos/negados antes da execucao.
Roles privilegiados (admin/tecnico) podem liberar comandos negados via
bypass de politica (``bypass_2fa``). NAO existe mecanismo 2FA: a camada
de execucao DEVE exigir confirmacao explicita antes de executar um
comando liberado por bypass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Comandos sempre permitidos (show/display)
_DEFAULT_ALLOW_PATTERNS: list[str] = [
    r"^display\s+",
    r"^show\s+",
]

# Comandos sempre negados
_DEFAULT_DENY_PATTERNS: list[str] = [
    r"^format\s+flash",
    r"^reset\s+saved-configuration",
    r"^undo\s+startup",
    r"\bdelete\b",
    r"\breset\b",
]

# Roles que podem liberar comandos negados (bypass de politica)
_BYPASS_ROLES: set[str] = {"admin", "tecnico"}

# Separadores de comando aceitos pelo VRP: encadeiam comandos na mesma
# linha (ex.: ``display version;system-view``). O pipe (``|``) NAO divide:
# e filtro de output legitimo (``display cpu-usage | include cpu``).
_CMD_SEPARATORS = re.compile(r"[;\r\n]+")


@dataclass
class ValidationResult:
    """Resultado da validacao de um comando.

    Attributes:
        allowed: True se o comando pode ser executado.
        reason: Mensagem explicativa (None se allowed=True sem bypass).
        bypass_2fa: True se o comando foi liberado por bypass de politica
            (roles privilegiados). NAO e um mecanismo 2FA — a camada de
            execucao deve exigir confirmacao explicita do operador.
    """

    allowed: bool
    reason: str | None = None
    bypass_2fa: bool = False


class CommandValidator:
    """Validador de comandos CLI com allow-list e deny-list.

    Args:
        allow_patterns: Lista de padroes regex de comandos permitidos.
            Padrao: displays/shows.
        deny_patterns: Lista de padroes regex de comandos negados.
            Padrao: format flash, reset saved-configuration, undo
            startup, delete.*, reset.*.
    """

    def __init__(
        self,
        allow_patterns: list[str] | None = None,
        deny_patterns: list[str] | None = None,
    ) -> None:
        self._allow = [
            re.compile(p, re.IGNORECASE)
            for p in (allow_patterns or _DEFAULT_ALLOW_PATTERNS)
        ]
        self._deny = [
            re.compile(p, re.IGNORECASE)
            for p in (deny_patterns or _DEFAULT_DENY_PATTERNS)
        ]

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self, command: str, role: str = "user") -> ValidationResult:
        """Valida um buffer de comandos contra allow-list e deny-list.

        O buffer e dividido em comandos logicos por separadores VRP
        (``;``, ``\\r``, ``\\n``) e cada parte e validada
        individualmente — um comando negado encadeado a um permitido
        nao escapa da politica. O pipe (``|``) nao divide.

        Regras por comando logico:
        1. Deny-list primeiro: deny vence allow.
        2. Deny-list + role com bypass → permitido (bypass de politica;
           exige confirmacao explicita na camada de execucao).
        3. Deny-list + role sem bypass → negado.
        4. Allow-list → permitido.
        5. Desconhecido (nem allow nem deny) → negado.

        Args:
            command: Buffer de comandos CLI a ser validado.
            role: Papel do usuario (user, tecnico, admin).

        Returns:
            ``ValidationResult`` com o resultado da validacao.
        """
        if not command.strip():
            return ValidationResult(allowed=False, reason="Empty command")

        parts = _split_logical(command)
        if not parts:
            return ValidationResult(allowed=False, reason="Empty command")

        for part in parts:
            result = self._validate_one(part, role)
            if not result.allowed:
                return result
            if result.bypass_2fa:
                return result
        return ValidationResult(allowed=True)

    def _validate_one(self, command: str, role: str) -> ValidationResult:
        """Valida um comando logico unico (sem separadores)."""
        # Deny-list primeiro: deny vence allow (invariante de seguranca)
        for pattern in self._deny:
            if pattern.search(command):
                if role in _BYPASS_ROLES:
                    return ValidationResult(
                        allowed=True,
                        reason=f"Admin bypass for: {command}",
                        bypass_2fa=True,
                    )
                return ValidationResult(
                    allowed=False,
                    reason=f"Command denied by policy: {command}",
                )

        # Allow-list
        for pattern in self._allow:
            if pattern.search(command):
                return ValidationResult(allowed=True)

        # Unknown command
        return ValidationResult(
            allowed=False,
            reason=f"Unknown command: {command}",
        )


def _split_logical(command: str) -> list[str]:
    """Divide um buffer em comandos logicos por separadores VRP."""
    return [
        part.strip()
        for part in _CMD_SEPARATORS.split(command)
        if part.strip()
    ]
