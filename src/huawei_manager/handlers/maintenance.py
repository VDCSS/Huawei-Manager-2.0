"""Maintenance mixin — execução de diagnóstico, agentes e setup.

Extraído de ``pages/manutencao.py`` (desvio de MVP apontado em
``docs/padroes-de-projeto.md``): a View constrói widgets e reage a
filtros; o handler executa processos e IO. Ambos compartilham o mesmo
``_manut_output`` via ``_write``/``_dispatch``.

Segurança: toda entrada exige papel ``tecnico``; processos rodam com
timeout, cancelamento cooperativo e saída streamada em lotes — falhas
viram texto no painel, nunca exceção na thread de UI.
"""
from __future__ import annotations

import logging
import subprocess
import threading

from huawei_manager._protocols import AppCoreProtocol

log = logging.getLogger(__name__)

# Timeouts por tipo de processo (segundos).
_DEV_TIMEOUT_S = 180
_SETUP_TIMEOUT_S = 120
# Saída é publicada na UI em lotes para não gerar um sinal por linha.
_FLUSH_EVERY = 5


class MaintenanceMixin:
    """Execução da página Manutenção (DEV, Agentes e Setup)."""

    def _run_dev_cmd(self: AppCoreProtocol, target: str) -> None:
        """Executa alvo de desenvolvimento (``make lint|test|typecheck|ci``)."""
        if not self._require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        self._cancel_and_clear()

        commands = {
            "lint": ["make", "lint"],
            "test": ["make", "test"],
            "typecheck": ["make", "typecheck"],
            "all": ["make", "ci"],
        }
        cmd_list = commands.get(target, ["true"])
        self._loading(self._manut_output, f"Executando: {' '.join(cmd_list)}...")
        self._spawn_stream(
            cmd_list,
            timeout_s=_DEV_TIMEOUT_S,
            done_label="Concluido",
            cwd=str(PROJECT_ROOT),
        )

    def _run_agents(self: AppCoreProtocol) -> None:
        """Varre o projeto com os agentes e publica os resultados na View."""
        if not self._require_access("tecnico"):
            return

        from huawei_manager.agents.runner import run_all

        self._loading(self._manut_output, "Varrendo projeto com agentes...")

        def target_fn() -> None:
            try:
                results = run_all()
                self._watcher_results = results
                self._dispatch(lambda: self._display_watcher_results(results))
            except Exception as e:
                self._write(self._manut_output, f"Erro nos agentes: {e}")

        self._spawn_cpu(target_fn)

    def _run_setup(self: AppCoreProtocol, mode: str) -> None:
        """Executa ``setup/install.sh install <mode>`` com timeout e cancelamento."""
        if not self._require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        self._cancel_and_clear()

        setup_script = str(PROJECT_ROOT / "setup" / "install.sh")
        self._loading(self._manut_output, f"install.sh install {mode}...")
        self._spawn_stream(
            [setup_script, "install", mode],
            timeout_s=_SETUP_TIMEOUT_S,
            done_label=f"install.sh install {mode} concluido",
            cwd=str(PROJECT_ROOT),
        )

    def _cancel_and_clear(self: AppCoreProtocol) -> None:
        """Cancela o processo em curso (se houver) ou limpa o painel."""
        if self._cancel_event is not None:
            self._cancel_event.set()
            self._cancel_event = None

            def _note_cancel() -> None:
                out = self._manut_output
                if out is not None:
                    out.append("\n\u26a1  Processo cancelado")

            self._dispatch(_note_cancel)
        else:
            self._write(self._manut_output, "")

    def _spawn_stream(
        self: AppCoreProtocol,
        cmd_list: list[str],
        *,
        timeout_s: int,
        done_label: str,
        cwd: str,
    ) -> None:
        """Roda um processo com streaming, cancelamento e timeout.

        O buffer é acumulado na thread de IO e publicado na UI em lotes
        (``_dispatch``) — a thread de UI nunca toca ``subprocess``.
        """
        cancel = threading.Event()
        self._cancel_event = cancel

        def target_fn() -> None:
            buf: list[str] = []
            lock = threading.Lock()

            def _append(text: str) -> None:
                out = self._manut_output
                if out is not None:
                    out.append(text)

            def _set_output(text: str) -> None:
                out = self._manut_output
                if out is not None:
                    out.clear()
                    out.setPlainText(text)

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._dispatch(lambda t=text: _set_output(t))

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
                    self._dispatch(lambda: _append(
                        "\n\u26a1  Processo cancelado"))
                    return
                proc.wait(timeout=timeout_s)
                _flush()
                rc = proc.returncode
                prefix = "\u2705" if rc == 0 else f"\u274c (exit {rc})"
                self._dispatch(lambda p=prefix: _append(
                    f"\n{p}  {done_label}"))
            except subprocess.TimeoutExpired:
                self._dispatch(lambda: _append(
                    f"\n\u23f0  Timeout ({timeout_s}s)"))
            except Exception as e:
                self._dispatch(lambda err=str(e): _append(
                    f"\n\u274c  Erro: {err}"))
            finally:
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                self._dispatch(lambda: setattr(self, "_cancel_event", None))

        self._spawn_io(target_fn)
