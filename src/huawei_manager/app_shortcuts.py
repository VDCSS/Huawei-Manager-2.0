from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QTextEdit

import huawei_manager.constants as C


class ShortcutsMixin(QObject):
    def _setup_bindings(self) -> None:
        parent: QObject = self
        QShortcut(QKeySequence("Return"), parent).activated.connect(self._on_enter)
        QShortcut(QKeySequence("Ctrl+Shift+Return"), parent).activated.connect(
            self._on_ctrl_shift_enter)
        QShortcut(QKeySequence("Ctrl+D"), parent).activated.connect(self._on_ctrl_d)
        QShortcut(QKeySequence("Ctrl+L"), parent).activated.connect(self._on_ctrl_l)
        QShortcut(QKeySequence("Ctrl+Q"), parent).activated.connect(self._on_ctrl_q)
        QShortcut(QKeySequence("Ctrl+Shift+A"), parent).activated.connect(
            self._on_ctrl_shift_a)
        QShortcut(QKeySequence("F5"), parent).activated.connect(self._on_f5)
        QShortcut(QKeySequence("Ctrl+Tab"), parent).activated.connect(self._on_ctrl_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), parent).activated.connect(
            self._on_ctrl_shift_tab)
        QShortcut(QKeySequence("Escape"), parent).activated.connect(self._on_escape)
        for i, key in enumerate(self._PAGE_KEYS[:9], 1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), parent).activated.connect(
                lambda _chk, k=key: self._show_page(k))

    def _on_enter(self) -> None:
        focus = self.focusWidget()
        if isinstance(focus, QTextEdit):
            return
        page = self._current_page
        if page == "config":
            self._run(self._fetch_config)
        elif page == "route":
            label_to_key = {v: k for k, v in C.ROUTE_FILTER_LABELS.items()}
            fkey = label_to_key.get(self._route_filter_cb.currentText(), "routing")
            self._run(lambda: self._fetch_route(fkey))
        elif page == "arp":
            self._run(self._fetch_arp)
        elif page == "info":
            self._run(self._fetch_info)
        elif page == "cmd":
            cmd = self._get_editor_cmd()
            if cmd:
                self._run(lambda: self._exec_cmd(cmd))
        elif page == "backup":
            fmt = self._backup_fmt_cb.currentText()
            self._run(lambda: self._do_backup(fmt))

    def _on_ctrl_shift_enter(self) -> None:
        if self._current_page == "cmd":
            cmd = self._get_editor_cmd()
            if cmd:
                self._run(lambda: self._exec_config(cmd))

    def _on_ctrl_d(self) -> None:
        self._toggle_connect()

    def _on_ctrl_l(self) -> None:
        page = self._current_page
        if page == "config" and self.out_config is not None:
            self._write(self.out_config, "")
        elif page == "route" and self.out_route is not None:
            self._write(self.out_route, "")
        elif page == "arp" and self.out_arp is not None:
            self._write(self.out_arp, "")
        elif page == "info" and self.out_info is not None:
            self._write(self.out_info, "")
        elif page == "cmd" and self.out_cmd is not None:
            self._write(self.out_cmd, "")
        elif page == "backup" and self.out_backup is not None:
            self._write(self.out_backup, "")
        elif page == "services" and self._svc_output is not None:
            self._write(self._svc_output, "")

    def _on_ctrl_q(self) -> None:
        self._on_close()

    def _on_ctrl_shift_a(self) -> None:
        self._show_auth_dialog()

    def _on_f5(self) -> None:
        page = self._current_page
        if page == "topology":
            self._spawn_io(self._refresh_vnfs)
        elif page == "services":
            self._refresh_service_list()
        else:
            self._on_enter()

    def _on_ctrl_tab(self) -> None:
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx + 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_ctrl_shift_tab(self) -> None:
        if not self._current_page:
            return
        try:
            idx = self._PAGE_KEYS.index(self._current_page)
            self._show_page(self._PAGE_KEYS[(idx - 1) % len(self._PAGE_KEYS)])
        except ValueError:
            self._show_page(self._PAGE_KEYS[0])

    def _on_escape(self) -> None:
        self._on_ctrl_l()
