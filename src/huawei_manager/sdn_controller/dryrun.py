"""Dry-Run Engine — diff generation, dry-run, apply, and rollback.

Compara config atual vs proposta usando difflib. Todo deploy passa
por dry-run antes de ser aplicado. Rollback automatico.
"""
from __future__ import annotations

import difflib
from collections.abc import Callable
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


@dataclass
class ApplyResult:
    """Resultado da aplicacao de config.

    Attributes:
        success: True se a operacao foi bem-sucedida.
        output: Output do comando.
        error: Mensagem de erro (None se success=True).
        rollback_command: Comando para rollback (None se nao houver).
    """

    success: bool
    output: str
    error: str | None = None
    rollback_command: str | None = None


class DryRunEngine:
    """Engine de dry-run para comandos de configuracao.

    Gera diff entre config atual e proposta, executa dry-run
    (simulacao sem envio), apply, e rollback.
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

    # ── Dry-run ──────────────────────────────────────────────────────────

    def dry_run(
        self,
        execute_fn: Callable[[str], str],
        current: str,
        proposed: str,
    ) -> DiffReport:
        """Simula a execucao sem enviar comandos ao dispositivo.

        Gera o diff e retorna o relatorio. A funcao *nao* e chamada
        — apenas simulamos o resultado.

        Args:
            execute_fn: Funcao de execucao (nao chamada em dry-run).
            current: Configuracao atual.
            proposed: Configuracao proposta.

        Returns:
            ``DiffReport`` com o resultado da simulacao.
        """
        return self.diff(current, proposed)

    # ── Apply ────────────────────────────────────────────────────────────

    def apply(
        self,
        execute_fn: Callable[[str], str],
        proposed: str,
        original: str | None = None,
    ) -> ApplyResult:
        """Aplica a configuracao proposta.

        Se ``original`` for fornecido, gera um comando de rollback
        para restaurar a config original em caso de falha.

        Args:
            execute_fn: Funcao que executa o comando no dispositivo.
            proposed: Configuracao proposta a ser aplicada.
            original: Configuracao original (para rollback).

        Returns:
            ``ApplyResult`` com o resultado da aplicacao.
        """
        try:
            output = execute_fn(proposed)
        except RuntimeError as e:
            return ApplyResult(
                success=False,
                output="",
                error=str(e),
            )

        rollback_cmd: str | None = None
        if original is not None:
            diff_report = self.diff(original, proposed)
            if diff_report.has_changes:
                rollback_cmd = original

        return ApplyResult(
            success=True,
            output=output,
            rollback_command=rollback_cmd,
        )

    # ── Rollback ─────────────────────────────────────────────────────────

    def rollback(
        self,
        execute_fn: Callable[[str], str],
        command: str,
    ) -> ApplyResult:
        """Executa rollback para restaurar config anterior.

        Args:
            execute_fn: Funcao que executa o comando no dispositivo.
            command: Comando/configuracao de rollback.

        Returns:
            ``ApplyResult`` com o resultado do rollback.
        """
        try:
            output = execute_fn(command)
        except RuntimeError as e:
            return ApplyResult(
                success=False,
                output="",
                error=str(e),
            )

        return ApplyResult(success=True, output=output)
