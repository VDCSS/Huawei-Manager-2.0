"""Dry-Run Engine — diff generation.

Compara config atual vs proposta usando difflib. Todo deploy passa
por dry-run antes de ser aplicado.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field


@dataclass
class DiffReport:
    """Relatorio de diff entre config atual e proposta.

    Attributes:
        has_changes: True se houver diferencas.
        added: Linhas adicionadas (com prefixo +).
        removed: Linhas removidas (com prefixo -).
        context_lines: Linhas de contexto ao redor das mudancas.
        total_added: Numero de linhas adicionadas.
        total_removed: Numero de linhas removidas.
    """

    has_changes: bool = False
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    context_lines: list[str] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return len(self.added)

    @property
    def total_removed(self) -> int:
        return len(self.removed)

    @property
    def summary(self) -> str:
        """Resumo legivel do diff."""
        if not self.has_changes:
            return "No changes."
        parts: list[str] = []
        if self.added:
            parts.append(f"+{self.total_added} added")
        if self.removed:
            parts.append(f"-{self.total_removed} removed")
        return ", ".join(parts)


class DryRunEngine:
    """Engine de dry-run para comandos de configuracao.

    Gera diff entre config atual e proposta (simulacao sem envio).
    """

    # ── Diff generation ──────────────────────────────────────────────────

    def diff(self, current: str, proposed: str) -> DiffReport:
        """Gera diff entre config atual e proposta.

        Args:
            current: Configuracao atual (string multilinha).
            proposed: Configuracao proposta (string multilinha).

        Returns:
            ``DiffReport`` com as diferencas encontradas.
        """
        if current == proposed:
            return DiffReport()

        curr_lines = current.splitlines(keepends=True)
        prop_lines = proposed.splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                curr_lines,
                prop_lines,
                fromfile="current",
                tofile="proposed",
                n=3,
            )
        )

        added: list[str] = []
        removed: list[str] = []
        context: list[str] = []

        for line in diff:
            if line.startswith("+"):
                added.append(line)
            elif line.startswith("-"):
                removed.append(line)
            elif line.startswith(" "):
                context.append(line)

        return DiffReport(
            has_changes=True,
            added=added,
            removed=removed,
            context_lines=context,
        )
