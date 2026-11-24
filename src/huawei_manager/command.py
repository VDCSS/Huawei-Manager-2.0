"""Command pattern — operações transacionais de configuração.

Contrato de toda mutação de estado do dispositivo (AGENTS.md):

1. **snapshot pré-mudança** — fail-closed: sem snapshot, nada é aplicado;
2. **execução** da mutação via callback injetado (send_config, etc.);
3. **auditoria** preservando o schema do ``AuditLogger`` (hash chain);
4. **rollback best-effort** disponível via ``ConfigCommand.rollback()``.

Limitação honesta: VRP não possui transação — linhas que passaram a
existir após a mutação não têm ``undo`` automático. O rollback restaura
o que é restaurável e reporta o restante como pendência (status
``partial``). NETCONF com commit confirmado seria o rollback real
(evolução futura — ver ``docs/padroes-de-projeto.md``).
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from huawei_manager.exceptions import SdnError, SnapshotError
from huawei_manager.sdn_controller.dryrun import DryRunEngine

if TYPE_CHECKING:
    from huawei_manager.audit_log import AuditLogger

log = logging.getLogger(__name__)

# Cabeçalhos do unified_diff gerado por DryRunEngine.diff()
# (fromfile="current", tofile="proposed") — nunca são linhas de config.
_DIFF_HEADERS = frozenset({"--- current", "+++ proposed"})


@dataclass
class CommandResult:
    """Resultado de ``execute()``/``rollback()`` de um ``DeviceCommand``.

    Attributes:
        ok: True quando a operação atingiu o objetivo.
        status: ``"ok" | "partial" | "error" | "blocked"`` — valores
            alinhados ao campo ``status`` do schema de auditoria.
        message: Mensagem pronta para exibição ao operador.
        duration_ms: Duração da operação em milissegundos.
        restored: Linhas re-aplicadas no rollback.
        pending: Linhas que exigem undo manual (parcialidade honesta).
    """

    ok: bool
    status: str
    message: str
    duration_ms: float = 0.0
    restored: int = 0
    pending: int = 0


class DeviceCommand(ABC):
    """Command abstrato com snapshot pré-mudança e rollback.

    Subclasses implementam ``_read_state()`` (leitura do estado atual) e
    ``_apply()`` (mutação); o template de execução é fixo: snapshot →
    aplicação, com falha fechada no snapshot.
    """

    def __init__(self, lines: Sequence[str], *,
                 dry_run: DryRunEngine | None = None) -> None:
        self._lines: list[str] = list(lines)
        self._dry_run = DryRunEngine() if dry_run is None else dry_run
        self._snapshot: str | None = None

    @property
    def snapshot(self) -> str | None:
        """Estado pré-mudança capturado (``None`` antes do ``execute()``)."""
        return self._snapshot

    @property
    def lines(self) -> tuple[str, ...]:
        """Linhas originais da mutação (tupla imutável)."""
        return tuple(self._lines)

    @abstractmethod
    def _read_state(self) -> str:
        """Lê o estado atual do dispositivo (running-config)."""

    @abstractmethod
    def _apply(self, lines: list[str]) -> tuple[bool, str]:
        """Aplica ``lines`` no dispositivo; retorna ``(ok, mensagem)``.

        Falhas de domínio são levantadas como ``SdnError`` (propagam
        sem conversão para ``SnapshotError``).
        """

    def capture_snapshot(self) -> str:
        """Lê e guarda o estado pré-mudança.

        Raises:
            SnapshotError: qualquer falha na leitura — fail-closed, a
                mutação não deve ser iniciada sem snapshot.
        """
        try:
            state = self._read_state()
        except SdnError as exc:
            raise SnapshotError(
                f"snapshot pré-mudança falhou: {exc}",
            ) from exc
        except Exception as exc:
            # justificativa: fail-closed — QUALQUER erro inesperado de
            # leitura aborta a mutação; converter em erro de domínio.
            log.exception("capture_snapshot falhou")
            raise SnapshotError(
                f"snapshot pré-mudança falhou: {exc}",
            ) from exc
        self._snapshot = state
        return state

    def execute(self) -> CommandResult:
        """Captura o snapshot (fail-closed) e aplica a mutação.

        Returns:
            ``CommandResult`` com ``status="ok"`` ou ``"error"`` conforme
            o ``(ok, mensagem)`` devolvido por ``_apply()``.

        Raises:
            SnapshotError: leitura do snapshot falhou — nada aplicado.
            SdnError: falha do dispositivo na aplicação (propagada).
        """
        t0 = time.monotonic()
        self.capture_snapshot()
        ok, message = self._apply(self._lines)
        return CommandResult(
            ok=ok,
            status="ok" if ok else "error",
            message=message,
            duration_ms=(time.monotonic() - t0) * 1000.0,
        )


class ConfigCommand(DeviceCommand):
    """Mutação de configuração com rollback via diff de running-config."""

    def __init__(
        self,
        lines: Sequence[str],
        *,
        read_state: Callable[[], str],
        apply_fn: Callable[[list[str]], tuple[bool, str]],
        dry_run: DryRunEngine | None = None,
    ) -> None:
        super().__init__(lines, dry_run=dry_run)
        self._read_state_fn = read_state
        self._apply_fn = apply_fn

    def _read_state(self) -> str:
        return self._read_state_fn()

    def _apply(self, lines: list[str]) -> tuple[bool, str]:
        return self._apply_fn(lines)

    def rollback(self) -> CommandResult:
        """Restaura o estado do snapshot (best-effort e honesto).

        Fluxo: relê o estado atual → diff(atual → snapshot) → re-aplica
        as linhas que faltam → reverifica o resultado. Linhas que só
        existem no estado pós-mudança não têm ``undo`` automático em
        VRP: sobram como pendência e o resultado sai com status
        ``partial`` — nunca se afirma restauração completa sem prova.

        Returns:
            ``CommandResult`` com ``status`` ``"ok"``, ``"partial"``,
            ``"error"`` (recusa do dispositivo) ou ``"blocked"`` (sem
            snapshot registrado).

        Raises:
            SdnError: falha de leitura/aplicação — tratada pelo chamador.
        """
        if self._snapshot is None:
            return CommandResult(
                ok=False,
                status="blocked",
                message="Sem snapshot registrado — nada a desfazer.",
            )
        t0 = time.monotonic()
        current = self._read_state()
        diff = self._dry_run.diff(current, self._snapshot)
        if not diff.has_changes:
            return CommandResult(
                ok=True,
                status="ok",
                message="Config já está no estado original do snapshot.",
                duration_ms=(time.monotonic() - t0) * 1000.0,
            )
        # added = linhas do snapshot ausentes no estado atual → restauráveis.
        restore: list[str] = []
        for line in diff.added:
            if line.rstrip("\n") in _DIFF_HEADERS:
                continue
            text = line[1:].rstrip("\n")  # remove o prefixo '+'
            if text.strip():
                restore.append(text)
        error: str | None = None
        restored = 0
        if restore:
            ok, message = self._apply(restore)
            if ok:
                restored = len(restore)
            else:
                error = message
        # Re-verificação honesta: o que restou DEPOIS da tentativa.
        verify = self._read_state()
        vdiff = self._dry_run.diff(verify, self._snapshot)
        pending = sum(
            1
            for line in (*vdiff.added, *vdiff.removed)
            if line.rstrip("\n") not in _DIFF_HEADERS
        )
        duration_ms = (time.monotonic() - t0) * 1000.0
        if error is not None:
            return CommandResult(
                ok=False,
                status="error",
                message=f"Rollback recusado pelo dispositivo: {error} "
                        f"({pending} diferença(s) permanecem).",
                duration_ms=duration_ms,
                restored=restored,
                pending=pending,
            )
        if pending == 0:
            return CommandResult(
                ok=True,
                status="ok",
                message=f"Rollback concluído — {restored} linha(s) restaurada(s).",
                duration_ms=duration_ms,
                restored=restored,
            )
        return CommandResult(
            ok=False,
            status="partial",
            message=f"Restauração parcial — {restored} linha(s) restaurada(s); "
                    f"{pending} linha(s) exigem undo manual (VRP sem transação).",
            duration_ms=duration_ms,
            restored=restored,
            pending=pending,
        )


def audit_config_op(
    audit: AuditLogger | None,
    *,
    op: str,
    user: str,
    host: str,
    status: str,
    duration_ms: float = 0.0,
    session_id: str | None = None,
    # Any justificado: espelha **extra: Any da assinatura do AuditLogger —
    # tipar mais estreito faz o spread colidir com os parâmetros nomeados.
    **extra: Any,
) -> None:
    """Registra uma operação de configuração preservando o schema.

    Campos canônicos do ``AuditLogger`` (``op``/``user``/``host``/
    ``status``/``duration_ms``/``session_id``/``category``) ficam
    sempre nessa assinatura — quebrar a hash chain é regressão crítica.
    Detalhes adicionais entram em ``extra``. A auditoria **nunca**
    derruba a operação (fail-closed).
    """
    if audit is None:
        return
    try:
        audit.log_operation(
            op,
            user=user,
            host=host,
            status=status,
            duration_ms=duration_ms,
            session_id=session_id,
            category="config",
            **extra,
        )
    except Exception:  # justificativa: auditoria nunca derruba a operação
        log.exception("audit_config_op falhou (op=%s, status=%s)", op, status)
