#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Event handlers (PySide6) — connection, fetch, exec, backup, dialogs, etc."""

from __future__ import annotations

import datetime
import io
import os
import re

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager._config import (
    ADMIN_PASSWORD,
    PROJECT_ROOT,
    TECNICO_PASSWORD,
    audit,
    log,
)
from huawei_manager.constants import (
    CLI_FILTERS,
    ROUTE_FILTER_LABELS,
)
from huawei_manager.sdn_controller.authz import Role
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.validator import CommandValidator
from huawei_manager.services import VNF_TYPES, ServiceDef, execute_service
from huawei_manager.vnf_models import (
    VNF,
    load_vnf_inventory,
    probe_vnfs,
    save_vnf_inventory,
    simulate_status,
)
from huawei_manager.widgets import AuthOverlay, action_button

_INVENTORY_PATH = str(PROJECT_ROOT / "src" / "huawei_manager" / "data" / "vnf_inventory.json")


class EventHandlers:
    """Mixin de eventos PySide6: conexao SSH, fetch, backup, servicos, autenticacao e VNFs."""

    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30

    # ══════════════════════════════════════════════════════════════════
    #  CONEXAO SSH
    # ══════════════════════════════════════════════════════════════════
    def _get_selected_vnf(self) -> VNF | None:
        """Retorna o VNF selecionado no canvas ou o alvo salvo em _target_vnf."""
        return (self._topo_canvas.get_selected()
                if self._topo_canvas else None) or self._target_vnf

    def _toggle_connect(self) -> None:
        """Alterna entre conectar (VNF alvo ou default) e desconectar."""
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado", C.NEON_PURP)
            self._set_conn_btn()
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source="user", data={"reason": "manual"}))
            return

        vnf = self._get_selected_vnf()
        if vnf:
            self._connect_with_vnf(vnf)
        else:
            self._connect_default()

    def _do_connect(self, on_success_fmt: str, on_error_msg: str) -> None:
        """Tenta conectar SSH em background; atualiza status conforme resultado."""
        self._session_tracker.touch()
        def _do():
            """Executa a conexao SSH em background."""
            try:
                self._sb.connect()
                sid = self.session._session_id or "?"
                self._dispatch(lambda: self._set_status(
                    on_success_fmt.format(sid=sid), C.NEON_CYAN))
                self._set_conn_btn("  DESCONECTAR  ")
                self._event_queue.put(Event(EventType.DEVICE_CONNECTED,
                                            source="user", data={"session_id": sid}))
            except NetmikoAuthenticationException:
                self._dispatch(lambda: self._set_status(
                    "Falha de autenticacao", C.NEON_AMBER))
                self._set_conn_btn()
            except NetmikoTimeoutException:
                self._dispatch(lambda: self._set_status(
                    "Timeout de conexao", C.NEON_AMBER))
                self._set_conn_btn()
            except ValueError as exc:
                msg = f"Config: {exc}"
                self._dispatch(lambda: self._set_status(msg, C.NEON_AMBER))
                self._set_conn_btn()
            except Exception as exc:
                log.exception("Falha inesperada em _do_connect: %s", exc)
                self._dispatch(lambda: self._set_status(
                    on_error_msg, C.NEON_AMBER))
                self._set_conn_btn()

        self._spawn_io(_do)

    def _connect_default(self) -> None:
        """Conecta ao roteador padrao definido nas configuracoes."""
        self._set_status("Conectando SSH\u2026", C.NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect("SSH \u2714  {sid}", "Erro ao conectar")

    def _connect_with_vnf(self, vnf: VNF) -> None:
        """Sobrescreve parametros SSH com os dados do VNF e conecta."""
        if self._sb.is_alive():
            self._sb.disconnect()
        self.session.override_host = vnf.host
        self.session.override_port = vnf.port
        self.session.override_username = vnf.username or None
        self.session.override_password = vnf.password or None
        self.session.override_ssh_key = vnf.ssh_key or None
        self._set_status(f"Conectando ao VNF {vnf.name}\u2026", C.NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect(f"VNF \u2714  {vnf.name}  {{sid}}", "Erro ao conectar ao VNF")

    # ══════════════════════════════════════════════════════════════════
    #  FETCH METHODS
    # ══════════════════════════════════════════════════════════════════
    def _fetch_config(self) -> None:
        """Busca a configuracao atual do roteador (display current-configuration)."""
        self._session_tracker.touch()
        self._loading(self.out_config, "Carregando configuracao atual\u2026")
        output = self._sb.send_command("display current-configuration")
        self._write(self.out_config, output)
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch", data={"command": "display current-configuration"}))

    def _fetch_route(self) -> None:
        """Busca a tabela de roteamento com o filtro selecionado."""
        self._session_tracker.touch()
        label_to_key = {v: k for k, v in ROUTE_FILTER_LABELS.items()}
        fkey = label_to_key.get(self._route_filter_cb.currentText(), "routing")
        if fkey == "routing":
            entries = self._drv.get_routing_table()
            buf = io.StringIO()
            buf.write(f"{'Destino/Mask':<22} {'Proto':<10} {'Pre':>4} {'Custo':>6}  {'NextHop':<16} {'Interface'}\n")
            buf.write(f"{'-' * 72}\n")
            for e in entries:
                route = f"{e.destination}/{e.mask}"
                buf.write(f"{route:<22} {e.protocol:<10} {e.preference:>4} {e.cost:>6}"
                          f"  {e.next_hop:<16} {e.interface}\n")
            self._write(self.out_route, buf.getvalue())
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="fetch", data={"command": "display ip routing-table"}))
        else:
            cmd = CLI_FILTERS.get(fkey, "display ip routing-table")
            self._loading(self.out_route, f"Executando: {cmd}\u2026")
            self._write(self.out_route, self._sb.send_command(cmd or ""))
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="fetch", data={"command": cmd or ""}))

    def _fetch_arp(self) -> None:
        """Busca a tabela ARP do roteador."""
        self._session_tracker.touch()
        entries = self._drv.get_arp_table()
        buf = io.StringIO()
        buf.write(f"{'IP Address':<18} {'MAC Address':<20} {'Tipo':<6} {'Interface'}\n")
        buf.write(f"{'-' * 60}\n")
        for e in entries:
            buf.write(f"{e.ip_address:<18} {e.mac_address:<20} {e.status:<6} {e.interface}\n")
        self._write(self.out_arp, buf.getvalue())
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch", data={"command": "display arp"}))

    def _fetch_info(self) -> None:
        """Coleta multiplas informacoes do sistema (versao, CPU, memoria, interfaces, LLDP)."""
        self._session_tracker.touch()
        self._loading(self.out_info, "Coletando informacoes do sistema\u2026")
        buf = io.StringIO()
        commands = [
            ("Versao / Sistema", "display version"),
            ("Dispositivo", "display device"),
            ("Licenca", "display license"),
            ("CPU", "display cpu-usage"),
            ("Memoria", "display memory-usage"),
            ("LLDP", "display lldp neighbor brief"),
        ]
        for title, cmd in commands:
            buf.write(f"{'=' * 70}\n\u25b6  {title}\n{'-' * 70}\n")
            buf.write(self._sb.send_command(cmd or ""))
            buf.write("\n\n")
        buf.write(f"{'=' * 70}\n\u25b6  Interfaces\n{'-' * 70}\n")
        intf_entries = self._drv.get_interfaces()
        if intf_entries:
            buf.write(f"{'Interface':<30} {'Status':<8} {'Protocolo'}\n")
            buf.write(f"{'-' * 50}\n")
            for e in intf_entries:
                buf.write(f"{e.name:<30} {e.status:<8} {e.protocol_status}\n")
        else:
            buf.write("(nenhuma interface encontrada)\n")
        buf.write("\n\n")
        self._write(self.out_info, buf.getvalue())
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch", data={"command": "display version, interfaces, lldp, etc."}))

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR
    # ══════════════════════════════════════════════════════════════════
    def _get_editor_cmd(self) -> str:
        """Retorna o texto atual do editor de comandos."""
        return self._cmd_editor.toPlainText().strip()

    def _exec_cmd(self) -> None:
        """Executa o comando do editor, opcionalmente dentro de system-view."""
        self._session_tracker.touch()
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd, "\u2718  Editor vazio \u2014 digite um comando")
            return
        validator: CommandValidator | None = self._cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._access_level)
            if not vr.allowed:
                self._write(self.out_cmd, f"\u2718  Comando bloqueado: {vr.reason}")
                return
        if self._sysview_var:
            self._loading(self.out_cmd,
                          "system-view \u2192 " + cmd.splitlines()[0] + " \u2192 quit\u2026")
            _ok, result = self._sb.send_config(cmd.strip().splitlines())
        else:
            self._loading(self.out_cmd, f"Executando: {cmd}\u2026")
            result = self._sb.send_command(cmd or "")
        self._write(self.out_cmd, result)
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="editor", data={"command": cmd.splitlines()[0], "mode": "exec"}))

    def _exec_config(self) -> None:
        """Envia comandos de configuracao do editor via send_config."""
        self._session_tracker.touch()
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd,
                         "\u2718  Editor vazio \u2014 digite os comandos de configuracao")
            return
        validator: CommandValidator | None = self._cmd_validator
        if validator is not None:
            vr = validator.validate(cmd, self._access_level)
            if not vr.allowed:
                self._write(self.out_cmd, f"\u2718  Config bloqueada: {vr.reason}")
                return
        dry_run: DryRunEngine | None = self._dry_run
        if dry_run is not None and self.session.is_connected:
            try:
                current = self.session.run_cli_rpc("display current-configuration")
                diff_report = dry_run.diff(current, cmd)
                if diff_report.has_changes:
                    preview = diff_report.summary + "\n\n"
                    for line in diff_report.added[:10]:
                        preview += line
                    for line in diff_report.removed[:10]:
                        preview += line
                    self._loading(self.out_cmd, f"Dry-run: {diff_report.summary}")
                else:
                    self._write(self.out_cmd, "\u2139  Nenhuma alteracao detectada em relacao a config atual.")
                    return
            except Exception:
                pass
        self._loading(self.out_cmd, "Aplicando configuracao\u2026")
        ok, msg = self._sb.send_config(cmd.strip().splitlines())
        self._write(self.out_cmd, msg)
        self._event_queue.put(Event(EventType.CONFIG_CHANGED,
                                    source="editor", data={"status": "ok" if ok else "error"}))

    # ══════════════════════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════════════════════
    def _do_backup(self) -> None:
        """Salva a running-config em arquivo TXT e registra na auditoria."""
        self._session_tracker.touch()
        fmt = self._backup_fmt_cb.currentText()
        self._loading(self.out_backup, "Coletando configuracao para backup\u2026")
        conteudo = self._sb.send_command("display current-configuration")
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext  = "txt"
        host = self.session._host
        nome = f"backup_{host}_{ts}.{ext}"
        pasta = self.backup_path or os.path.expanduser("~")
        path  = os.path.join(pasta, nome)
        try:
            os.makedirs(pasta, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                header = (
                    f"# Backup CLI\n"
                    f"# Host   : {host}\n"
                    f"# User   : {self.session._user}\n"
                    f"# Data   : {ts}\n\n"
                )
                fh.write(header + conteudo)
            linhas = conteudo.count("\n") + 1
            resumo = (
                f"\u2714  Backup concluido!\n{'-' * 60}\n"
                f"  Arquivo  : {path}\n"
                f"  Formato  : {fmt}\n"
                f"  Data     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"  Linhas   : {linhas}\n"
                f"  Tamanho  : {os.path.getsize(path):,} bytes\n"
                f"{'-' * 60}\n\nPrevia (40 linhas):\n\n"
                + "\n".join(conteudo.splitlines()[:40])
            )
            self._write(self.out_backup, resumo)
            self._dispatch(lambda: self._set_status(f"Backup: {nome}", C.NEON_CYAN))
            audit.log_operation("backup", user=self.session._user,
                                host=host, status="ok", file=path)
            log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="backup", data={"file": path, "host": host}))
        except OSError as ex:
            log.error("Backup falhou: %s", ex)
            self._write(self.out_backup, f"\u2718  Erro ao salvar:\n  {ex}")

    # ══════════════════════════════════════════════════════════════════
    #  SERVICOS
    # ══════════════════════════════════════════════════════════════════
    def _run_service(self, svc: ServiceDef) -> None:
        """Executa um servico no modo mock ou cli, com substituicao de parametros e sanitizacao."""
        mode = self._svc_mode_var
        vnf = self._target_vnf
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if vnf:
            label += f"  |  Alvo: {vnf.name} ({vnf.host})"
        self._svc_vnf_lbl.setText(label)

        _REJECT_PARAM = re.compile(r"[;&|`$(){}]")

        final_svc = svc
        if svc.config_mode and self._svc_param_entries:
            cmd = svc.description
            for name, entry in self._svc_param_entries.items():
                val = entry.text().strip()
                if _REJECT_PARAM.search(val):
                    self._write(self._svc_output,
                        f"\u2718  Parametro '{name}' contem caracteres invalidos "
                        f"(& ; | ` $ ( ) {{ }}).")
                    return
                cmd = cmd.replace(f"<{name}>", val)
            final_svc = ServiceDef(
                id=svc.id, name=svc.name, description=svc.description,
                category=svc.category, vnf_types=svc.vnf_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        def _do():
            """Executa o servico selecionado (mock ou SSH real)."""
            self._loading(self._svc_output, f"Executando: {svc.name} ({mode})\u2026")

            if mode == "mock":
                result = execute_service(final_svc, session_type="mock")
                self._write(self._svc_output, result)
                self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                            source="service", data={"name": svc.name, "mode": "mock"}))
                return

            if not self._sb.is_alive():
                self._write(self._svc_output,
                    "\u2718  Sem sessao SSH ativa. Conecte-se primeiro.")
                return

            if mode == "cli":
                result = execute_service(final_svc, session_type="cli",
                                         session=self.session._conn)
                self._write(self._svc_output, result)
                self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                            source="service", data={"name": svc.name, "mode": "cli"}))
                return

            self._write(self._svc_output, f"Modo desconhecido: {mode}")

        self._spawn_io(_do)

    # ══════════════════════════════════════════════════════════════════
    #  TOPOLOGIA / VNFs
    # ══════════════════════════════════════════════════════════════════
    def _init_topology_backend(self) -> None:
        """Inicializa o backend da topologia (apenas log inicial)."""
        log.info("Topology backend: vnf_inventory.json")

    def _refresh_vnfs(self) -> None:
        """Recarrega o inventario de VNFs, aplica probe/simulacao e atualiza a UI."""
        vnfs_lock = self._vnfs_lock
        if vnfs_lock is not None and not vnfs_lock.acquire(blocking=False):
            return
        try:
            vnfs = load_vnf_inventory(_INVENTORY_PATH)
            if self._mock_mode:
                vnfs = simulate_status(vnfs)
            else:
                vnfs = probe_vnfs(vnfs)
            save_vnf_inventory(vnfs, _INVENTORY_PATH)
            self._dispatch(lambda: self._update_vnfs_ui(vnfs))
            self._dispatch(lambda: (
                self._vnf_status_lbl.setText(
                    "Inventario: {} dispositivos  \u2022  {}"
                    .format(len(vnfs), datetime.datetime.now().strftime('%H:%M:%S'))
                )
            ) if self._vnf_status_lbl is not None else None)
        finally:
            if vnfs_lock is not None:
                vnfs_lock.release()

    def _update_vnfs_ui(self, vnfs: list[VNF]) -> None:
        """Atualiza o canvas de topologia com a nova lista de VNFs."""
        self._vnfs = vnfs
        if self._topo_canvas:
            self._topo_canvas.set_access(self._access_level)
            self._topo_canvas.update_vnfs(vnfs)

    # ── Autenticacao (Admin / Tecnico) ────────────────────────────────
    def _show_auth_dialog(self) -> None:
        if self._access_level != "user":
            self._access_level = "user"
            self._session_tracker.set_role(Role.USER)
            self._mock_mode = False
            self._watcher.stop()
            self._rebuild_page("topology")
            log.info("Acesso: deslogado")
            return

        if self._auth_overlay is not None and self._auth_overlay.isVisible():
            return

        if not ADMIN_PASSWORD or not TECNICO_PASSWORD:
            QMessageBox.warning(None, "Configuracao incompleta",
                "Defina ADMIN_PASSWORD e TECNICO_PASSWORD no .env")
            return

        now = datetime.datetime.now().timestamp()
        if now < self._admin_locked_until:
            remaining = int(self._admin_locked_until - now)
            QMessageBox.warning(None, "Acesso Bloqueado",
                f"Tentativas excedidas. Aguarde {remaining}s e tente novamente.")
            return

        def _on_result(level: str, attempts: int, locked_until: float) -> None:
            if level != "user":
                self._access_level = level
                self._session_tracker.set_role(Role.from_string(level))
                self._admin_attempts = 0
                self._admin_locked_until = 0
                self._rebuild_page("topology")
                if level == "tecnico":
                    self._watcher.start()
                else:
                    self._watcher.stop()
                log.info("Acesso: %s autenticado", level)
            else:
                self._admin_attempts = attempts
                self._admin_locked_until = locked_until
                if locked_until > 0:
                    log.warning("Acesso: lockout por %ds", self.ADMIN_LOCKOUT_SECS)

        overlay = AuthOverlay(
            parent=self.content,
            on_result=_on_result,
            admin_locked_until=self._admin_locked_until,
            admin_max_attempts=self.ADMIN_MAX_ATTEMPTS,
            admin_lockout_secs=self.ADMIN_LOCKOUT_SECS,
            attempts_so_far=self._admin_attempts,
        )
        self._auth_overlay = overlay
        overlay.show()

    # ── Device Dialog ────────────────────────────────────────────────
    def _show_device_dialog(self, vnf: VNF | None = None) -> None:
        """Abre dialogo para cadastrar ou editar um dispositivo VNF."""
        if self._access_level == "user":
            return
        editing = vnf is not None
        vnf = vnf or VNF(id="", name="", host="")

        win = QDialog()
        win.setWindowTitle("Editar Dispositivo" if editing else "Cadastrar Dispositivo")
        win.setMinimumSize(500, 480)
        win.setWindowFlags(win.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        win.setStyleSheet(f"background: {C.BG_CARD};")
        layout = QVBoxLayout(win)
        layout.setContentsMargins(20, 16, 20, 12)

        # Nome
        name_row = QWidget(win)
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(name_row)
        name_lbl = QLabel("Nome:", name_row)
        name_lbl.setStyleSheet(f"color: {C.FG_DIM}; font: 11px 'Inter'; min-width: 80px;")
        name_layout.addWidget(name_lbl)
        name_entry = QLineEdit(win)
        name_entry.setText(vnf.name)
        name_entry.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"padding: 4px 8px; font: 12px 'Inter';")
        name_layout.addWidget(name_entry, stretch=1)

        # Tipo
        type_row = QWidget(win)
        type_layout = QHBoxLayout(type_row)
        type_layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(type_row)
        type_lbl = QLabel("Tipo:", type_row)
        type_lbl.setStyleSheet(f"color: {C.FG_DIM}; font: 11px 'Inter'; min-width: 80px;")
        type_layout.addWidget(type_lbl)
        type_cb = QComboBox(win)
        type_cb.addItems(list(VNF_TYPES.keys()))
        idx = type_cb.findText(vnf.type)
        if idx >= 0:
            type_cb.setCurrentIndex(idx)
        type_cb.setStyleSheet(
            f"QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"padding: 4px 8px; font: 12px 'Inter'; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {C.BG_INPUT}; "
            f"color: {C.NEON_CYAN}; selection-background-color: {C.NEON_PURP}; }}")
        type_layout.addWidget(type_cb, stretch=1)

        layout.addSpacing(6)

        fields = [
            ("host", "IP / Host", vnf.host),
            ("port", "Porta SSH", str(vnf.port)),
            ("username", "Usuario SSH", vnf.username),
            ("password", "Senha SSH", vnf.password, True),
            ("ssh_key", "Chave SSH (path)", vnf.ssh_key),
            ("location", "Localizacao", vnf.location),
        ]

        entries: dict[str, QLineEdit] = {}

        for fname, flabel, *rest in fields:
            is_secret = len(rest) > 1 and rest[1] is True
            default = rest[0]
            row = QWidget(win)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            layout.addWidget(row)

            lbl = QLabel(f"{flabel}:", row)
            lbl.setStyleSheet(f"color: {C.FG_DIM}; font: 11px 'Inter'; min-width: 80px;")
            lbl.setFixedWidth(100)
            row_layout.addWidget(lbl)

            entry = QLineEdit(row)
            entry.setText(default)
            entry.setStyleSheet(
                f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
                f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
                f"padding: 4px 8px; font: 12px 'Inter';")
            if is_secret:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            row_layout.addWidget(entry, stretch=1)
            entries[fname] = entry

            if is_secret:
                show_cb = QCheckBox("Exibir", row)
                show_cb.setStyleSheet(
                    f"color: {C.NEON_PURP}; font: 11px 'Inter';")
                show_cb.toggled.connect(
                    lambda checked, e=entry: e.setEchoMode(
                        QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
                row_layout.addWidget(show_cb)

        def _save():
            """Valida e persiste os dados do dispositivo no inventario."""
            name = name_entry.text().strip()
            if not name:
                QMessageBox.warning(None, "Validacao", "Nome e obrigatorio.")
                return
            host = entries["host"].text().strip()
            if not host:
                QMessageBox.warning(None, "Validacao", "IP/Host e obrigatorio.")
                return

            try:
                port_val = int(entries["port"].text().strip() or "22")
                if not (1 <= port_val <= 65535):
                    QMessageBox.warning(None, "Validacao", "Porta deve estar entre 1 e 65535.")
                    return
            except ValueError:
                port_val = 22

            vnfs = load_vnf_inventory(_INVENTORY_PATH)
            if editing:
                new_vnf = VNF(
                    id=vnf.id, name=name,
                    host=host, port=port_val,
                    type=type_cb.currentText(),
                    username=entries["username"].text().strip(),
                    password=entries["password"].text().strip(),
                    ssh_key=entries["ssh_key"].text().strip(),
                    location=entries["location"].text().strip(),
                )
                for i, v in enumerate(vnfs):
                    if v.id == vnf.id:
                        vnfs[i] = new_vnf
                        break
                else:
                    vnfs.append(new_vnf)
            else:
                new_id = f"vnf-{len(vnfs) + 1:03d}-{name.lower().replace(' ', '-')}"
                new_vnf = VNF(
                    id=new_id, name=name,
                    host=host, port=port_val,
                    type=type_cb.currentText(),
                    username=entries["username"].text().strip(),
                    password=entries["password"].text().strip(),
                    ssh_key=entries["ssh_key"].text().strip(),
                    location=entries["location"].text().strip(),
                )
                vnfs.append(new_vnf)

            save_vnf_inventory(vnfs, _INVENTORY_PATH)
            win.accept()
            self._spawn_io(self._refresh_vnfs)

        layout.addSpacing(12)

        bar = QWidget(win)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(bar)

        action_button(bar, "\U0001f4be  Salvar", _save, C.NEON_CYAN)
        bar_layout.addSpacing(8)
        action_button(bar, "\u2716  Cancelar", win.reject, C.NEON_PURP)

        win.setModal(True)
        win.show()

    def _delete_device(self, vnf: VNF) -> None:
        """Remove um VNF do inventario após confirmacao do usuario."""
        if self._access_level == "user":
            return
        reply = QMessageBox.question(None, "Excluir",
            f"Confirmar exclusao de {vnf.name} ({vnf.host})?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        vnfs = load_vnf_inventory(_INVENTORY_PATH)
        vnfs = [v for v in vnfs if v.id != vnf.id]
        save_vnf_inventory(vnfs, _INVENTORY_PATH)
        if self._target_vnf and self._target_vnf.id == vnf.id:
            self._clear_vnf_target()
        self._spawn_io(self._refresh_vnfs)

    def _on_vnf_selected(self, vnf: VNF) -> None:
        """Atualiza o alvo SSH e informacoes ao selecionar um VNF no canvas."""
        self._target_vnf = vnf
        info = f"{vnf.name} ({vnf.host})"
        if self._access_level in ("admin", "tecnico"):
            info += f":{vnf.port}"
        if self._access_level in ("admin", "tecnico") and vnf.username:
            info += f"  user:{vnf.username}"
        if self._vnf_info_lbl is not None:
            self._vnf_info_lbl.setText(f"  Selecionado: {info}")
            self._vnf_info_lbl.setStyleSheet(
                f"color: {C.NEON_CYAN}; background: {C.BG_CARD}; font: 11px 'Inter';")
        self._vnf_target_lbl.setText(info)
        log.info("VNF selecionado: %s", info)
        self._refresh_service_list()

    def _clear_vnf_target(self) -> None:
        """Limpa o alvo VNF selecionado e volta ao roteador padrao."""
        self._target_vnf = None
        self.session.override_host = None
        self.session.override_port = None
        self.session.override_username = None
        self.session.override_password = None
        self.session.override_ssh_key = None
        if self._topo_canvas:
            self._topo_canvas.deselect()
        self._vnf_target_lbl.setText("(roteador padrao)")
        if self._vnf_info_lbl is not None:
            self._vnf_info_lbl.setText("  Nenhum VNF selecionado")
            self._vnf_info_lbl.setStyleSheet(
                f"color: {C.FG_DIM}; background: {C.BG_CARD}; font: 11px 'Inter';")
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado", C.NEON_PURP)
            self._set_conn_btn()
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source="vnf", data={"reason": "target_cleared"}))
        self._refresh_service_list()

    def _refresh_dashboard(self) -> None:
        """Atualiza os indicadores do dashboard (conexao, VNFs, auditoria)."""
        try:
            conn = self._sb.is_alive()
        except Exception:
            conn = False
        if conn:
            host = getattr(self.session, "_host", "?")
            self._dash_conn_status.setText("Online")
            self._dash_conn_status.setStyleSheet(
                f"color: {C.NEON_CYAN}; font: bold 14px 'Inter'; background: {C.BG_INPUT};")
            self._dash_conn_host.setText(f"Host: {host}")
        else:
            self._dash_conn_status.setText("Desconectado")
            self._dash_conn_status.setStyleSheet(
                f"color: #ff4d4d; font: bold 14px 'Inter'; background: {C.BG_INPUT};")
            self._dash_conn_host.setText("Host: ---")

        vnfs = self._vnfs
        online = sum(1 for v in vnfs if getattr(v, "status", "") == "online")
        offline = sum(1 for v in vnfs if getattr(v, "status", "") == "offline")
        unknown = sum(1 for v in vnfs if getattr(v, "status", "") not in ("online", "offline"))
        self._dash_vnf_online.setText(f"Online: {online}")
        self._dash_vnf_offline.setText(f"Offline: {offline}")
        self._dash_vnf_unknown.setText(f"Desconhecido: {unknown}")

        try:
            text = audit.format_tail(5)
        except Exception:
            text = "  (erro ao ler auditoria)"
        self._dash_audit_text.setReadOnly(False)
        self._dash_audit_text.clear()
        self._dash_audit_text.setPlainText(text)
        self._dash_audit_text.setReadOnly(True)
