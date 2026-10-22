"""Aba Backup — módulo TabModule (F2-backup).

Migrado de ``pages/builder.py`` (``_build_backup_page`` +
``_choose_backup_dir``): a construção virou ``BackupTab.build(ctx) ->
QWidget`` e o estado vive em :class:`BackupState`.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.tabs import _ui
from huawei_manager.tabs.backup.handlers import BackupHandlers
from huawei_manager.tabs.backup.state import BackupState
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import neon_entry, output_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class BackupTab:
    """Módulo da aba Backup (TabModule)."""

    def __init__(self) -> None:
        self.state = BackupState()
        self._ctx: TabContext | None = None
        self._handlers: BackupHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite acionar o backup via atalho/atalho sem que a UI tenha
        sido construída: os writes caem nos guards de widget ``None``
        (paridade com o mixin legado pré-build).
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = BackupHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página de Backup de Configuração."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("backup")
        _ui.page_title(p, "Backup de Configuracao", C.NEON_PURP,
                       "display current-configuration → arquivo")

        ctrl = QWidget(p)
        ctrl.setStyleSheet(f"background: {C.BG_CARD};")
        ctrl.setMaximumHeight(40)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        page_layout = _ui.page_layout(p)
        page_layout.addWidget(ctrl)
        page_layout.addSpacing(12)

        dest_lbl = QLabel("Destino:", ctrl)
        dest_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        ctrl_layout.addWidget(dest_lbl)
        ctrl_layout.addSpacing(8)

        state.backup_entry = neon_entry(ctrl, width=24)
        state.backup_entry.setSizePolicy(QSizePolicy.Policy.Expanding,
                                         QSizePolicy.Policy.Fixed)
        state.backup_path = os.path.expanduser("~")
        state.backup_entry.setText(state.backup_path)
        state.backup_entry.textChanged.connect(
            lambda t: setattr(state, 'backup_path', t))
        ctrl_layout.addWidget(state.backup_entry)

        btn_dir = action_button(ctrl, "📁 Escolha",
                                self._choose_backup_dir, C.NEON_PURP)
        ctrl_layout.addWidget(btn_dir)
        ctrl_layout.addSpacing(8)

        fmt_frame = QWidget(p)
        fmt_frame.setStyleSheet(f"background: {C.BG_CARD};")
        fmt_frame.setMaximumHeight(40)
        fmt_layout = QHBoxLayout(fmt_frame)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(fmt_frame)
        page_layout.addSpacing(8)

        fmt_lbl = QLabel("Formato:", fmt_frame)
        fmt_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        fmt_layout.addWidget(fmt_lbl)
        fmt_layout.addSpacing(8)

        state.fmt_lbl = QLabel(f"Formato: {C.BACKUP_FMT_TEXT}", fmt_frame)
        state.fmt_lbl.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_CARD, 11))
        fmt_layout.addWidget(state.fmt_lbl)
        fmt_layout.addStretch()

        state.out = output_text(p)
        page_layout.addWidget(state.out, stretch=1)
        page_layout.addSpacing(10)
        btn = action_button(p, "💾  Fazer Backup",
                            lambda: self.run_backup(C.BACKUP_FMT_TEXT),
                            C.NEON_PURP)
        page_layout.addWidget(btn)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        state = self.state
        state.out = None
        state.backup_entry = None
        state.fmt_lbl = None

    # ── Fachadas (usadas pelo shell: atalhos) ────────────────────────
    def run_backup(self, fmt: str = "") -> None:
        """Despacha ``do_backup`` na IO thread (paridade com legado)."""
        if self._ctx is None:
            return
        self._ctx.run(lambda: self._h().do_backup(fmt))

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída do backup)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> BackupHandlers:
        if self._handlers is None:
            raise RuntimeError("BackupTab não foi construído (build ausente)")
        return self._handlers

    def _choose_backup_dir(self) -> None:
        """Abre QFileDialog e atualiza o caminho de destino do backup."""
        d = QFileDialog.getExistingDirectory(
            None, "Escolha o diretorio", self.state.backup_path)
        if d:
            self.state.backup_path = d
            if self.state.backup_entry is not None:
                self.state.backup_entry.setText(d)
