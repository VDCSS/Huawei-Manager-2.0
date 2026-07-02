"""Command Validator — Allow-list and deny-list para comandos CLI.

Valida comandos contra listas de permitidos/negados antes da execucao.
Admin/Tecnico podem bypassar 2FA para comandos negados.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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

# Roles que podem bypassar 2FA para comandos negados
_BYPASS_ROLES: set[str] = {"admin", "tecnico"}


@dataclass
class ValidationResult:
    """Resultado da validacao de um comando.

    Attributes:
        allowed: True se o comando pode ser executado.
        reason: Mensagem explicativa (None se allowed=True sem bypass).
        bypass_2fa: True se o comando foi liberado por bypass 2FA.
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
        """Valida um comando contra allow-list e deny-list.

        Regras:
        1. Comando vazio → negado.
        2. Comando em allow-list → permitido.
        3. Comando em deny-list + role com bypass → permitido (bypass).
        4. Comando em deny-list + role sem bypass → negado.
        5. Comando desconhecido (nem allow nem deny) → negado.

        Args:
            command: Comando CLI a ser validado.
            role: Papel do usuario (user, tecnico, admin).

        Returns:
            ``ValidationResult`` com o resultado da validacao.
        """
        if not command.strip():
            return ValidationResult(allowed=False, reason="Empty command")

        # Check allow-list
        for pattern in self._allow:
            if pattern.search(command):
                return ValidationResult(allowed=True)

        # Check deny-list
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

        # Unknown command
        return ValidationResult(
            allowed=False,
            reason=f"Unknown command: {command}",
        )

    # ── Validate + Audit ────────────────────────────────────────────────

    def validate_and_audit(
        self,
        command: str,
        role: str = "user",
        audit_logger: Any = None,
        user: str = "unknown",
        host: str = "unknown",
    ) -> ValidationResult:
        """Valida e audita o resultado.

        Comandos negados e bypass 2FA sao registrados no audit log.

        Args:
            command: Comando CLI.
            role: Papel do usuario.
            audit_logger: Opcional — ``AuditLogger`` para registrar.
            user: Nome do usuario (para audit log).
            host: Host alvo (para audit log).

        Returns:
            ``ValidationResult``.
        """
        result = self.validate(command, role)

        if audit_logger is not None and not result.allowed:
            audit_logger.log_operation(
                "command_denied", user, host,
                status="blocked",
                details=result.reason or command,
            )
        elif audit_logger is not None and result.bypass_2fa:
            audit_logger.log_operation(
                "command_bypass", user, host,
                status="allowed",
                details=result.reason or command,
            )

        return result
