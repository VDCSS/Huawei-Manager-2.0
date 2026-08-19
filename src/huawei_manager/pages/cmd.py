"""PageBuilder mixin — Command Editor page (_build_cmd_page)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.constants import BUILTIN_CMDS, CMD_TEMPLATES
from huawei_manager.services import get_all_show_commands
from huawei_manager.widgets.neon_button import action_button
from huawei_manager.widgets.neon_entry import output_text, styled_text


class _CmdReturnFilter(QObject):
    """Event filter for cmd_editor: Enter runs command, Shift+Enter inserts newline.

    Also handles ShortcutOverride to prevent global Return shortcut from stealing the key.
    """

    def __init__(self, app_ref: object) -> None:
        super().__init__()
        self.app = app_ref

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        from PySide6.QtCore import Qt as _Qt

        if event.type() == QEvent.Type.ShortcutOverride:
            # Accept Return/Enter to prevent global QShortcut("Return") from firing
            if event.key() == _Qt.Key.Key_Return or event.key() == _Qt.Key.Key_Enter:
                event.accept()
                return True
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.KeyPress:
            if event.key() == _Qt.Key.Key_Return or event.key() == _Qt.Key.Key_Enter:
                if event.modifiers() & _Qt.KeyboardModifier.ShiftModifier:
                    cursor = obj.textCursor() if hasattr(obj, "textCursor") else None
                    if cursor:
                        cursor.insertText("\n")
                    return True
                else:
                    self.app._run(lambda cmd=self.app._get_editor_cmd(): self.app._exec_cmd(cmd))
                    return True
        return super().eventFilter(obj, event)


class PageBuilderCmdMixin:
    """Mixin — Command Editor page builder."""

    def _build_cmd_page(self: AppCoreProtocol) -> None:
        """Constrói a página do Editor de Comandos."""
        p = self._make_page("cmd")
        self._page_title(p, "Editor de Comandos", C.NEON_MAG, "")

        card = QFrame(p)
        card.setStyleSheet(f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; border-radius: 4px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        self._page_layout(p).addWidget(card, stretch=1)
        self._page_layout(p).addSpacing(8)

        split_w = QWidget(card)
        split_layout = QHBoxLayout(split_w)
        split_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(split_w, stretch=1)

        # Left: template list
        left = QWidget(split_w)
        left.setMinimumWidth(200)
        left.setMaximumWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left.setStyleSheet(f"background: {C.BG_INPUT};")
        split_layout.addWidget(left)
        split_layout.addSpacing(10)

        tpl_header = QLabel("COMANDOS DISPONIVEIS", left)
        tpl_header.setStyleSheet(self._css_label(C.FG_DIM, C.BG_INPUT, 10, True))
        left_layout.addWidget(tpl_header)

        self._tpl_listbox = QListWidget(left)
        self._tpl_listbox.setStyleSheet(f"""
            QListWidget {{
                background: {C.BG_INPUT}; color: {C.NEON_CYAN};
                border: none; font: 12px 'Inter';
                outline: none;
            }}
            QListWidget:focus {{
                border: 1px solid {C.NEON_CYAN};
            }}
            QListWidget::item:selected {{
                background: {C.NEON_PURP}; color: white;
            }}
            QListWidget::item:hover {{
                background: #2a2a4a;
            }}
        """)
        self._tpl_listbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        left_layout.addWidget(self._tpl_listbox, stretch=1)

        self._tpl_cmd_map: dict[str, str] = {}
        for name in CMD_TEMPLATES:
            cmd = CMD_TEMPLATES[name]
            if cmd and cmd not in BUILTIN_CMDS:
                self._tpl_cmd_map[name] = cmd

        existing_cmds = set(self._tpl_cmd_map.values())
        show_cmds = get_all_show_commands()
        for svc_name, cmd in show_cmds:
            if cmd not in existing_cmds and cmd not in BUILTIN_CMDS:
                existing_cmds.add(cmd)
                self._tpl_cmd_map[svc_name] = cmd

        for name in sorted(self._tpl_cmd_map.keys()):
            self._tpl_listbox.addItem(name)

        self._tpl_listbox.currentRowChanged.connect(self._on_tpl_select)
        self._tpl_listbox.itemActivated.connect(self._on_tpl_activate)

        # Right: editor + output
        right = QWidget(split_w)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right.setStyleSheet(f"background: {C.BG_INPUT};")
        split_layout.addWidget(right, stretch=1)

        self._cmd_editor = styled_text(right)
        self._cmd_editor.setMinimumHeight(150)
        self._cmd_editor.setPlainText("display ip interface brief")
        right_layout.addWidget(self._cmd_editor)
        right_layout.addSpacing(6)

        cmd_filter = _CmdReturnFilter(self)
        self._cmd_editor.installEventFilter(cmd_filter)

        abar = QWidget(right)
        abar_layout = QHBoxLayout(abar)
        abar_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(abar)
        right_layout.addSpacing(6)

        btn_exec = action_button(abar, "\u25b6 Executar",
                                 lambda: self._run(
                                     lambda cmd=self._get_editor_cmd(): self._exec_cmd(cmd)), C.NEON_CYAN)
        abar_layout.addWidget(btn_exec)
        abar_layout.addSpacing(6)
        btn_cfg = action_button(abar, "\u2699 Enviar Config",
                                lambda: self._run(
                                    lambda cmd=self._get_editor_cmd(): self._exec_config(cmd)), C.NEON_AMBER)
        abar_layout.addWidget(btn_cfg)

        self._sysview_var = False
        sysview_cb = QCheckBox("system-view", abar)
        sysview_cb.setStyleSheet(f"""
            QCheckBox {{ color: {C.FG_DIM}; background: {C.BG_INPUT}; font: 11px 'Inter'; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; }}
        """)
        sysview_cb.stateChanged.connect(lambda s: setattr(self, '_sysview_var', bool(s)))
        abar_layout.addSpacing(12)
        abar_layout.addWidget(sysview_cb)
        abar_layout.addStretch()

        warn_lbl = QLabel("\u26a0  Todas as operacoes sao registradas em huawei_audit_structured.jsonl", right)
        warn_lbl.setStyleSheet(self._css_label(C.NEON_AMBER, C.BG_INPUT, 10))
        right_layout.addWidget(warn_lbl)
        right_layout.addSpacing(4)

        self.out_cmd = output_text(right)
        right_layout.addWidget(self.out_cmd, stretch=1)

    def _on_tpl_select(self, row: int) -> None:
        """Atualiza o editor quando a seleção muda (navegação por teclado)."""
        if row >= 0:
            name = self._tpl_listbox.item(row).text()
            cmd = self._tpl_cmd_map.get(name)
            if cmd:
                self._cmd_editor.setPlainText(cmd)

    def _on_tpl_activate(self, item) -> None:
        """Enter/Space ativa o template (acessibilidade por teclado)."""
        name = item.text()
        cmd = self._tpl_cmd_map.get(name)
        if cmd:
            self._cmd_editor.setPlainText(cmd)
