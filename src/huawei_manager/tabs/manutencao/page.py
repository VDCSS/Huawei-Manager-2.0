"""Aba Manutenção — módulo TabModule (piloto da Fase 1).

Substitui ``PageBuilderManutencaoMixin``: a View constrói widgets e reage a
filtros; a execução fica em :class:`MaintenanceHandlers` (injetado); o
estado vive em :class:`ManutencaoState`. Tudo que a aba consome vem do
:class:`~huawei_manager.tabs._contract.TabContext` — nunca do App.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.manutencao.handlers import MaintenanceHandlers
from huawei_manager.tabs.manutencao.state import ManutencaoState
from huawei_manager.widgets.icons import icon
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from huawei_manager.agents import AgentResult
    from huawei_manager.tabs._contract import TabContext

log = logging.getLogger("huawei.manutencao")

__all__ = ["ManutencaoTab"]


class ManutencaoTab:
    """Ciclo de vida da aba: ``build(ctx)`` → QWidget; ``dispose()`` limpa widgets."""

    def __init__(self) -> None:
        self.state = ManutencaoState()
        self._ctx: TabContext | None = None
        self._handlers: MaintenanceHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────

    def build(self, ctx: TabContext) -> QWidget:
        self._ctx = ctx
        st = self.state
        self._handlers = MaintenanceHandlers(ctx, st, display=self._display_results)

        if ctx.role() == "user":
            p = _ui.page_frame("manutencao")
            _ui.page_title(p, "Acesso Restrito", C.NEON_AMBER)

            lbl = QLabel("Esta página é exclusiva para usuários Técnico ou Admin.", p)
            lbl.setStyleSheet(_ui.css_label(C.FG_DIM, "", 13))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay = _ui.page_layout(p)
            lay.addSpacing(40)
            lay.addWidget(lbl)
            lay.addSpacing(10)

            btn = action_button(p, "Autenticar como Tecnico / Admin",
                                ctx.show_auth_dialog, C.NEON_PURP,
                                variant="outline")
            btn.setIcon(icon("i-key", C.NEON_PURP, 16))
            btn.setIconSize(QSize(16, 16))
            lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
            return p

        p = _ui.page_frame("manutencao")
        lay = _ui.page_layout(p)
        _ui.page_title(p, "Manutencao e Diagnostico", C.NEON_MAG,
                       "Testes + Agentes + Setup")

        top = QWidget(p)
        top_layout = QGridLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(top)
        lay.addSpacing(12)

        # ── Group: DEV ──
        grp_dev = QGroupBox("  DEV  ", top)
        grp_dev.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_CYAN};
                font: 600 11px {C.FONT_UI_FAMILY}; border: 1px solid {C.BORDER_SOFT};
                border-radius: 10px; margin-top: 14px; padding: 20px 14px 14px 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 12px; padding: 0 6px;
            }}
        """)
        grp_dev_layout = QHBoxLayout(grp_dev)
        grp_dev_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.addWidget(grp_dev, 0, 0)

        btn_lint = action_button(grp_dev, "Lint",
                                 lambda: self._h().run_dev_cmd("lint"), C.NEON_CYAN)
        btn_lint.setIcon(icon("i-settings", C.NEON_CYAN, 16))
        btn_lint.setIconSize(QSize(16, 16))
        grp_dev_layout.addWidget(btn_lint)
        grp_dev_layout.addSpacing(4)
        btn_test = action_button(grp_dev, "Testes",
                                 lambda: self._h().run_dev_cmd("test"), C.NEON_MAG)
        btn_test.setIcon(icon("i-activity", C.NEON_MAG, 16))
        btn_test.setIconSize(QSize(16, 16))
        grp_dev_layout.addWidget(btn_test)
        grp_dev_layout.addSpacing(4)
        btn_types = action_button(grp_dev, "Types",
                                  lambda: self._h().run_dev_cmd("typecheck"), C.NEON_PURP)
        btn_types.setIcon(icon("i-search", C.NEON_PURP, 16))
        btn_types.setIconSize(QSize(16, 16))
        grp_dev_layout.addWidget(btn_types)
        grp_dev_layout.addSpacing(4)
        btn_all = action_button(grp_dev, "Todos",
                                lambda: self._h().run_dev_cmd("all"), C.NEON_AMBER)
        btn_all.setIcon(icon("i-play", C.NEON_AMBER, 16))
        btn_all.setIconSize(QSize(16, 16))
        grp_dev_layout.addWidget(btn_all)

        # ── Group: AGENTES ──
        grp_agents = QGroupBox("  AGENTES  ", top)
        grp_agents.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_PURP};
                font: 600 11px {C.FONT_UI_FAMILY}; border: 1px solid {C.BORDER_SOFT};
                border-radius: 10px; margin-top: 14px; padding: 20px 14px 14px 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 12px; padding: 0 6px;
            }}
        """)
        grp_agents_layout = QHBoxLayout(grp_agents)
        grp_agents_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.addWidget(grp_agents, 0, 1)

        btn_agents = action_button(grp_agents, "Agora",
                                   lambda: self._h().run_agents(), C.NEON_PURP)
        btn_agents.setIcon(icon("i-search", C.NEON_PURP, 16))
        btn_agents.setIconSize(QSize(16, 16))
        grp_agents_layout.addWidget(btn_agents)
        grp_agents_layout.addSpacing(4)
        watcher_btn = action_button(
            grp_agents,
            f"Auto: {'ON' if ctx.watcher.is_active else 'OFF'}",
            self._toggle_watcher, C.NEON_CYAN)
        watcher_btn.setIcon(icon("i-refresh", C.NEON_CYAN, 16))
        watcher_btn.setIconSize(QSize(16, 16))
        st.watcher_btn = watcher_btn
        grp_agents_layout.addWidget(watcher_btn)

        # ── Group: MODO ──
        grp_mode = QGroupBox("  MODO  ", top)
        grp_mode.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_AMBER};
                font: 600 11px {C.FONT_UI_FAMILY}; border: 1px solid {C.BORDER_SOFT};
                border-radius: 10px; margin-top: 14px; padding: 20px 14px 14px 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 12px; padding: 0 6px;
            }}
        """)
        grp_mode_layout = QHBoxLayout(grp_mode)
        grp_mode_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.addWidget(grp_mode, 1, 0)

        mock = ctx.is_mock()
        mode_text = "Real" if not mock else "Mock"
        mode_color = C.NEON_CYAN if not mock else C.NEON_AMBER
        mode_btn = action_button(grp_mode, mode_text,
                                 self._toggle_probe_mode, mode_color)
        mode_btn.setIcon(icon("i-radio", mode_color, 16))
        mode_btn.setIconSize(QSize(16, 16))
        st.mode_btn = mode_btn
        grp_mode_layout.addWidget(mode_btn)

        # ── Group: SETUP ──
        grp_setup = QGroupBox("  SETUP  ", top)
        grp_setup.setStyleSheet(f"""
            QGroupBox {{
                background: {C.BG_CARD}; color: {C.NEON_AMBER};
                font: 600 11px {C.FONT_UI_FAMILY}; border: 1px solid {C.BORDER_SOFT};
                border-radius: 10px; margin-top: 14px; padding: 20px 14px 14px 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 12px; padding: 0 6px;
            }}
        """)
        grp_setup_layout = QHBoxLayout(grp_setup)
        grp_setup_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.addWidget(grp_setup, 1, 1)

        btn_check = action_button(grp_setup, "Check",
                                  lambda: self._h().run_setup("check"), C.NEON_AMBER)
        btn_check.setIcon(icon("i-file-text", C.NEON_AMBER, 16))
        btn_check.setIconSize(QSize(16, 16))
        grp_setup_layout.addWidget(btn_check)
        grp_setup_layout.addSpacing(4)
        btn_install = action_button(grp_setup, "Install",
                                    lambda: self._h().run_setup("install"), C.NEON_CYAN)
        btn_install.setIcon(icon("i-settings", C.NEON_CYAN, 16))
        btn_install.setIconSize(QSize(16, 16))
        grp_setup_layout.addWidget(btn_install)
        grp_setup_layout.addSpacing(4)
        btn_reset = action_button(grp_setup, "Reset",
                                  lambda: self._h().run_setup("reset"), C.NEON_MAG)
        btn_reset.setIcon(icon("i-refresh", C.NEON_MAG, 16))
        btn_reset.setIconSize(QSize(16, 16))
        grp_setup_layout.addWidget(btn_reset)

        # Summary
        summary_frame = QFrame(p)
        summary_frame.setObjectName("manutSummary")
        summary_frame.setStyleSheet(
            f"QFrame#manutSummary {{ background: {C.BG_CODE};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(14, 10, 14, 10)
        lay.addWidget(summary_frame)
        lay.addSpacing(10)

        summary = QTextEdit(summary_frame)
        summary.setReadOnly(True)
        summary.setMaximumHeight(110)
        summary.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; color: {C.FG_CODE};
                border: none; font: 11px {C.FONT_MONO_FAMILY}; padding: 0px;
                selection-background-color: {C.NEON_CYAN};
                selection-color: {C.BG_BASE};
            }}
        """)
        st.summary = summary
        summary_layout.addWidget(summary)

        # Filter bar
        filter_frame = QFrame(p)
        filter_frame.setObjectName("manutFilter")
        filter_frame.setStyleSheet(
            f"QFrame#manutFilter {{ background: {C.BG_SURFACE_2};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(20, 8, 20, 8)
        lay.addWidget(filter_frame)
        lay.addSpacing(8)

        filt_lbl = QLabel("Filtro", filter_frame)
        filt_lbl.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 11, True))
        filter_layout.addWidget(filt_lbl)
        filter_layout.addSpacing(4)

        st.active_filter = "all"
        st.rb_group = []
        filter_vals = [
            ("all",    "Todas",    C.FG_MAIN),
            ("error",  "Erros",    C.NEON_AMBER),
            ("warning","Avisos",   C.NEON_MAG),
            ("info",   "Info",     C.NEON_CYAN),
        ]
        for fval, flbl, fcol in filter_vals:
            rb = QRadioButton(flbl, filter_frame)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {fcol}; background: transparent;
                    font: {C.FONT_CAPTION}px {C.FONT_UI_FAMILY}; spacing: 5px;
                }}
                QRadioButton::indicator {{ width: 12px; height: 12px; }}
            """)
            if fval == "all":
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=fval: self._on_manut_filter_toggled(checked, v))
            filter_layout.addWidget(rb)
            filter_layout.addSpacing(6)
        filter_layout.addStretch()

        # Output
        output_frame = QFrame(p)
        output_frame.setObjectName("manutOutput")
        output_frame.setStyleSheet(
            f"QFrame#manutOutput {{ background: {C.BG_CARD};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(output_frame, stretch=1)
        lay.addSpacing(8)

        out = output_text(output_frame)
        st.output = out
        output_layout.addWidget(out, stretch=1)

        # Bottom bar
        bottom = QWidget(p)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bottom)

        btn_limpar = action_button(bottom, "Limpar",
                                   lambda: self._h().cancel_and_clear(), C.NEON_PURP,
                                   variant="ghost")
        btn_limpar.setIcon(icon("i-x", C.NEON_PURP, 16))
        btn_limpar.setIconSize(QSize(16, 16))
        bottom_layout.addWidget(btn_limpar)
        bottom_layout.addStretch()

        watcher_snapshot = ctx.watcher_results()
        if watcher_snapshot:
            self._display_results(watcher_snapshot)
        else:
            _ui.loading(out, "Pronto. Clique em 'Agora' para varrer o projeto.",
                        ctx.dispatch)
            if ctx.watcher.is_active:
                _ui.loading(out, "Watcher ativo — resultados em ate 60s...",
                            ctx.dispatch)
        return p

    def dispose(self) -> None:
        """Rebuild: zera refs de widgets (processos em curso toleram None)."""
        st = self.state
        st.output = None
        st.summary = None
        st.rb_group = []
        st.mode_btn = None
        st.watcher_btn = None
        # active_filter/last_results/cancel_event sobrevivem entre rebuilds
        # (cancel_event: processo streamado continua vivo — paridade com o
        # rebuild legado, que não cancelava nada).

    # ── Interações da View ───────────────────────────────────────────

    def _h(self) -> MaintenanceHandlers:
        handlers = self._handlers
        if handlers is None:
            raise RuntimeError("ManutencaoTab não foi construído (build ausente)")
        return handlers

    def _on_manut_filter_toggled(self, checked: bool, value: str) -> None:
        if checked:
            self.state.active_filter = value
            self._apply_manut_filter()

    def _toggle_watcher(self) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        if ctx.watcher.is_active:
            ctx.watcher.stop()
            if self.state.watcher_btn is not None:
                self.state.watcher_btn.setText("Auto: OFF")
            _ui.write(self.state.output, "Watcher desligado.", ctx.dispatch)
        else:
            ctx.watcher.start()
            if self.state.watcher_btn is not None:
                self.state.watcher_btn.setText("Auto: ON")
            _ui.write(self.state.output,
                      "Watcher ligado — varredura a cada 60s.", ctx.dispatch)

    def _toggle_probe_mode(self) -> None:
        ctx = self._ctx
        btn = self.state.mode_btn
        if ctx is None or btn is None:
            return
        mock = ctx.toggle_mock()
        mode = "Mock" if mock else "Real"
        color = C.NEON_AMBER if mock else C.NEON_CYAN
        btn.setText(mode)
        btn.configure(color=color)
        log_msg = f"Modo de probe alterado: {mode}"
        _ui.write(self.state.output, log_msg, ctx.dispatch)
        log.info("Probe mode changed to %s", mode)

    def _apply_manut_filter(self) -> None:
        if self.state.last_results:
            self._display_results(self.state.last_results)

    def _display_results(self, results: Sequence[AgentResult]) -> None:
        ctx = self._ctx
        if ctx is None:
            return
        st = self.state
        st.last_results = results

        counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1

        lines: list[str] = []
        for r in results:
            marker = {"ok": "[OK]", "warning": "[!]", "error": "[X]",
                      "info": "[i]"}.get(r.status, "[?]")
            lines.append(f"{marker:<5} {r.name:<12}  {r.summary}")
        total = sum(counts.values())
        lines.insert(0, f"  Total: {total} scans | "
                        f"ERR {counts.get('error',0)}  "
                        f"WARN {counts.get('warning',0)}  "
                        f"INFO {counts.get('info',0)}  "
                        f"OK {counts.get('ok',0)}")
        lines.insert(1, "")

        summary = st.summary
        if summary is not None:
            summary.setReadOnly(False)
            summary.setPlainText("\n".join(lines))
            summary.setReadOnly(True)

        filter_val = st.active_filter
        items: list[str] = []
        for r in results:
            for it in r.items:
                if filter_val != "all" and it.severity != filter_val:
                    continue
                marker = {"warning": "[!]", "error": "[X]",
                          "info": "[i]"}.get(it.severity, "[-]")
                items.append(f"{marker:<5} {r.name}: {it.file}\n"
                             f"   {it.message}\n"
                             f"   {it.suggestion}")
        if items:
            label = {"all": "Todos", "error": "Erros", "warning": "Avisos",
                     "info": "Info"}.get(filter_val, filter_val)
            header = f"─ Filtro: {label} ({len(items)} itens) ─\n"
            _ui.write(st.output, header + "\n".join(items), ctx.dispatch)
        else:
            _ui.write(st.output,
                      "Nenhum problema encontrado para o filtro atual.",
                      ctx.dispatch)
