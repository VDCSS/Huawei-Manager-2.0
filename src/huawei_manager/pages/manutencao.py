"""PageBuilder mixin — Manutenção e Diagnóstico page."""

from __future__ import annotations

import subprocess
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text


class PageBuilderManutencaoMixin:
    """Mixin com métodos de construção da página de Manutenção."""

    def _build_manutencao_page(self: AppCoreProtocol) -> None:
        if self._access_level == "user":
            p = self._make_page("manutencao")
            self._page_title(p, "Acesso Restrito", C.NEON_AMBER)

            lbl = QLabel("\U0001f512  Esta pagina e exclusiva para usuarios Tecnico ou Admin.", p)
            lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 13))
            lbl.setAlignment(Qt.AlignCenter)
            self._page_layout(p).addSpacing(40)
            self._page_layout(p).addWidget(lbl)
            self._page_layout(p).addSpacing(10)

            btn = action_button(p, "\U0001f511  Autenticar como Tecnico / Admin",
                                self._show_auth_dialog, C.NEON_PURP)
            self._page_layout(p).addWidget(btn, alignment=Qt.AlignCenter)
            return

        p = self._make_page("manutencao")
        self._page_title(p, "Manutencao e Diagnostico", C.NEON_MAG,
                         "Testes + Agentes + Setup")

        top = QWidget(p)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(top)
        self._page_layout(p).addSpacing(12)

        # ── Group: DEV ──
        grp_dev = QGroupBox("  DEV  ", top)
        grp_dev.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_CYAN};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_dev_layout = QHBoxLayout(grp_dev)
        grp_dev_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_dev)

        btn_lint = action_button(grp_dev, "\u2699  Lint",
                                 lambda: self._run_dev_cmd("lint"), C.NEON_CYAN)
        grp_dev_layout.addWidget(btn_lint)
        grp_dev_layout.addSpacing(4)
        btn_test = action_button(grp_dev, "\U0001f9ea  Testes",
                                 lambda: self._run_dev_cmd("test"), C.NEON_MAG)
        grp_dev_layout.addWidget(btn_test)
        grp_dev_layout.addSpacing(4)
        btn_types = action_button(grp_dev, "\U0001f50d  Types",
                                  lambda: self._run_dev_cmd("typecheck"), C.NEON_PURP)
        grp_dev_layout.addWidget(btn_types)
        grp_dev_layout.addSpacing(4)
        btn_all = action_button(grp_dev, "\u25b6  Todos",
                                lambda: self._run_dev_cmd("all"), C.NEON_AMBER)
        grp_dev_layout.addWidget(btn_all)

        # ── Group: AGENTES ──
        grp_agents = QGroupBox("  AGENTES  ", top)
        grp_agents.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_PURP};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_agents_layout = QHBoxLayout(grp_agents)
        grp_agents_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_agents)

        btn_agents = action_button(grp_agents, "\U0001f50d  Agora",
                                   lambda: self._run_agents(), C.NEON_PURP)
        grp_agents_layout.addWidget(btn_agents)
        grp_agents_layout.addSpacing(4)
        self._watcher_btn = action_button(grp_agents, "\U0001f504  Auto: ON",
                                          self._toggle_watcher, C.NEON_CYAN)
        grp_agents_layout.addWidget(self._watcher_btn)

        # ── Group: SETUP ──
        grp_setup = QGroupBox("  SETUP  ", top)
        grp_setup.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_AMBER};
                font: bold 10px 'Inter'; border: 1px solid {C.BORDER_NRM};
                border-radius: 4px; margin-top: 8px; padding: 12px 4px 4px 4px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }}
        """)
        grp_setup_layout = QHBoxLayout(grp_setup)
        grp_setup_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(grp_setup)

        btn_check = action_button(grp_setup, "\U0001f4cb  Check",
                                  lambda: self._run_setup("check"), C.NEON_AMBER)
        grp_setup_layout.addWidget(btn_check)
        grp_setup_layout.addSpacing(4)
        btn_install = action_button(grp_setup, "\u2699  Install",
                                    lambda: self._run_setup("install"), C.NEON_CYAN)
        grp_setup_layout.addWidget(btn_install)
        grp_setup_layout.addSpacing(4)
        btn_reset = action_button(grp_setup, "\U0001f504  Reset",
                                  lambda: self._run_setup("reset"), C.NEON_MAG)
        grp_setup_layout.addWidget(btn_reset)

        # Summary
        summary_frame = QFrame(p)
        summary_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(summary_frame)
        self._page_layout(p).addSpacing(10)

        self._manut_summary = QTextEdit(summary_frame)
        self._manut_summary.setReadOnly(True)
        self._manut_summary.setMaximumHeight(100)
        self._manut_summary.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG_INPUT}; color: {C.FG_CODE};
                border: none; font: 11px 'Inter'; padding: 8px 10px;
            }}
        """)
        summary_layout.addWidget(self._manut_summary)

        # Filter bar
        filter_frame = QFrame(p)
        filter_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 2, 8, 2)
        self._page_layout(p).addWidget(filter_frame)
        self._page_layout(p).addSpacing(4)

        filt_lbl = QLabel("  Filtro:", filter_frame)
        filt_lbl.setStyleSheet(self._css_label(C.FG_DIM, C.BG_CARD, 10, True))
        filter_layout.addWidget(filt_lbl)
        filter_layout.addSpacing(2)

        self._manut_filter = "all"
        filter_vals = [
            ("all",    "Todas",    C.FG_MAIN),
            ("error",  "Erros",    C.NEON_AMBER),
            ("warning","Avisos",   C.NEON_MAG),
            ("info",   "Info",     C.NEON_CYAN),
        ]
        self._manut_rb_group: list[QRadioButton] = []
        for fval, flbl, fcol in filter_vals:
            rb = QRadioButton(flbl, filter_frame)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {fcol}; background: {C.BG_CARD};
                    font: 10px 'Inter'; spacing: 2px;
                }}
                QRadioButton::indicator {{ width: 12px; height: 12px; }}
            """)
            if fval == "all":
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=fval: self._on_manut_filter_toggled(checked, v))
            filter_layout.addWidget(rb)
            filter_layout.addSpacing(4)
            self._manut_rb_group.append(rb)
        filter_layout.addStretch()

        # Output
        output_frame = QFrame(p)
        output_frame.setStyleSheet(f"background: {C.BG_CARD}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(8, 4, 8, 4)
        self._page_layout(p).addWidget(output_frame, stretch=1)
        self._page_layout(p).addSpacing(4)

        self._manut_output = output_text(output_frame)
        output_layout.addWidget(self._manut_output, stretch=1)

        # Bottom bar
        bottom = QWidget(p)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout(p).addWidget(bottom)

        btn_limpar = action_button(bottom, "\u2716  Limpar",
                                   lambda: self._cancel_and_clear(), C.NEON_PURP)
        bottom_layout.addWidget(btn_limpar)
        bottom_layout.addStretch()

        if self._watcher_results:
            self._display_watcher_results(self._watcher_results)
        else:
            self._loading(self._manut_output, "Pronto. Clique em 'Agora' para varrer o projeto.")
            if self._watcher.is_active:
                self._loading(self._manut_output, "Watcher ativo — resultados em ate 60s...")

    def _on_manut_filter_toggled(self, checked: bool, value: str) -> None:
        if checked:
            self._manut_filter = value
            self._apply_manut_filter()

    def _run_dev_cmd(self: AppCoreProtocol, target: str) -> None:
        if not self._require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        # Cancela processo anterior se houver
        self._cancel_and_clear()

        cmds = {
            "lint":      ["make", "lint"],
            "test":      ["make", "test"],
            "typecheck": ["make", "typecheck"],
            "all":       ["make", "ci"],
        }
        cmd_list = cmds.get(target, ["true"])
        self._loading(self._manut_output, f"Executando: {' '.join(cmd_list)}...")

        cancel = threading.Event()
        self._cancel_event = cancel

        def target_fn():
            buf: list[str] = []
            lock = threading.Lock()

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._dispatch(lambda t=text: (
                            self._manut_output.clear(),
                            self._manut_output.setPlainText(t),
                        ))

            proc: subprocess.Popen | None = None
            try:
                proc = subprocess.Popen(
                    cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(PROJECT_ROOT),
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    if cancel.is_set() or (proc.poll() is not None and not line):
                        break
                    buf.append(line.rstrip("\n"))
                    if len(buf) % 5 == 0:
                        _flush()
                if cancel.is_set():
                    proc.kill()
                    proc.wait(timeout=5)
                    self._dispatch(lambda: self._manut_output.append(
                        "\n\u26a1  Processo cancelado"))
                    return
                proc.wait(timeout=180)
                _flush()
                rc = proc.returncode
                prefix = "\u2705" if rc == 0 else f"\u274c (exit {rc})"
                self._dispatch(lambda p=prefix: self._manut_output.append(
                    f"\n{p}  Concluido"))
            except subprocess.TimeoutExpired:
                self._dispatch(lambda: self._manut_output.append(
                    "\n\u23f0  Timeout (180s)"))
            except Exception as e:
                self._dispatch(lambda err=str(e): self._manut_output.append(
                    f"\n\u274c  Erro: {err}"))
            finally:
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                self._dispatch(lambda: setattr(self, '_cancel_event', None))

        self._spawn_io(target_fn)

    def _run_agents(self: AppCoreProtocol) -> None:
        if not self._require_access("tecnico"):
            return
        from huawei_manager.agents.runner import run_all

        self._loading(self._manut_output, "Varrendo projeto com agentes...")

        def target_fn():
            try:
                results = run_all()
                self._watcher_results = results
                self._dispatch(lambda: self._display_watcher_results(results))
            except Exception as e:
                self._write(self._manut_output, f"Erro nos agentes: {e}")

        self._spawn_cpu(target_fn)

    def _toggle_watcher(self: AppCoreProtocol) -> None:
        if self._watcher.is_active:
            self._watcher.stop()
            self._watcher_btn.setText("\U0001f504  Auto: OFF")
            self._write(self._manut_output, "Watcher desligado.")
        else:
            self._watcher.start()
            self._watcher_btn.setText("\U0001f504  Auto: ON")
            self._write(self._manut_output, "Watcher ligado — varredura a cada 60s.")

    def _apply_manut_filter(self) -> None:
        if self._last_manut_results:
            self._display_watcher_results(self._last_manut_results)

    def _display_watcher_results(self: AppCoreProtocol, results) -> None:
        self._last_manut_results = results

        counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        lines = []
        for r in results:
            icon = {"ok": "\u2705", "warning": "\u26a0", "error": "\u274c",
                    "info": "\U0001f4a1"}.get(r.status, "\u2753")
            lines.append(f"{icon}  {r.name:<12}  {r.summary}")
        total = sum(counts.values())
        lines.insert(0, f"  Total: {total} scans | "
                        f"\u274c{counts.get('error',0)}  "
                        f"\u26a0{counts.get('warning',0)}  "
                        f"\U0001f4a1{counts.get('info',0)}  "
                        f"\u2705{counts.get('ok',0)}")
        lines.insert(1, "")

        self._manut_summary.setReadOnly(False)
        self._manut_summary.setPlainText("\n".join(lines))
        self._manut_summary.setReadOnly(True)

        filter_val = self._manut_filter
        items = []
        for r in results:
            for it in r.items:
                if filter_val != "all" and it.severity != filter_val:
                    continue
                icon = {"warning": "\u26a0", "error": "\u274c",
                        "info": "\U0001f4a1"}.get(it.severity, "\u2022")
                items.append(f"{icon}  {r.name}: {it.file}\n"
                             f"   \U0001f4cb  {it.message}\n"
                             f"   \U0001f4a1  {it.suggestion}")
        if items:
            label = {"all": "Todos", "error": "Erros", "warning": "Avisos",
                     "info": "Info"}.get(filter_val, filter_val)
            header = f"\u2500 Filtro: {label} ({len(items)} itens) \u2500\n"
            self._write(self._manut_output, header + "\n".join(items))
        else:
            self._write(self._manut_output, "\u2705  Nenhum problema encontrado para o filtro atual.")

    def _cancel_and_clear(self: AppCoreProtocol) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self._cancel_event = None
            self._dispatch(lambda: self._manut_output.append("\n\u26a1  Processo cancelado"))
        else:
            self._write(self._manut_output, "")

    def _run_setup(self: AppCoreProtocol, mode: str) -> None:
        if not self._require_access("tecnico"):
            return

        from huawei_manager._config import PROJECT_ROOT

        self._cancel_and_clear()

        setup_script = str(PROJECT_ROOT / "setup" / "setup.sh")
        self._loading(self._manut_output, f"setup.sh {mode}...")

        cancel = threading.Event()
        self._cancel_event = cancel

        def target_fn():
            buf: list[str] = []
            lock = threading.Lock()

            def _flush() -> None:
                with lock:
                    text = "\n".join(buf)
                    if text:
                        self._dispatch(lambda t=text: (
                            self._manut_output.clear(),
                            self._manut_output.setPlainText(t),
                        ))

            proc: subprocess.Popen | None = None
            try:
                proc = subprocess.Popen(
                    [setup_script, mode], stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True,
                    cwd=str(PROJECT_ROOT),
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    if cancel.is_set() or (proc.poll() is not None and not line):
                        break
                    buf.append(line.rstrip("\n"))
                    if len(buf) % 5 == 0:
                        _flush()
                if cancel.is_set():
                    proc.kill()
                    proc.wait(timeout=5)
                    self._dispatch(lambda: self._manut_output.append(
                        "\n\u26a1  Processo cancelado"))
                    return
                proc.wait(timeout=120)
                _flush()
                rc = proc.returncode
                prefix = "\u2705" if rc == 0 else f"\u274c (exit {rc})"
                self._dispatch(lambda p=prefix: self._manut_output.append(
                    f"\n{p}  setup.sh {mode} concluido"))
            except subprocess.TimeoutExpired:
                self._dispatch(lambda: self._manut_output.append(
                    "\n\u23f0  Timeout (120s)"))
            except Exception as e:
                self._dispatch(lambda err=str(e): self._manut_output.append(
                    f"\n\u274c  Erro: {err}"))
            finally:
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                self._dispatch(lambda: setattr(self, '_cancel_event', None))

        self._spawn_io(target_fn)

