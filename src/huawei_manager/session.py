from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection as NetmikoConnection

from huawei_manager._config import PROJECT_ROOT
from huawei_manager.audit_log import AuditLogger
from huawei_manager.exceptions import SdnConnectionError, SdnValidationError
from huawei_manager.session_commands import SessionCommandsMixin
from huawei_manager.vault import SecretsBackend

log = logging.getLogger("huawei.session")


@dataclass
class ConnectionConfig:
    device_type: str = "huawei_vrp"
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    ssh_key: str | None = None
    timeout: int = 30
    ssh_strict: bool = True
    session_log: str = ""


class NetmikoSession(SessionCommandsMixin):

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
        return self.override_host or self._backend.get("ROUTER_HOST")

    @property
    def _port(self) -> int:
        return self.override_port or int(self._backend.get("ROUTER_PORT", "22"))

    @property
    def _user(self) -> str:
        if self.override_username:
            return self.override_username
        return self._backend.get("ROUTER_USERNAME")

    @property
    def _pass(self) -> str:
        if self.override_password:
            return self.override_password
        return self._backend.get("ROUTER_PASSWORD")

    @property
    def _ssh_key(self) -> str | None:
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
        raw = self._backend.get("ROUTER_HOSTKEY_VERIFY", "strict").lower().strip()
        if raw in ("strict", "tofu", "off"):
            return raw
        return "strict"

    @property
    def _session_id(self) -> str | None:
        return f"{self._host}:{self._port}" if self._conn else None

    # ── TOFU host key cache ────────────────────────────────────────
    @property
    def _known_hosts_path(self) -> Path:
        return Path("~/.ssh/huawei_known_hosts").expanduser()

    def _load_host_key(self, host: str) -> str | None:
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
        kh = self._known_hosts_path
        kh.parent.mkdir(exist_ok=True, parents=True)
        with kh.open("a") as f:
            f.write(f"{host} {key}\n")

    # ── validacao pre-conexao ─────────────────────────────────────────
    def _validate_credentials(self) -> None:
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
            raise SdnValidationError(
                "Credenciais incompletas — verifique secrets backend: "
                + ", ".join(missing)
            )

    # ── conexao ──────────────────────────────────────────────────────
    def connect(self, timeout: int = 30) -> None:
        mode = self._hk_verify
        ssh_strict = mode == "strict"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sess_dir = PROJECT_ROOT / "sessions"
        sess_log_path = ""
        try:
            sess_dir.mkdir(parents=True, exist_ok=True)
            sess_log_path = str(sess_dir / f"{self._host}_{self._port}_{ts}.log")
            log.debug("Session log: %s", sess_log_path)
        except OSError:
            log.warning("Nao foi possivel criar %s — session log desabilitado", sess_dir)

        cfg = ConnectionConfig(
            host=self._host,
            port=self._port,
            username=self._user,
            password=self._pass,
            timeout=timeout,
            ssh_strict=ssh_strict,
            session_log=sess_log_path,
        )

        key = self._ssh_key
        if key:
            cfg.ssh_key = key
            log.debug("Auth com chave SSH: %s", key)

        with self._audit.timed("connect", user=self._user, host=self._host) as ctx:
            kwargs = {k: v for k, v in {
                "device_type": cfg.device_type,
                "host": cfg.host,
                "port": cfg.port,
                "username": cfg.username,
                "password": cfg.password,
                "timeout": cfg.timeout,
                "ssh_strict": cfg.ssh_strict,
                "use_keys": True if cfg.ssh_key else None,
                "ssh_private_key_file": cfg.ssh_key,
                "session_log": cfg.session_log or None,
            }.items() if v is not None}
            self._conn = ConnectHandler(**kwargs)
            ctx.set_status("ok")

        if mode == "tofu" and self._conn:
            remote = self._conn.remote_server_key
            remote_key = f"{remote.get_name()} {remote.get_base64()}"
            cached = self._load_host_key(self._host)
            if cached and cached != remote_key:
                self.disconnect()
                raise SdnConnectionError(
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
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception as exc:
                log.warning("disconnect: %s", exc)
            self._conn = None
            log.info("Sessao SSH encerrada")

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and self._conn.is_alive()

    # ── resolve filter (delega para session_helpers) ───────────────
    @staticmethod
    def _resolve_filter(filter_xml: str | None) -> str | None:
        from huawei_manager.session_helpers import resolve_filter
        return resolve_filter(filter_xml)
