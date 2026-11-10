"""Execução da aba Manutenção — diagnóstico, agentes e setup.

Classe com injeção de dependências (Fase 1 do plano TabModule): recebe o
:class:`~huawei_manager.tabs._contract.TabContext` (serviços centrais),
o estado privado da aba e o callback que exibe resultados na View. Nada de
``self`` do App — o módulo é fechado.

Segurança: toda entrada exige papel ``tecnico`` (``ctx.require_access``);
processos rodam com timeout, cancelamento cooperativo e saída streamada em
lotes — falhas viram texto no painel, nunca exceção na thread de UI.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.agents import AgentResult
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.manutencao.state import ManutencaoState

log = logging.getLogger(__name__)

# Timeouts por tipo de processo (segundos).
_DEV_TIMEOUT_S = 180
_SETUP_TIMEOUT_S = 120
# Saída é publicada na UI em lotes para não gerar um sinal por linha.
_FLUSH_EVERY = 5

__all__ = ["MaintenanceHandlers"]


class MaintenanceHandlers:
    """Execução da aba Manutenção (DEV, Agentes e Setup)."""

    def __init__(
        self,
        ctx: TabContext,
        state: ManutencaoState,
        display: Callable[[Sequence[AgentResult]], None],
    ) -> None:
        self._ctx = ctx
        self._state = state
        self._display = display

    # ── Ações ────────────────────────────────────────────────────────

    def run_dev_cmd(self, target: str) -> None:
        """Executa alvo de desenvolvimento (``make lint|test|typecheck|ci``)."""
        if not self._ctx.require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        self.cancel_and_clear()

        commands = {
            "lint": ["make", "lint"],
            "test": ["make", "test"],
            "typecheck": ["make", "typecheck"],
            "all": ["make", "ci"],
        }
        cmd_list = commands.get(target, ["true"])
        _ui.loading(self._state.output,
                    f"Executando: {' '.join(cmd_list)}...", self._ctx.dispatch)
        self.spawn_stream(
            cmd_list,
            timeout_s=_DEV_TIMEOUT_S,
            done_label="Concluido",
            cwd=str(PROJECT_ROOT),
        )

    def run_agents(self) -> None:
        """Varre o projeto com os agentes e publica os resultados na View."""
        if not self._ctx.require_access("tecnico"):
            return

        from huawei_manager.agents.runner import run_all

        _ui.loading(self._state.output, "Varrendo projeto com agentes...",
                    self._ctx.dispatch)

        def target_fn() -> None:
            try:
                results = run_all()
                self._ctx.set_watcher_results(results)
                self._ctx.dispatch(lambda: self._display(results))
            except Exception as e:
                _ui.write(self._state.output, f"Erro nos agentes: {e}",
                          self._ctx.dispatch)

        self._ctx.spawn_cpu(target_fn)

    def run_setup(self, mode: str) -> None:
        """Executa ``setup/install.sh install <mode>`` com timeout e cancelamento."""
        if not self._ctx.require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        self.cancel_and_clear()

        setup_script = str(PROJECT_ROOT / "setup" / "install.sh")
        _ui.loading(self._state.output, f"install.sh install {mode}...",
                    self._ctx.dispatch)
        self.spawn_stream(
            [setup_script, "install", mode],
            timeout_s=_SETUP_TIMEOUT_S,
            done_label=f"install.sh install {mode} concluido",
            cwd=str(PROJECT_ROOT),
        )

    def cancel_and_clear(self) -> None:
        """Cancela o processo em curso (se houver) ou limpa o painel."""
        if self._state.cancel_event is not None:
            self._state.cancel_event.set()
            self._state.cancel_event = None

            def _note_cancel() -> None:
                out = self._state.output
                if out is not None:
                    out.append("\n⚡  Processo cancelado")

            self._ctx.dispatch(_note_cancel)
        else:
            _ui.write(self._state.output, "", self._ctx.dispatch)

    # ── Streaming ────────────────────────────────────────────────────

    def spawn_stream(
        self,
        cmd_list: list[str],
        *,
        timeout_s: int,
        done_label: str,
        cwd: str,
    ) -> None:
        """Roda um processo com streaming, cancelamento e timeout.

        O buffer é acumulado na thread de IO e publicado na UI em lotes
        (``ctx.dispatch``) — a thread de UI nunca toca ``subprocess``.
        """
        cancel = threading.Event()
        self._state.cancel_event = cancel

        def target_fn() -> None:
            buf: list[str] = []
            lock = threading.Lock()

            def _append(text: str) -> None:
                out = self._state.output
                if out is not None:
                    out.append(text)

            def _set_output(text: str) -> None:
                out = self._state.output
                if out is not None:
                    out.clear()
                    out.setPlainText(text)

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._ctx.dispatch(lambda t=text: _set_output(t))

            proc: subprocess.Popen[str] | None = None
            try:
                proc = subprocess.Popen(
                    cmd_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=cwd,
                )
                if proc.stdout is None:
                    raise RuntimeError("subprocess stdout is not available")
                for line in proc.stdout:
                    if cancel.is_set() or (proc.poll() is not None and not line):
                        break
                    buf.append(line.rstrip("\n"))
                    if len(buf) % _FLUSH_EVERY == 0:
                        _flush()
                if cancel.is_set():
                    proc.kill()
                    proc.wait(timeout=5)
                    self._ctx.dispatch(lambda: _append(
                        "\n⚡  Processo cancelado"))
                    return
                proc.wait(timeout=timeout_s)
                _flush()
                rc = proc.returncode
                prefix = "✅" if rc == 0 else f"❌ (exit {rc})"
                self._ctx.dispatch(lambda p=prefix: _append(
                    f"\n{p}  {done_label}"))
            except subprocess.TimeoutExpired:
                self._ctx.dispatch(lambda: _append(
                    f"\n⏰  Timeout ({timeout_s}s)"))
            except Exception as e:
                self._ctx.dispatch(lambda err=str(e): _append(
                    f"\n❌  Erro: {err}"))
            finally:
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                self._ctx.dispatch(
                    lambda: setattr(self._state, "cancel_event", None))

        self._ctx.spawn_io(target_fn)
