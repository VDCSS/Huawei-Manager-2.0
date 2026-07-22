"""SSH mixin — connect / disconnect helpers."""

from __future__ import annotations

import logging

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import (
    DeviceConnectedPayload,
    DeviceDisconnectedPayload,
)
from huawei_manager.vnf_models import VNF

log = logging.getLogger(__name__)


class SshMixin:
    """Mixin com metodos de conexao SSH."""

    # ══════════════════════════════════════════════════════════════════
    #  CONEXAO SSH
    # ══════════════════════════════════════════════════════════════════
    def _get_selected_vnf(self: AppCoreProtocol) -> VNF | None:
        """Retorna o VNF selecionado no canvas ou o alvo salvo em _target_vnf."""
        return (self._topo_canvas.get_selected()
                if self._topo_canvas else None) or self._target_vnf

    def _toggle_connect(self: AppCoreProtocol) -> None:
        """Alterna entre conectar (VNF alvo ou default) e desconectar."""
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado", C.NEON_PURP)
            self._set_conn_btn()
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source="user",
                                        payload=DeviceDisconnectedPayload(reason="manual")))
            return

        vnf = self._get_selected_vnf()
        if vnf:
            self._connect_with_vnf(vnf)
        else:
            self._connect_default()

    def _do_connect(self: AppCoreProtocol, on_success_fmt: str, on_error_msg: str) -> None:
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
                                            source="user",
                                            payload=DeviceConnectedPayload(
                                                host=self.session.override_host or "",
                                                session_id=sid,
                                            )))
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

    def _connect_default(self: AppCoreProtocol) -> None:
        """Conecta ao roteador padrao definido nas configuracoes."""
        self._set_status("Conectando SSH\u2026", C.NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect("SSH \u2714  {sid}", "Erro ao conectar")

    def _connect_with_vnf(self: AppCoreProtocol, vnf: VNF) -> None:
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
