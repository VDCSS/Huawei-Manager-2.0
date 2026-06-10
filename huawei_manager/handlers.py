#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false
"""Event handlers — connection, fetch, exec, backup, dialogs, etc."""

from __future__ import annotations

import datetime
import io
import os
import tkinter as tk
from tkinter import messagebox, ttk

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from huawei_manager._config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    NCE_HOST,
    NCE_PASS,
    NCE_PORT,
    NCE_USER,
    NCE_VERIFY_SSL,
    TECNICO_PASSWORD,
    TECNICO_USERNAME,
    audit,
    log,
)
from huawei_manager.constants import (
    BG_CARD,
    BG_INPUT,
    BORDER_NRM,
    CLI_FILTERS,
    FG_DIM,
    FONT_BODY,
    FONT_MEDIUM,
    FONT_XLARGE,
    FONT_XLARGE_B,
    NEON_AMBER,
    NEON_CYAN,
    NEON_PURP,
    ROUTE_FILTER_LABELS,
)
from huawei_manager.services import VNF_TYPES, ServiceDef, execute_service
from huawei_manager.topology import (
    VNF,
    NorthboundController,
    load_vnf_inventory,
    probe_vnfs,
    save_vnf_inventory,
    simulate_status,
)
from huawei_manager.widgets import action_button


class EventHandlers:

    ADMIN_MAX_ATTEMPTS = 3
    ADMIN_LOCKOUT_SECS = 30

    # ══════════════════════════════════════════════════════════════════
    #  CONEXAO SSH
    # ══════════════════════════════════════════════════════════════════
    def _get_selected_vnf(self) -> VNF | None:
        return (self._topo_canvas.get_selected()
                if self._topo_canvas else None) or self._target_vnf

    def _toggle_connect(self) -> None:
        if self.session.is_connected:
            self.session.disconnect()
            self._set_status("Desconectado", NEON_PURP)
            self._set_conn_btn()
            return

        vnf = self._get_selected_vnf()
        if vnf:
            self._connect_with_vnf(vnf)
        else:
            self._connect_default()

    def _do_connect(self, on_success_fmt: str, on_error_msg: str) -> None:
        def _do():
            try:
                self.session.connect()
                sid = self.session._session_id or "?"
                self.root.after(0, lambda: self._set_status(
                    on_success_fmt.format(sid=sid), NEON_CYAN))
                self._set_conn_btn("  DESCONECTAR  ")
            except NetmikoAuthenticationException:
                self.root.after(0, lambda: self._set_status(
                    "Falha de autenticacao", NEON_AMBER))
                self._set_conn_btn()
            except NetmikoTimeoutException:
                self.root.after(0, lambda: self._set_status(
                    "Timeout de conexao", NEON_AMBER))
                self._set_conn_btn()
            except ValueError as exc:
                msg = f"Config: {exc}"
                self.root.after(0, lambda m=msg: self._set_status(m, NEON_AMBER))
                self._set_conn_btn()
            except Exception as exc:
                log.exception("Falha inesperada em _do_connect: %s", exc)
                self.root.after(0, lambda: self._set_status(
                    on_error_msg, NEON_AMBER))
                self._set_conn_btn()

        self._spawn(_do)

    def _connect_default(self) -> None:
        self._set_status("Conectando SSH\u2026", NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect("SSH \u2714  {sid}", "Erro ao conectar")

    def _connect_with_vnf(self, vnf: VNF) -> None:
        if self.session.is_connected:
            self.session.disconnect()
        self.session.override_host = vnf.host
        self.session.override_port = vnf.port
        self.session.override_username = vnf.username or None
        self.session.override_password = vnf.password or None
        self.session.override_ssh_key = vnf.ssh_key or None
        self._set_status(f"Conectando ao VNF {vnf.name}\u2026", NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect(f"VNF \u2714  {vnf.name}  {{sid}}", "Erro ao conectar ao VNF")

    # ══════════════════════════════════════════════════════════════════
    #  FETCH METHODS
    # ══════════════════════════════════════════════════════════════════
    def _fetch_config(self) -> None:
        self._loading(self.out_config, "Carregando configuracao atual\u2026")
        self._write(self.out_config, self.session.run_cli_rpc("display current-configuration"))

    def _fetch_route(self) -> None:
        label_to_key = {v: k for k, v in ROUTE_FILTER_LABELS.items()}
        fkey = label_to_key.get(self.route_filter_var.get(), "routing")
        cmd  = CLI_FILTERS.get(fkey, "display ip routing-table")
        self._loading(self.out_route, f"Executando: {cmd}\u2026")
        self._write(self.out_route, self.session.run_cli_rpc(cmd or ""))

    def _fetch_arp(self) -> None:
        self._loading(self.out_arp, "Executando: display arp\u2026")
        self._write(self.out_arp, self.session.run_cli_rpc("display arp"))

    def _fetch_info(self) -> None:
        self._loading(self.out_info, "Coletando informacoes do sistema\u2026")
        buf = io.StringIO()
        commands = [
            ("Versao / Sistema", "display version"),
            ("Dispositivo", "display device"),
            ("Licenca", "display license"),
            ("CPU", "display cpu-usage"),
            ("Memoria", "display memory-usage"),
            ("Interfaces", "display interface brief"),
            ("LLDP", "display lldp neighbor brief"),
        ]
        for title, cmd in commands:
            buf.write(f"{'=' * 70}\n\u25b6  {title}\n{'-' * 70}\n")
            buf.write(self.session.run_cli_rpc(cmd or ""))
            buf.write("\n\n")
        self._write(self.out_info, buf.getvalue())

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR
    # ══════════════════════════════════════════════════════════════════
    def _on_tpl_select(self, _event=None) -> None:
        sel = self._tpl_listbox.curselection()
        if not sel:
            return
        name = self._tpl_listbox.get(sel[0])
        cmd  = self._tpl_cmd_map.get(name, name) or ""
        self._cmd_editor.delete("1.0", "end")
        self._cmd_editor.insert("end", cmd)

    def _get_editor_cmd(self) -> str:
        return self._cmd_editor.get("1.0", "end").strip()

    def _exec_cmd(self) -> None:
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd, "\u2718  Editor vazio \u2014 digite um comando")
            return
        if self._sysview_var.get():
            self._loading(self.out_cmd,
                          "system-view \u2192 " + cmd.splitlines()[0] + " \u2192 quit\u2026")
            self.session.run_cli_timing("system-view")
            result = self.session.run_cli_timing(cmd)
            self.session.run_cli_timing("quit")
        else:
            self._loading(self.out_cmd, f"Executando: {cmd}\u2026")
            result = self.session.run_cli_rpc(cmd or "")
        self._write(self.out_cmd, result)

    def _exec_config(self) -> None:
        cmd = self._get_editor_cmd()
        if not cmd:
            self._write(self.out_cmd,
                         "\u2718  Editor vazio \u2014 digite os comandos de configuracao")
            return
        self._loading(self.out_cmd, "Aplicando configuracao\u2026")
        ok, msg = self.session.edit_config(cmd)
        self._write(self.out_cmd, msg)

    # ══════════════════════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════════════════════
    def _do_backup(self) -> None:
        fmt = self.backup_fmt.get()
        self._loading(self.out_backup, "Coletando configuracao para backup\u2026")
        conteudo = self.session.run_cli_rpc("display current-configuration")
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ext  = "txt"
        host = self.session._host
        nome = f"backup_{host}_{ts}.{ext}"
        pasta = self.backup_path.get().strip() or os.path.expanduser("~")
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
            self.root.after(0, lambda: self._set_status(f"Backup: {nome}", NEON_CYAN))
            audit.log_operation("backup", user=self.session._user,
                                host=host, status="ok", file=path)
            log.info("Backup salvo: %s (%d bytes)", path, os.path.getsize(path))
        except OSError as ex:
            log.error("Backup falhou: %s", ex)
            self._write(self.out_backup, f"\u2718  Erro ao salvar:\n  {ex}")

    # ══════════════════════════════════════════════════════════════════
    #  SERVICOS
    # ══════════════════════════════════════════════════════════════════
    def _run_service(self, svc: ServiceDef) -> None:
        mode = self._svc_mode_var.get()
        vnf = self._target_vnf
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if vnf:
            label += f"  |  Alvo: {vnf.name} ({vnf.host})"
        self._svc_vnf_lbl.configure(text=label)

        final_svc = svc
        if svc.config_mode and self._svc_param_entries:
            cmd = svc.description
            for name, entry in self._svc_param_entries.items():
                cmd = cmd.replace(f"<{name}>", entry.get().strip())
            final_svc = ServiceDef(
                id=svc.id, name=svc.name, description=svc.description,
                category=svc.category, vnf_types=svc.vnf_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        def _do():
            self._loading(self._svc_output, f"Executando: {svc.name} ({mode})\u2026")

            if mode == "mock":
                result = execute_service(final_svc, session_type="mock")
                self._write(self._svc_output, result)
                return

            if not self.session.is_connected:
                self._write(self._svc_output,
                    "\u2718  Sem sessao SSH ativa. Conecte-se primeiro.")
                return

            if mode == "cli":
                result = execute_service(final_svc, session_type="cli",
                                         session=self.session._conn)
                self._write(self._svc_output, result)
                return

            self._write(self._svc_output, f"Modo desconhecido: {mode}")

        self._spawn(_do)

    # ══════════════════════════════════════════════════════════════════
    #  TOPOLOGIA / VNFs
    # ══════════════════════════════════════════════════════════════════
    def _init_topology_backend(self) -> None:
        use_mock = not NCE_HOST
        self._nce_ctrl = NorthboundController(
            host=NCE_HOST, port=NCE_PORT,
            username=NCE_USER, password=NCE_PASS,
            verify_ssl=NCE_VERIFY_SSL,
            use_mock=use_mock,
        )
        log.info("Topology backend: mock=%s", use_mock)
        log.debug("Topology backend: mock=%s host=%s", use_mock, NCE_HOST or "(local)")

    def _refresh_vnfs(self) -> None:
        if getattr(self, "_vnfs_busy", False):
            return
        self._vnfs_busy = True
        try:
            vnfs = load_vnf_inventory()
            if getattr(self, "_mock_mode", False):
                vnfs = simulate_status(vnfs)
            else:
                vnfs = probe_vnfs(vnfs)
            save_vnf_inventory(vnfs)
            self.root.after(0, lambda: self._update_vnfs_ui(vnfs))
            self.root.after(0, lambda: self._nce_status_lbl.configure(
                text=("Inventario: {} dispositivos  \u2022  {}"
                           .format(len(vnfs), datetime.datetime.now().strftime('%H:%M:%S')))
            ) if hasattr(self, "_nce_status_lbl") else None)
        finally:
            self._vnfs_busy = False

    def _update_vnfs_ui(self, vnfs: list[VNF]) -> None:
        self._vnfs = vnfs
        if self._topo_canvas:
            self._topo_canvas.set_access(self._access_level)
            self._topo_canvas.update_vnfs(vnfs)

    # ── Autenticação (Admin / Técnico) ────────────────────────────────
    def _show_auth_dialog(self) -> None:
        if self._access_level != "user":
            self._access_level = "user"
            self._mock_mode = False
            if self._topo_canvas:
                self._topo_canvas.set_access("user")
            self._admin_btn.configure(text="\U0001f512  Acesso")
            self._update_vnfs_ui(self._vnfs)
            log.info("Acesso: deslogado")
            return

        if hasattr(self, "_auth_win") and self._auth_win.winfo_exists():
            return

        if not ADMIN_PASSWORD or not TECNICO_PASSWORD:
            messagebox.showwarning(
                "Configuracao incompleta",
                "Defina ADMIN_PASSWORD e TECNICO_PASSWORD no .env")
            return

        now = datetime.datetime.now().timestamp()
        if now < self._admin_locked_until:
            remaining = int(self._admin_locked_until - now)
            messagebox.showwarning(
                "Acesso Bloqueado",
                f"Tentativas excedidas. Aguarde {remaining}s e tente novamente.")
            return

        win = tk.Toplevel(self.root)
        win.title("Autenticacao")
        win.geometry("360x240")
        win.configure(bg=BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._auth_win = win

        tk.Label(win, text="Acesso Restrito", bg=BG_CARD, fg=NEON_CYAN,
                 font=FONT_XLARGE_B).pack(pady=(16, 8))

        tk.Label(win, text="Usuario:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(anchor="w", padx=24)
        user_var = tk.StringVar()
        user_entry = tk.Entry(win, textvariable=user_var,
                              bg=BG_INPUT, fg=NEON_CYAN, font=FONT_XLARGE,
                              relief="flat", bd=0, highlightthickness=1,
                              highlightbackground=BORDER_NRM)
        user_entry.pack(padx=24, fill="x", pady=(0, 8))
        user_entry.focus_set()

        tk.Label(win, text="Senha:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(anchor="w", padx=24)
        pw_var = tk.StringVar()
        pw_entry = tk.Entry(win, textvariable=pw_var, show="*",
                            bg=BG_INPUT, fg=NEON_CYAN, font=FONT_XLARGE,
                            relief="flat", bd=0, highlightthickness=1,
                            highlightbackground=BORDER_NRM)
        pw_entry.pack(padx=24, fill="x", pady=(0, 12))

        def _verify():
            nonlocal now
            user = user_var.get().strip()
            pw = pw_var.get()

            level = "user"
            if user == TECNICO_USERNAME and pw == TECNICO_PASSWORD:
                level = "tecnico"
            elif user == ADMIN_USERNAME and pw == ADMIN_PASSWORD:
                level = "admin"

            if level != "user":
                self._access_level = level
                self._admin_attempts = 0
                if self._topo_canvas:
                    self._topo_canvas.set_access(level)
                label = "\U0001f513  Admin" if level == "admin" else "\U0001f6e0  Tecnico"
                self._admin_btn.configure(text=label)
                self._update_vnfs_ui(self._vnfs)
                self._auth_win = None
                win.destroy()
                log.info("Acesso: %s autenticado", level)
            else:
                self._admin_attempts += 1
                remaining = self.ADMIN_MAX_ATTEMPTS - self._admin_attempts
                if remaining <= 0:
                    self._admin_locked_until = \
                        datetime.datetime.now().timestamp() + self.ADMIN_LOCKOUT_SECS
                    self._admin_attempts = 0
                    self._auth_win = None
                    win.destroy()
                    messagebox.showerror(
                        "Acesso Bloqueado",
                        f"Credenciais incorretas. Acesso bloqueado por "
                        f"{self.ADMIN_LOCKOUT_SECS}s.")
                    log.warning("Acesso: lockout por %ds", self.ADMIN_LOCKOUT_SECS)
                else:
                    messagebox.showerror(
                        "Autenticacao",
                        f"Usuario ou senha incorretos. "
                        f"{remaining} tentativa(s) restante(s).")
                    pw_var.set("")
                    pw_entry.focus_set()

        action_button(win, "Autenticar", _verify, NEON_CYAN).pack(pady=8)
        pw_entry.bind("<Return>", lambda _: _verify())
        win.bind("<Escape>", lambda _: (setattr(self, "_auth_win", None), win.destroy()))

    # ── Device Dialog ────────────────────────────────────────────────
    def _show_device_dialog(self, vnf: VNF | None = None) -> None:
        if self._access_level == "user":
            return
        editing = vnf is not None
        vnf = vnf or VNF(id="", name="", host="")

        win = tk.Toplevel(self.root)
        win.title("Editar Dispositivo" if editing else "Cadastrar Dispositivo")
        win.geometry("500x480")
        win.configure(bg=BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        fields = [
            ("host", "IP / Host", vnf.host),
            ("port", "Porta SSH", str(vnf.port)),
            ("username", "Usuario SSH", vnf.username),
            ("password", "Senha SSH", vnf.password, True),
            ("ssh_key", "Chave SSH (path)", vnf.ssh_key),
            ("location", "Localizacao", vnf.location),
        ]

        row_frame = tk.Frame(win, bg=BG_CARD)
        row_frame.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(row_frame, text="Nome:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        name_var = tk.StringVar(value=vnf.name)
        tk.Entry(row_frame, textvariable=name_var, bg=BG_INPUT,
                 fg=NEON_CYAN, font=FONT_MEDIUM, relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=BORDER_NRM).pack(
                     side="left", fill="x", expand=True, ipady=4)

        row_frame2 = tk.Frame(win, bg=BG_CARD)
        row_frame2.pack(fill="x", padx=20, pady=(4, 12))
        tk.Label(row_frame2, text="Tipo:", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_BODY).pack(side="left", padx=(0, 8))
        type_var = tk.StringVar(value=vnf.type)
        type_cb = ttk.Combobox(row_frame2, textvariable=type_var,
                               values=list(VNF_TYPES.keys()),
                               state="readonly", width=18, font=FONT_BODY)
        type_cb.pack(side="left", fill="x", expand=True)

        vars_dict: dict[str, tk.StringVar] = {"name": name_var, "type": type_var}
        secret_vars: dict[str, tk.StringVar] = {}

        for fname, flabel, *rest in fields:
            is_secret = len(rest) > 1 and rest[1] is True
            default = rest[0]
            fr = tk.Frame(win, bg=BG_CARD)
            fr.pack(fill="x", padx=20, pady=3)
            tk.Label(fr, text=f"{flabel}:", bg=BG_CARD, fg=FG_DIM,
                     font=FONT_BODY).pack(side="left", padx=(0, 8))
            var = tk.StringVar(value=default)
            show_char = "*" if is_secret else ""
            entry = tk.Entry(fr, textvariable=var, show=show_char,
                             bg=BG_INPUT, fg=NEON_CYAN, font=FONT_MEDIUM,
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=BORDER_NRM)
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            vars_dict[fname] = var

            if is_secret:
                secret_vars[fname] = var
                def _toggle(e=None, ev=var, en=entry):
                    en.configure(show="" if en.cget("show") == "*" else "*")
                btn = tk.Label(fr, text="\U0001f441", bg=BG_CARD, fg=NEON_PURP,
                               font=FONT_XLARGE, cursor="hand2")
                btn.pack(side="left", padx=(4, 0))
                btn.bind("<Button-1>", _toggle)

        def _save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Validacao", "Nome e obrigatorio.")
                return
            host = vars_dict["host"].get().strip()
            if not host:
                messagebox.showwarning("Validacao", "IP/Host e obrigatorio.")
                return

            try:
                port_val = int(vars_dict["port"].get().strip() or "22")
            except ValueError:
                port_val = 22

            vnfs = load_vnf_inventory()
            if editing:
                new_vnf = VNF(
                    id=vnf.id, name=name,
                    host=host, port=port_val,
                    type=type_var.get(),
                    username=vars_dict["username"].get().strip(),
                    password=vars_dict["password"].get().strip(),
                    ssh_key=vars_dict["ssh_key"].get().strip(),
                    location=vars_dict["location"].get().strip(),
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
                    type=type_var.get(),
                    username=vars_dict["username"].get().strip(),
                    password=vars_dict["password"].get().strip(),
                    ssh_key=vars_dict["ssh_key"].get().strip(),
                    location=vars_dict["location"].get().strip(),
                )
                vnfs.append(new_vnf)

            save_vnf_inventory(vnfs)
            win.destroy()
            self._spawn(self._refresh_vnfs)

        bar = tk.Frame(win, bg=BG_CARD)
        bar.pack(fill="x", padx=20, pady=(16, 12))
        action_button(bar, "\U0001f4be  Salvar", _save, NEON_CYAN).pack(side="left", padx=(0, 8))
        action_button(bar, "\u2716  Cancelar", win.destroy, NEON_PURP).pack(side="left")
        win.bind("<Escape>", lambda _: win.destroy())

    def _delete_device(self, vnf: VNF) -> None:
        if self._access_level == "user":
            return
        if not messagebox.askyesno("Excluir",
                                    f"Confirmar exclusao de {vnf.name} ({vnf.host})?"):
            return
        vnfs = load_vnf_inventory()
        vnfs = [v for v in vnfs if v.id != vnf.id]
        save_vnf_inventory(vnfs)
        if self._target_vnf and self._target_vnf.id == vnf.id:
            self._clear_vnf_target()
        self._spawn(self._refresh_vnfs)

    def _on_vnf_selected(self, vnf: VNF) -> None:
        self._target_vnf = vnf
        info = f"{vnf.name} ({vnf.host})"
        if self._access_level in ("admin", "tecnico"):
            info += f":{vnf.port}"
        if self._access_level in ("admin", "tecnico") and vnf.username:
            info += f"  user:{vnf.username}"
        if hasattr(self, "_vnf_info_lbl"):
            self._vnf_info_lbl.configure(
                text=f"  Selecionado: {info}", fg=NEON_CYAN)
        self._vnf_target_lbl.configure(text=info)
        log.info("VNF selecionado: %s", info)
        self._refresh_service_list()

    def _clear_vnf_target(self) -> None:
        self._target_vnf = None
        self.session.override_host = None
        self.session.override_port = None
        self.session.override_username = None
        self.session.override_password = None
        self.session.override_ssh_key = None
        if self._topo_canvas:
            self._topo_canvas.deselect()
        self._vnf_target_lbl.configure(text="(roteador padrao)")
        if hasattr(self, "_vnf_info_lbl"):
            self._vnf_info_lbl.configure(
                text="  Nenhum VNF selecionado", fg=FG_DIM)
        if self.session.is_connected:
            self.session.disconnect()
            self._set_status("Desconectado", NEON_PURP)
            self._set_conn_btn()
        self._refresh_service_list()

    def _refresh_dashboard(self) -> None:
        try:
            conn = self.session.is_connected
        except Exception:
            conn = False
        if conn:
            host = getattr(self.session, "_host", "?")
            self._dash_conn_status.configure(text="Online", fg=NEON_CYAN)
            self._dash_conn_host.configure(text=f"Host: {host}")
        else:
            self._dash_conn_status.configure(text="Desconectado", fg="#ff4d4d")
            self._dash_conn_host.configure(text="Host: ---")

        vnfs = getattr(self, "_vnfs", [])
        online = sum(1 for v in vnfs if getattr(v, "status", "") == "online")
        offline = sum(1 for v in vnfs if getattr(v, "status", "") == "offline")
        unknown = sum(1 for v in vnfs if getattr(v, "status", "") not in ("online", "offline"))
        self._dash_vnf_online.configure(text=f"Online: {online}")
        self._dash_vnf_offline.configure(text=f"Offline: {offline}")
        self._dash_vnf_unknown.configure(text=f"Desconhecido: {unknown}")

        try:
            text = audit.format_tail(5)
        except Exception:
            text = "  (erro ao ler auditoria)"
        self._dash_audit_text.configure(state="normal")
        self._dash_audit_text.delete("1.0", "end")
        self._dash_audit_text.insert("1.0", text)
        self._dash_audit_text.configure(state="disabled")
