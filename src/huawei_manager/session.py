from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection as NetmikoConnection

from huawei_manager.audit_log import AuditLogger
from huawei_manager.utils import clean_output, sanitize_command
from huawei_manager.vault import SecretsBackend

log = logging.getLogger("huawei.session")


class NetmikoSession:
    """
    Sessao SSH via Netmiko (transporte principal).

    Seguranca:
      - Credenciais via SecretsBackend (nunca hardcoded)
      - hostkey_verify configuravel (true em producao)
      - Auditoria de cada operacao via AuditLogger
      - Suporte a reconexao com host/porta de VNF alternativo
      - Session log gravado em sessions/
    """

    def __init__(
        self,
        backend: SecretsBackend,
        audit_logger: AuditLogger,
        override_host: str | None = None,
        override_port: int | None = None,
        override_username: str | None = None,
        override_password: str | None = None,
        override_ssh_key: str | None = None,
    ) -> None:
        """Inicializa sessao com backend de secrets, audit e overrides opcionais de VNF."""
        self._backend = backend
        self._audit   = audit_logger
        self._conn: NetmikoConnection | None = None
        self._lock = threading.Lock()
        self.override_host = override_host
        self.override_port = override_port
        self.override_username = override_username
        self.override_password = override_password
        self.override_ssh_key = override_ssh_key

    # ── credenciais dinamicas ─────────────────────────────────────────
    @property
    def _host(self) -> str:
        """Retorna o host (override ou do backend)."""
        return self.override_host or self._backend.get("ROUTER_HOST")

    @property
    def _port(self) -> int:
        """Retorna a porta (override ou do backend, padrao 2222)."""
        return self.override_port or int(self._backend.get("ROUTER_PORT", "2222"))

    @property
    def _user(self) -> str:
        """Retorna o usuario (override ou do backend)."""
        if self.override_username:
            return self.override_username
        return self._backend.get("ROUTER_USERNAME")

    @property
    def _pass(self) -> str:
        """Retorna a senha (override ou do backend)."""
        if self.override_password:
            return self.override_password
        return self._backend.get("ROUTER_PASSWORD")

    @property
    def _ssh_key(self) -> str | None:
        """Retorna o caminho da chave SSH (override ou do backend), ou None."""
        if self.override_ssh_key:
            p = Path(os.path.expanduser(self.override_ssh_key)).resolve()
            return str(p) if p.is_file() else None
        key_str = self._backend.get("ROUTER_SSH_KEY", "").strip()
        if not key_str:
            return None
        p = Path(os.path.expanduser(key_str)).resolve()
        return str(p) if p.is_file() else None

    @property
    def _hk_verify(self) -> str:
        """Modo de verificacao de hostkey: 'strict', 'tofu' ou 'off'."""
        raw = self._backend.get("ROUTER_HOSTKEY_VERIFY", "strict").lower().strip()
        if raw in ("strict", "tofu", "off"):
            return raw
        return "strict"

    @property
    def _session_id(self) -> str | None:
        """Retorna 'host:port' da sessao ativa, ou None."""
        return f"{self._host}:{self._port}" if self._conn else None

    # ── TOFU host key cache ────────────────────────────────────────
    @property
    def _known_hosts_path(self) -> Path:
        """Path do arquivo known_hosts do Huawei Manager."""
        return Path("~/.ssh/huawei_known_hosts").expanduser()

    def _load_host_key(self, host: str) -> str | None:
        """Carrega a chave publica do host do arquivo known_hosts.

        Returns:
            A string ``\"<tipo> <base64>\"`` da chave, ou None se nao
            encontrada.
        """
        kh = self._known_hosts_path
        if not kh.exists():
            return None
        for line in kh.read_text().splitlines():
            line = line.strip()
            if line.startswith(host) and " " in line:
                _, _, rest = line.partition(" ")
                return rest.strip()
        return None

    def _save_host_key(self, host: str, key: str) -> None:
        """Salva a chave publica do host no arquivo known_hosts (append)."""
        kh = self._known_hosts_path
        kh.parent.mkdir(exist_ok=True, parents=True)
        with kh.open("a") as f:
            f.write(f"{host} {key}\n")

    # ── validacao pre-conexao ─────────────────────────────────────────
    def _validate_credentials(self) -> None:
        """Verifica se host/usuario/senha ou chave estao preenchidos; lanca ValueError se nao."""
        missing = []
        if not self._host:
            missing.append("ROUTER_HOST")
        if not self._user:
            missing.append("ROUTER_USERNAME")
        pw = self._pass
        key = self._ssh_key
        if not pw and not key:
            missing.append("ROUTER_PASSWORD ou ROUTER_SSH_KEY")
        if missing:
            raise ValueError(
                "Credenciais incompletas — verifique secrets backend: "
                + ", ".join(missing)
            )

    # ── conexao ──────────────────────────────────────────────────────
    def connect(self, timeout: int = 30) -> None:
        """Abre sessao SSH via Netmiko com as credenciais configuradas.

        O modo de verificacao de hostkey e definido por ``_hk_verify``:

        * ``"strict"`` — rejeita qualquer host desconhecido ou com chave
          diferente (ssh_strict=True). Seguro, mas exige known_hosts
          previamente populado.
        * ``"tofu"`` — na primeira conexao aceita e salva a chave em
          ``~/.ssh/huawei_known_hosts``; nas seguintes rejeita se a
          chave mudar. Ideal para lab (Trust on First Use).
        * ``"off"`` — ignora verificacao de host key (ssh_strict=False).
          Apenas para laboratorio isolado.

        Args:
            timeout: Timeout de conexao em segundos (padrao 30).
        """
        mode = self._hk_verify
        ssh_strict = mode == "strict"

        kwargs = dict(
            device_type="huawei_vrp",
            host=self._host,
            port=self._port,
            username=self._user,
            password=self._pass,
            timeout=timeout,
            ssh_strict=ssh_strict,
        )

        key = self._ssh_key
        if key:
            kwargs["use_keys"] = True
            kwargs["ssh_private_key_file"] = key
            log.debug("Auth com chave SSH: %s", key)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sess_dir = Path("sessions")
        sess_dir.mkdir(exist_ok=True)
        sess_log = sess_dir / f"{self._host}_{self._port}_{ts}.log"
        kwargs["session_log"] = str(sess_log)
        log.debug("Session log: %s", sess_log)

        with self._audit.timed("connect", user=self._user, host=self._host) as ctx:
            self._conn = ConnectHandler(**kwargs)
            ctx.set_status("ok")

        # TOFU: verificar e/ou salvar host key apos conexao
        if mode == "tofu" and self._conn:
            remote = self._conn.remote_server_key
            remote_key = f"{remote.get_name()} {remote.get_base64()}"
            cached = self._load_host_key(self._host)
            if cached and cached != remote_key:
                self.disconnect()
                raise ValueError(
                    f"Host key mismatch for {self._host} — "
                    "possible MITM attack"
                )
            if not cached:
                self._save_host_key(self._host, remote_key)
                log.debug("Host key cached for %s", self._host)

        log.info("Sessao SSH aberta")
        log.debug("Sessao SSH aberta — %s", self._host)
        self._audit.log_operation(
            "connect", user=self._user, host=self._host,
            status="ok", session_id=self._session_id,
        )

    def disconnect(self) -> None:
        """Fecha a sessao SSH se ativa."""
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception as exc:
                log.warning("disconnect: %s", exc)
            self._conn = None
            log.info("Sessao SSH encerrada")

    @property
    def is_connected(self) -> bool:
        """Retorna True se a conexao SSH esta ativa."""
        return self._conn is not None and self._conn.is_alive()

    # ── executa comando CLI ──────────────────────────────────────────
    def _cmd(self, command: str) -> str:
        """Executa comando CLI via Netmiko e retorna output limpo."""
        if not self._conn:
            return "Sem conexao"
        try:
            out = self._conn.send_command(command, read_timeout=120)
            return clean_output(str(out))
        except Exception as e:
            log.exception("Comando falhou: %s", command)
            return f"ERRO: {e}"

    def run_cli_timing(self, cmd: str) -> str:
        """Executa comando com send_command_timing e retorna output limpo."""
        if not self._conn:
            return "Sem conexao"
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-timing", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                try:
                    out = self._conn.send_command_timing(cmd, read_timeout=120)
                    ctx.set_status("ok")
                    return clean_output(str(out))
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("CLI timing falhou: %s", cmd)
                    return f"ERRO: {e}"

    # ── mapeia filtro (key) para comando CLI ──────────────────────────
    @staticmethod
    def _resolve_filter(filter_xml: str | None) -> str | None:
        """Mapeia um filtro XML para o comando CLI correspondente."""
        if filter_xml is None:
            return None
        f = filter_xml.lower()
        if "full_config" in f or "current-configuration" in f:
            return "display current-configuration"
        if "interface" in f and "counter" not in f:
            return "display interface"
        if "interface" in f and "counter" in f:
            return "display counters interface"
        if "routing" in f or "route" in f or "network-instance" in f:
            return "display ip routing-table"
        if "bgp" in f or "huawei_bgp" in f:
            return "display bgp peer"
        if "ospf" in f:
            return "display ospf peer"
        if "vrf" in f or "vpn-instance" in f:
            return "display ip vpn-instance"
        if "lldp" in f:
            return "display lldp neighbor brief"
        if "qos" in f:
            return "display qos policy"
        if "system" in f or "cpu" in f or "mem" in f:
            return "display cpu-usage"
        if "arp" in f:
            return "display arp"
        if "mpls" in f:
            return "display mpls ldp peer"
        if "platform" in f or "component" in f or "version" in f:
            return "display version"
        return None

    # ── get config via CLI ────────────────────────────────────────────
    def get_config(
        self,
        filter_xml: str | None = None,
        source: str = "running",
    ) -> str:
        """Obtem configuracao do dispositivo via CLI, com filtro opcional."""
        cmd = self._resolve_filter(filter_xml) or "display current-configuration"
        with self._lock:
            with self._audit.timed(
                "get-config", user=self._user, host=self._host,
                datastore=source, session_id=self._session_id,
            ) as ctx:
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    return f"ERRO: {e}"

    # ── get estado operacional via CLI ────────────────────────────────
    def get(self, filter_xml: str | None = None) -> str:
        """Obtem estado operacional do dispositivo via CLI (ex: routing-table)."""
        cmd = self._resolve_filter(filter_xml) or "display ip routing-table"
        with self._lock:
            with self._audit.timed(
                "get", user=self._user, host=self._host,
                session_id=self._session_id,
            ) as ctx:
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    return f"ERRO: {e}"

    # ── edit config via CLI ───────────────────────────────────────────
    def edit_config(
        self,
        config: str,
        target: str = "running",
    ) -> tuple[bool, str]:
        """Aplica configuracao via CLI (send_config_set) e salva. Retorna (sucesso, mensagem)."""
        if not self._conn:
            return False, "Sem conexao"
        with self._lock:
            with self._audit.timed(
                "edit-config", user=self._user, host=self._host,
                datastore=target, session_id=self._session_id,
            ) as ctx:
                try:
                    lines = [line.strip() for line in config.splitlines() if line.strip()]
                    output = self._conn.send_config_set(lines, read_timeout=120)
                    self._conn.save_config()
                    ctx.set_status("ok")
                    return True, f"OK Configuracao aplicada\n{output}"
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("edit-config falhou")
                    return False, f"ERRO: {e}"

    # ── schemas (nao aplicavel via CLI) ───────────────────────────────
    def get_schemas(self) -> str:
        """Retorna mensagem informando que schemas NAO estao disponiveis via CLI."""
        return "Schemas nao disponiveis via Netmiko/CLI."

    # ── capabilities ─────────────────────────────────────────────────
    def get_capabilities(self) -> str:
        """Retorna a versao do dispositivo via CLI (display version)."""
        return self._cmd("display version")

    # ── comando CLI livre ─────────────────────────────────────────────
    def run_cli_rpc(self, cmd: str) -> str:
        """Executa comando CLI livre e retorna output com auditoria."""
        sanitized = sanitize_command(cmd)
        with self._lock:
            with self._audit.timed(
                "cli-rpc", user=self._user, host=self._host,
                session_id=self._session_id, cmd=sanitized,
            ) as ctx:
                try:
                    result = self._cmd(cmd)
                    ctx.set_status("ok")
                    return result
                except Exception as e:
                    ctx.set_status("error")
                    log.exception("CLI falhou")
                    return f"ERRO: {e}"
