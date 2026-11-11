"""Aba Editor de Comandos — módulo TabModule (F2-cmd).

Migrado de ``pages/cmd.py`` (``PageBuilderCmdMixin._build_cmd_page``):
a construção virou ``CmdTab.build(ctx) -> QWidget``, o filtro de Enter
referencia a aba (não o App) e o estado vive em :class:`CmdState`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.constants import BUILTIN_CMDS, CMD_TEMPLATES
from huawei_manager.services import get_all_show_commands
from huawei_manager.tabs import _ui
from huawei_manager.tabs.cmd.handlers import CmdHandlers
from huawei_manager.tabs.cmd.state import CmdState
from huawei_manager.widgets.icons import icon
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text, styled_text

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.tabs._contract import TabContext


class _CmdReturnFilter(QObject):
    """Event filter para o editor: Enter executa, Shift+Enter insere nova linha.

    Também trata ShortcutOverride para o QShortcut global("Return") não
    roubar a tecla. Referencia a :class:`CmdTab` — nunca o App.
    """

    def __init__(self, tab: CmdTab) -> None:
        super().__init__()
        self.tab = tab

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        from PySide6.QtCore import Qt as _Qt

        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent):
            # Accept Return/Enter to prevent global QShortcut("Return") from firing
            if event.key() == _Qt.Key.Key_Return or event.key() == _Qt.Key.Key_Enter:
                event.accept()
                return True
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == _Qt.Key.Key_Return or event.key() == _Qt.Key.Key_Enter:
                if event.modifiers() & _Qt.KeyboardModifier.ShiftModifier:
                    getter = getattr(obj, "textCursor", None)
                    cursor: Any = getter() if callable(getter) else None
                    if cursor is not None:
                        cursor.insertText("\n")
                    return True
                else:
                    self.tab.run_cmd_safe(self.tab.get_editor_cmd())
                    return True
        return super().eventFilter(obj, event)


class CmdTab:
    """Módulo da aba Editor de Comandos (TabModule)."""

    def __init__(self) -> None:
        self.state = CmdState()
        self._ctx: TabContext | None = None
        self._handlers: CmdHandlers | None = None

    # ── TabModule ────────────────────────────────────────────────────
    def attach(self, ctx: TabContext) -> None:
        """Injeta o contexto (idempotente) — chamado por build e fachadas.

        Permite executar ações da aba (ex.: rollback via paleta Ctrl+K)
        sem que a UI tenha sido construída: os writes caem nos guards de
        widget ``None`` (paridade com o mixin legado pré-build).
        """
        if self._ctx is None:
            self._ctx = ctx
            self._handlers = CmdHandlers(ctx, self.state)

    def build(self, ctx: TabContext) -> QWidget:
        """Constrói a página do Editor de Comandos."""
        self.attach(ctx)
        state = self.state

        p = _ui.page_frame("cmd")
        _ui.page_title(p, "Editor de Comandos", C.NEON_MAG, "")

        card = QFrame(p)
        card.setObjectName("cmdCard")
        card.setStyleSheet(
            f"QFrame#cmdCard {{ background: {C.BG_CARD};"
            f" border: 1px solid {C.BORDER_SOFT}; border-radius: 10px; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        page_layout = _ui.page_layout(p)
        page_layout.addWidget(card, stretch=1)
        page_layout.addSpacing(8)

        split_w = QWidget(card)
        split_w.setStyleSheet("background: transparent;")
        split_layout = QHBoxLayout(split_w)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(18)
        card_layout.addWidget(split_w, stretch=1)

        # Left: template list
        left = QWidget(split_w)
        left.setMinimumWidth(200)
        left.setMaximumWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left.setStyleSheet("background: transparent;")
        split_layout.addWidget(left)

        tpl_header = QLabel("COMANDOS DISPONIVEIS", left)
        tpl_header.setStyleSheet(_ui.css_label(C.FG_FAINT, "", 11, True))
        left_layout.addWidget(tpl_header)

        state.tpl_listbox = QListWidget(left)
        state.tpl_listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_CARD}; color: {C.FG_MAIN};
                border: none; font: 13px {C.FONT_UI_FAMILY};
                outline: none;
            }}
            QListWidget:focus {{
                border: 1px solid {C.NEON_CYAN};
                border-radius: 8px;
            }}
            QListWidget::item {{
                padding: 8px 11px;
                border-radius: 5px;
            }}
            QListWidget::item:selected {{
                background: {C.rgba(C.NEON_CYAN, 0.09)};
                color: {C.NEON_CYAN};
            }}
            QListWidget::item:hover {{
                background: {C.BG_HOVER};
            }}
        """)
        state.tpl_listbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        left_layout.addWidget(state.tpl_listbox, stretch=1)

        state.tpl_cmd_map = {}
        for name in CMD_TEMPLATES:
            cmd = CMD_TEMPLATES[name]
            if cmd and cmd not in BUILTIN_CMDS:
                state.tpl_cmd_map[name] = cmd

        existing_cmds = set(state.tpl_cmd_map.values())
        show_cmds = get_all_show_commands()
        for svc_name, cmd in show_cmds:
            if cmd not in existing_cmds and cmd not in BUILTIN_CMDS:
                existing_cmds.add(cmd)
                state.tpl_cmd_map[svc_name] = cmd

        for name in sorted(state.tpl_cmd_map.keys()):
            state.tpl_listbox.addItem(name)

        state.tpl_listbox.currentRowChanged.connect(self._on_tpl_select)
        state.tpl_listbox.itemActivated.connect(self._on_tpl_activate)

        # Right: editor + output
        right = QWidget(split_w)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right.setStyleSheet("background: transparent;")
        split_layout.addWidget(right, stretch=1)

        state.editor = styled_text(right)
        state.editor.setMinimumHeight(150)
        state.editor.setPlainText("display ip interface brief")
        right_layout.addWidget(state.editor)

        cmd_filter = _CmdReturnFilter(self)
        cmd_filter.setParent(right)
        state.editor.installEventFilter(cmd_filter)

        abar = QWidget(right)
        abar.setStyleSheet("background: transparent;")
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(abar)

        btn_exec = action_button(abar, "Executar",
                                 lambda: self.run_cmd_safe(self.get_editor_cmd()), C.NEON_CYAN)
        btn_exec.setIcon(icon("i-play", C.NEON_CYAN, 16))
        btn_exec.setIconSize(QSize(16, 16))
        abar_layout.addWidget(btn_exec)
        abar_layout.addSpacing(6)
        btn_cfg = action_button(abar, "Enviar Config",
                                lambda: self.run_config_safe(self.get_editor_cmd()), C.NEON_AMBER)
        btn_cfg.setIcon(icon("i-settings", C.NEON_AMBER, 16))
        btn_cfg.setIconSize(QSize(16, 16))
        abar_layout.addWidget(btn_cfg)

        state.sysview_var = False
        sysview_cb = QCheckBox("system-view", abar)
        sysview_cb.setStyleSheet(f"""
            QCheckBox {{ color: {C.FG_DIM}; background: transparent;
                         font: 12.5px {C.FONT_UI_FAMILY}; spacing: 6px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; }}
        """)
        sysview_cb.stateChanged.connect(lambda s: setattr(state, 'sysview_var', bool(s)))
        abar_layout.addSpacing(12)
        abar_layout.addWidget(sysview_cb)
        abar_layout.addStretch()

        warn_lbl = QLabel("Todas as operações são registradas em huawei_audit_structured.jsonl", right)
        warn_lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, "", 11.5))
        right_layout.addWidget(warn_lbl)

        state.out = output_text(right)
        right_layout.addWidget(state.out, stretch=1)

        return p

    def dispose(self) -> None:
        """Solta refs de widget no rebuild (estado lógico é preservado)."""
        state = self.state
        state.editor = None
        state.out = None
        state.tpl_listbox = None

    # ── Fachadas (usadas pelo shell: atalhos, paleta) ────────────────
    def get_editor_cmd(self) -> str:
        """Retorna o texto atual do editor de comandos."""
        editor = self.state.editor
        return "" if editor is None else editor.toPlainText().strip()

    def run_cmd_safe(self, cmd: str = "") -> None:
        if self._ctx is None:
            return
        self._h().run_cmd_safe(cmd)

    def run_config_safe(self, cmd: str = "") -> None:
        if self._ctx is None:
            return
        self._h().run_config_safe(cmd)

    def rollback_last_config(self) -> None:
        if self._ctx is None:
            return
        self._h().rollback_last_config()

    def out_widget(self) -> QTextEdit | None:
        """Widget de saída (Ctrl+L limpa a saída do editor)."""
        return self.state.out

    # ── Internos ─────────────────────────────────────────────────────
    def _h(self) -> CmdHandlers:
        if self._handlers is None:
            raise RuntimeError("CmdTab não foi construído (build ausente)")
        return self._handlers

    def _on_tpl_select(self, row: int) -> None:
        """Atualiza o editor quando a seleção muda (navegação por teclado)."""
        state = self.state
        if row >= 0 and state.tpl_listbox is not None:
            name = state.tpl_listbox.item(row).text()
            cmd = state.tpl_cmd_map.get(name)
            if cmd and state.editor is not None:
                state.editor.setPlainText(cmd)

    def _on_tpl_activate(self, item: QListWidgetItem) -> None:
        """Enter/Space ativa o template (acessibilidade por teclado)."""
        state = self.state
        cmd = state.tpl_cmd_map.get(item.text())
        if cmd and state.editor is not None:
            state.editor.setPlainText(cmd)
